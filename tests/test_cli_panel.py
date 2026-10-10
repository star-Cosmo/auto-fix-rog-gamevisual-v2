"""Tests for the smart panel picker in cli (regression: model-prefixed match)."""

from gamevisual_fixer.cli import _pick_panel, _reason_zh
from gamevisual_fixer.edid import EdidInfo
from gamevisual_fixer.sysprobe import PanelInfo


def _panel(hw: str, pnp: str) -> PanelInfo:
    return PanelInfo(pnp_name=pnp, info=EdidInfo(vendor=pnp[:3], product_code=hw[-4:], hardware_id=hw))


def test_single_panel_autopicked(capsys):
    probes = [_panel("770E150F", "CSW150F")]
    picked = _pick_panel(probes)
    assert picked is not None and picked.hardware_id == "770E150F"


def test_model_prefix_match_autopicks_internal(capsys):
    probes = [_panel("E5090A07", "BOE0A07"), _panel("770E150F", "CSW150F")]
    library = ["FA507RM_10DE_E5090A07.icm", "FX507ZM_10DE_770E150F.icm"]
    picked = _pick_panel(probes, library, model="FX507ZM")
    assert picked is not None and picked.hardware_id == "770E150F"
    assert "自动选用" in capsys.readouterr().out


def test_other_model_files_do_not_autopick(capsys):
    """外接屏的 icm（他机型前缀）不能当内屏证据——回归：曾错选 E5090A07。"""
    probes = [_panel("E5090A07", "BOE0A07"), _panel("770E150F", "CSW150F")]
    library = ["FA507RM_10DE_E5090A07.icm"]  # FA507RM != FX507ZM
    picked = _pick_panel(probes, library, model="FX507ZM")
    # 管道输入为空 → 默认选 1（第一个）
    assert picked is not None and picked.hardware_id == "E5090A07"
    assert "无法自动判断" in capsys.readouterr().out


def test_reason_zh_translates_known_and_misnamed():
    assert _reason_zh("bundled profile matches panel hardware id") == "ICC 库里有这个面板的文件，直接匹配"
    assert _reason_zh("repair misnamed id 6F0E150F -> 770E150F") == "修正错误命名的旧文件（6F0E150F -> 770E150F）"
    assert _reason_zh("unknown reason") == "unknown reason"


def test_offer_device_manager_opens_when_1(monkeypatch, tmp_path):
    """输入 1 -> 打开设备管理器并在日志记录「已为用户打开」."""
    import gamevisual_fixer.cli as cli
    from gamevisual_fixer.logger import RunLog

    opened: list[bool] = []
    monkeypatch.setattr(cli, "_ask", lambda *a, **k: "1")
    monkeypatch.setattr(cli, "_open_device_manager", lambda: opened.append(True) or True)
    log = RunLog(log_dir=tmp_path)
    cli._offer_device_manager(log)
    assert opened == [True]
    assert "已为用户打开" in log.finish().read_text(encoding="utf-8")


def test_offer_device_manager_skips_when_2(monkeypatch, tmp_path):
    """输入 2 -> 跳过打开，日志记录「用户跳过」."""
    import gamevisual_fixer.cli as cli
    from gamevisual_fixer.logger import RunLog

    monkeypatch.setattr(cli, "_ask", lambda *a, **k: "2")
    log = RunLog(log_dir=tmp_path)
    cli._offer_device_manager(log)
    assert "用户跳过" in log.finish().read_text(encoding="utf-8")


def test_child_log_target(monkeypatch, tmp_path):
    """_child_log_target 只在「提权子进程 + 父进程日志已存在」时返回路径."""
    import gamevisual_fixer.cli as cli
    from argparse import Namespace

    # 非提权 -> None
    assert cli._child_log_target(Namespace(elevated=False)) is None
    # 提权但无环境变量 -> None
    monkeypatch.delenv("GVFIX_LOG_FILE", raising=False)
    assert cli._child_log_target(Namespace(elevated=True)) is None
    # 提权 + 父日志存在 -> 返回该路径
    existing = tmp_path / "log.log"
    existing.write_text("x", encoding="utf-8")
    monkeypatch.setenv("GVFIX_LOG_FILE", str(existing))
    assert cli._child_log_target(Namespace(elevated=True)) == existing
    # 提权 + 指向不存在的文件 -> None
    monkeypatch.setenv("GVFIX_LOG_FILE", str(tmp_path / "nope.log"))
    assert cli._child_log_target(Namespace(elevated=True)) is None


def test_open_device_manager_uses_shelleexecute(monkeypatch):
    """修复后 _open_device_manager 走 ShellExecuteW（mmc.exe 需提权，Popen 会 740 失败）."""
    import ctypes

    import gamevisual_fixer.cli as cli

    calls: list[tuple] = []

    def fake_shell(hwnd, op, file, params, directory, show):  # noqa: A002
        calls.append((op, file, params))
        return 42  # > 32 = 成功

    monkeypatch.setattr(ctypes.windll.shell32, "ShellExecuteW", fake_shell)
    assert cli._open_device_manager() is True
    assert calls == [("open", "mmc.exe", "devmgmt.msc")]


def test_open_device_manager_false_when_denied(monkeypatch):
    """ShellExecuteW 返回 <=32（如 5=拒绝 / 1223=取消）时 _open_device_manager 返回 False."""
    import ctypes

    import gamevisual_fixer.cli as cli

    monkeypatch.setattr(ctypes.windll.shell32, "ShellExecuteW", lambda *a, **k: 5)
    assert cli._open_device_manager() is False


def test_wants_quit_markers():
    """识别 q/quit/exit/退出 为退出标记."""
    import gamevisual_fixer.cli as cli

    for raw in ("q", "Q", "quit", "exit", "退出"):
        assert cli._wants_quit(raw) is True
    for raw in ("1", "2", "", "yes", "开始"):
        assert cli._wants_quit(raw) is False


def test_offer_device_manager_quits_on_q(monkeypatch, tmp_path):
    """输入 q -> 抛 _UserQuit，退出且不做任何修改."""
    import pytest

    import gamevisual_fixer.cli as cli
    from gamevisual_fixer.logger import RunLog

    monkeypatch.setattr(cli, "_ask", lambda *a, **k: "q")
    log = RunLog(log_dir=tmp_path)
    with pytest.raises(cli._UserQuit):
        cli._offer_device_manager(log)


def test_exit_clean_logs_summary_and_returns_zero(tmp_path):
    """_exit_clean 打印退出提示、写入「用户主动退出」并返回 0."""
    import gamevisual_fixer.cli as cli
    from gamevisual_fixer.logger import RunLog

    log = RunLog(log_dir=tmp_path)
    assert cli._exit_clean(log) == 0
    assert log.path.exists()
    assert "用户主动退出" in log.path.read_text(encoding="utf-8")
