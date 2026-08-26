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

NEXT_STEPS: Final = """Next steps:
  1. Disconnect network (Wi-Fi off / unplug cable)
  2. Shut down the PC completely
  3. Power on, open Armoury Crate -> GameVisual"""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gamevisual_fixer",
        description="Repair ASUS Armoury Crate GameVisual after screen replacement.",
    )
    parser.add_argument("--dry-run", action="store_true", help="show plan without changing files")
    parser.add_argument("--yes", action="store_true", help="apply without confirmation prompt")
    parser.add_argument(
        "--library", type=Path, default=None, help="bundled ICC folder (default: <repo>/color)"
    )
    parser.add_argument("--model", default=None, help="override motherboard model, e.g. FX507ZM")
    parser.add_argument("--panel-hwid", default=None, help="override panel hardware id, e.g. 770E150F")
    parser.add_argument("--elevated", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args(argv)


def _default_library_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "color"


def _ask(prompt: str) -> str:
    """input() that survives closed stdin / Ctrl-C by returning empty."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _pick_panel(probes: list[PanelInfo | ProbeIssue]) -> EdidInfo | None:
    """Return one panel's EdidInfo; interactive choice when several exist."""
    panels = [p for p in probes if isinstance(p, PanelInfo)]
    issues = [p for p in probes if isinstance(p, ProbeIssue)]
    for issue in issues:
        print(f"[probe issue] {issue.source}: {issue.detail}")
    unique_hwids: dict[str, EdidInfo] = {}
    for panel in panels:
        unique_hwids.setdefault(panel.info.hardware_id, panel.info)
        print(f"panel found: {panel.pnp_name}  vendor={panel.info.vendor}  id={panel.info.hardware_id}")
    if not unique_hwids:
        return None
    if len(unique_hwids) == 1:
        return next(iter(unique_hwids.values()))
    ordered = list(unique_hwids.items())
    for idx, (_hwid, info) in enumerate(ordered, start=1):
        print(f"  {idx}. {info.vendor} id={info.hardware_id} ({info.product_code})")
    raw = _ask(f"Multiple panels detected, select [1-{len(ordered)}, default 1]: ")
    choice = int(raw) - 1 if raw.isdigit() and raw != "0" else 0
    return ordered[choice][1]


def _resolve_model(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    found = board_product()
    if isinstance(found, ProbeIssue):
        print(f"[probe issue] board: {found.detail}")
        manual = _ask("Enter motherboard model manually (e.g. FX507ZM): ")
        return manual or None
    print(f"board model: {found}")
    return found


def _print_plan(plan: FixPlan) -> None:
    print(f"\nplan: {len(plan.actions)} action(s)")
    for action in plan.actions:
        extra = "  (+ spool copy)" if action.extra_dst_dir else ""
        print(f"  COPY {action.src_dir}/{action.src_name}")
        print(f"    -> {action.dst_file}{extra}")
        print(f"    reason: {action.reason}")


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns process exit code."""
    if not is_windows():
        print("This tool only works on Windows.")
        return 2
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return _run(args)
    except Exception:  # noqa: BROAD_EXCEPT_OK — single top-level boundary
        print("unexpected failure:", file=sys.stderr)
        import traceback  # noqa: PLC0415

        traceback.print_exc()
        return 1


def _run(args: argparse.Namespace) -> int:
    probes = list_panels()
    expected = args.panel_hwid.upper() if args.panel_hwid else None
    if expected is None:
        picked = _pick_panel(probes)
        if picked is None:
            print("no display EDID found; nothing to do.")
            return 1
        expected_info = picked
    else:
        expected_info = EdidInfo(vendor="?", product_code=expected[-4:], hardware_id=expected)
    print(f"target panel hardware id: {expected_info.hardware_id}")

    model = _resolve_model(args.model)
    if model is None:
        print("a model name is required to name the profiles.")
        return 1

    library_dir = (args.library or _default_library_dir()).resolve()
    library_names = sorted(p.name for p in library_dir.iterdir()) if library_dir.is_dir() else []
    gv_dir = DEFAULT_GAMEVISUAL_DIR
    system_names = sorted(p.name for p in gv_dir.iterdir()) if gv_dir.is_dir() else []

    plan = build_plan(
        model, expected_info.hardware_id, expected_info.product_code, library_names, system_names
    )
    _print_plan(plan)
    if not plan.actions:
        print("\nnothing to copy: this machine already has matching profiles (or none exist).")
        print("if GameVisual still fails, check compressed/*.zip in this repo for your panel,")
        print("or contribute your ICC profile upstream.")
        return 0
    if args.dry_run:
        print("\ndry run complete; no files were changed.")
        return 0

    if not args.yes:
        answer = _ask("\nApply changes? [y/N]: ").lower()
        if not answer.startswith("y"):
            print("aborted by user; nothing was changed.")
            return 0

    if not is_admin():
        print("administrator rights required; launching elevated window...")
        if try_elevate([*sys.argv[1:], "--yes"] if args.yes else [*sys.argv[1:]]):
            print("elevated window started; continue there.")
            return 0
        print("[warn] elevation declined; attempting direct write (may fail)...")

    report: AppliedReport = apply(plan, gv_dir, library_dir, DEFAULT_SPOOL_DIR)
    print(f"\ndone. copied={report.copied} skipped={report.skipped}")
    if report.backup_path is not None:
        print(f"backup saved at: {report.backup_path}")
    print(NEXT_STEPS)
    return 0
