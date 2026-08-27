"""Command line interface for the GameVisual fixer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from . import __version__
from .applier import AppliedReport, apply
from .edid import EdidInfo
from .planner import FixPlan, build_plan
from .sysprobe import (
    PanelInfo,
    ProbeIssue,
    board_product,
    is_admin,
    is_windows,
    list_panels,
    try_elevate,
)

DEFAULT_GAMEVISUAL_DIR: Final = Path(r"C:\ProgramData\ASUS\GameVisual")
DEFAULT_SPOOL_DIR: Final = Path(r"C:\Windows\System32\spool\drivers\color")

NEXT_STEPS: Final = """接下来请你手动完成（很重要）:
  1. 断开网络（关 Wi-Fi / 拔网线）
  2. 完全关机（不是重启）
  3. 开机后打开奥创中心 -> GameVisual 查看效果
提示: 断网是为了防止奥创联网下载官方文件覆盖修复，详见 README。"""

# planner 生成的原因是英文，展示层翻译成小白能看懂的说法
REASON_ZH: Final[dict[str, str]] = {
    "bundled profile matches panel hardware id": "ICC 库里有这个面板的文件，直接匹配",
    "fallback: same panel product code, different vendor prefix": "同产品号兜底匹配（厂商前缀不同）",
    "gamut switch profile missing on system": "色域切换所需的配置缺失",
}

_MISNAMED_PREFIX: Final = "repair misnamed id "

# sysprobe 返回的 detail 是英文，展示层翻译成小白能看懂的说法
DETAIL_ZH: Final[dict[str, str]] = {
    "no instance exposes an EDID value": "该设备未提供 EDID 数据（外接转换器/采集卡等属正常现象）",
    "BaseBoardProduct/SystemProductName not found in registry": "注册表里找不到机型信息",
}


def _reason_zh(reason: str) -> str:
    if reason in REASON_ZH:
        return REASON_ZH[reason]
    if reason.startswith(_MISNAMED_PREFIX):
        return f"修正错误命名的旧文件（{reason[len(_MISNAMED_PREFIX):]}）"
    return reason


def _detail_zh(detail: str) -> str:
    return DETAIL_ZH.get(detail, detail)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gamevisual_fixer",
        description="修复华硕/ROG 换屏后奥创中心 GameVisual 失效。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只看计划，不修改任何文件")
    parser.add_argument("--yes", action="store_true", help="兼容保留（默认已自动执行）")
    parser.add_argument("--ask", action="store_true", help="修复前询问确认（默认自动执行）")
    parser.add_argument(
        "--library", type=Path, default=None, help="自定义 ICC 库目录（默认本仓库 color/）"
    )
    parser.add_argument("--model", default=None, help="手动指定机型代码，如 FX507ZM")
    parser.add_argument("--panel-hwid", default=None, help="手动指定面板硬件 ID，如 770E150F")
    parser.add_argument(
        "--gamevisual-dir",
        type=Path,
        default=None,
        help="覆盖 GameVisual 目录（高级/测试用）",
    )
    parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def _default_library_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "color"


def _ask(prompt: str) -> str:
    """input() that survives closed stdin / Ctrl-C by returning empty."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt, OSError):
        return ""


def _pick_panel(
    probes: list[PanelInfo | ProbeIssue],
    library_names: list[str] | None = None,
    model: str | None = None,
) -> EdidInfo | None:
    """Return one panel's EdidInfo.

    Auto-picks when only one panel exists, or when exactly one of several
    panels has ICC files named ``{model}_..._{hwid}.icm`` in the bundled
    library — a model-specific match proves which panel is the internal
    one, so a double-click run finishes without keyboard input.
    """
    panels = [p for p in probes if isinstance(p, PanelInfo)]
    issues = [p for p in probes if isinstance(p, ProbeIssue)]
    for issue in issues:
        print(f"[检测提示] {issue.source}: {_detail_zh(issue.detail)}")
    unique_hwids: dict[str, EdidInfo] = {}
    for panel in panels:
        unique_hwids.setdefault(panel.info.hardware_id, panel.info)
        print(f"发现面板: {panel.pnp_name}  厂商={panel.info.vendor}  硬件ID={panel.info.hardware_id}")
    if not unique_hwids:
        return None
    if len(unique_hwids) == 1:
        return next(iter(unique_hwids.values()))
    # several distinct panels: a model-prefixed library hit is the only
    # trustworthy signal — other models' icm files prove nothing
    if library_names and model:
        prefix = f"{model}_"
        matched = [
            (hwid, info)
            for hwid, info in unique_hwids.items()
            if any(n.startswith(prefix) and hwid in n for n in library_names)
        ]
        if len(matched) == 1:
            hwid, info = matched[0]
            print(f"ICC 库中存在 {model} 专属文件（硬件 ID {hwid}），自动选用该面板。")
            return info
    ordered = list(unique_hwids.items())
    print("检测到多个面板，且无法自动判断哪个是笔记本内屏:")
    for idx, (_hwid, info) in enumerate(ordered, start=1):
        print(f"  {idx}. 厂商={info.vendor}  硬件ID={info.hardware_id}（产品号 {info.product_code}）")
    raw = _ask(f"请选笔记本内屏对应的序号 [1-{len(ordered)}，直接回车=1]: ")
    choice = int(raw) - 1 if raw.isdigit() and raw != "0" else 0
    return ordered[choice][1]


