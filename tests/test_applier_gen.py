"""Tests for applying plans that generate synthetic ICC files."""

import struct

from gamevisual_fixer.applier import apply
from gamevisual_fixer.edid import Chromaticity
from gamevisual_fixer.planner import build_generated_plan

_PANEL = Chromaticity(
    red_x=0.669, red_y=0.325,
    green_x=0.289, green_y=0.634,
    blue_x=0.147, blue_y=0.063,
    white_x=0.313, white_y=0.329,
    gamma=2.2,
)


def test_apply_generated_icc_writes_valid_profile(tmp_path) -> None:
    """Given a generated plan + chromaticity, When applying, Then a parseable ICC lands on disk."""
    gv = tmp_path / "GameVisual"
    plan = build_generated_plan("FX507ZM", "770E150F", "10DE")
    report = apply(plan, gv, tmp_path / "lib", tmp_path / "spool", chromaticity=_PANEL)
    assert report.copied == 1
    dst = gv / "FX507ZM_10DE_770E150F.icm"
    assert dst.is_file()
    raw = dst.read_bytes()
    assert raw[36:40] == b"acsp"
    assert struct.unpack(">I", raw[0:4])[0] == len(raw)
    # backup created alongside
    backups = list(tmp_path.glob("GameVisual_backup_*"))
    assert len(backups) == 1


def test_apply_generated_skips_existing_file(tmp_path) -> None:
    """Given the dst already exists, When applying, Then it is skipped, not overwritten."""
    gv = tmp_path / "GameVisual"
    gv.mkdir(parents=True)
    (gv / "FX507ZM_10DE_770E150F.icm").write_text("original", encoding="utf-8")
    plan = build_generated_plan("FX507ZM", "770E150F", "10DE")
    report = apply(plan, gv, tmp_path / "lib", tmp_path / "spool", chromaticity=_PANEL)
    assert report.skipped == 1
    assert report.copied == 0
    assert (gv / "FX507ZM_10DE_770E150F.icm").read_text(encoding="utf-8") == "original"


def test_apply_generated_requires_chromaticity(tmp_path) -> None:
    """Given a generated plan but no chromaticity, When applying, Then ApplyError is raised."""
    gv = tmp_path / "GameVisual"
    plan = build_generated_plan("FX507ZM", "770E150F", "10DE")
    try:
        apply(plan, gv, tmp_path / "lib", tmp_path / "spool", chromaticity=None)
        raise AssertionError("expected ApplyError")
    except Exception as exc:  # ApplyError
        assert "chromaticity" in str(exc)