def _resolve_model(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    found = board_product()
    if isinstance(found, ProbeIssue):
        print(f"[检测提示] 机型: {_detail_zh(found.detail)}")
        manual = _ask("请手动输入机型型号（如 FX507ZM）: ")
        return manual or None
    print(f"机型: {found}")
    return found


def _print_plan(plan: FixPlan) -> None:
    print(f"共 {len(plan.actions)} 项操作:")
    for action in plan.actions:
        extra = "（同时复制到系统色彩目录）" if action.extra_dst_dir else ""
        print(f"  复制 {action.src_dir}/{action.src_name}")
        print(f"    -> {action.dst_file}{extra}")
        print(f"    原因: {_reason_zh(action.reason)}")


def _ensure_console_output() -> None:
    """重定向/非中文代码页环境下避免中文输出直接崩溃（尽力而为）。"""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower()
        if enc and enc not in ("utf-8", "utf8") and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns process exit code."""
    _ensure_console_output()
    if not is_windows():
        print("本工具只能在 Windows 上运行。")
        return 2
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return _run(args)
    except Exception:  # noqa: BROAD_EXCEPT_OK — single top-level boundary
        print("程序出现意外错误:", file=sys.stderr)
        import traceback  # noqa: PLC0415

        traceback.print_exc()
        print("请把上面的报错截图发给作者（邮箱见 README「问题反馈」）。", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    print("==== GameVisual 修复工具 v2 ====")
    print("本工具会自动检测屏幕与机型，并把正确的 ICC 配置复制到奥创目录。")
    print()
    print("第 1 步 / 共 3 步: 检测屏幕与机型")
    print("-" * 46)
    probes = list_panels()
    library_dir = (args.library or _default_library_dir()).resolve()
    library_names = sorted(p.name for p in library_dir.iterdir()) if library_dir.is_dir() else []
    model = _resolve_model(args.model)
    if model is None:
        print("缺少机型型号，无法命名配置文件，已退出。")
        return 1
    expected = args.panel_hwid.upper() if args.panel_hwid else None
    if expected is None:
        picked = _pick_panel(probes, library_names, model)
        if picked is None:
            print("未检测到屏幕 EDID，无法继续。")
            print("请确认: 本工具要在笔记本本机直接双击运行（不要在远程桌面里跑）。")
            print("仍失败的话，可用 --panel-hwid 手动指定 8 位硬件 ID（见 README）。")
            return 1
        expected_info = picked
        print(f"已自动识别目标面板: {expected_info.hardware_id}")
    else:
        expected_info = EdidInfo(vendor="?", product_code=expected[-4:], hardware_id=expected)
        print(f"使用手动指定的面板硬件 ID: {expected_info.hardware_id}")

    gv_dir = args.gamevisual_dir.resolve() if args.gamevisual_dir else DEFAULT_GAMEVISUAL_DIR
    system_names = sorted(p.name for p in gv_dir.iterdir()) if gv_dir.is_dir() else []

    print()
    print("第 2 步 / 共 3 步: 生成修复计划")
    print("-" * 46)
    plan = build_plan(
        model, expected_info.hardware_id, expected_info.product_code, library_names, system_names
    )
    _print_plan(plan)
    if not plan.actions:
        print()
        print("没有需要复制的文件: 本机已有匹配的配置（或 ICC 库里没有你的面板）。")
        print("若 GameVisual 仍然不可用:")
        print("  1. 看仓库 compressed/ 里有没有你机型的压缩包;")
        print("  2. 或按 README「贡献你的 ICC 文件」一节提交你的面板文件。")
        return 0
    if args.dry_run:
        print()
        print("试运行结束: 以上为将要执行的操作，本次未修改任何文件。")
        return 0

    if args.ask:
        answer = _ask("确认执行修复? [直接回车=确认，输入 n=取消]: ").lower()
        if answer.startswith("n"):
            print("已取消，未修改任何文件。")
            return 0

    print()
    print("第 3 步 / 共 3 步: 备份并修复（无需你操作）")
    print("-" * 46)
    if not is_admin():
        print("需要管理员权限: 正在弹出 UAC 窗口，请在弹窗中点「是」。")
        if try_elevate([*sys.argv[1:], "--yes"] if args.yes else [*sys.argv[1:]]):
            print("已在新窗口继续修复，本窗口可以直接关闭。")
            return 0
        print("[提示] 未获得授权，尝试直接写入（可能失败）...")

    report: AppliedReport = apply(plan, gv_dir, library_dir, DEFAULT_SPOOL_DIR)
    print()
    print("=" * 46)
    print(f"  修复完成! 已复制 {report.copied} 个文件，跳过 {report.skipped} 个。")
    if report.backup_path is not None:
        print(f"  修改前的完整备份: {report.backup_path}")
    print("=" * 46)
    print(NEXT_STEPS)
    return 0
