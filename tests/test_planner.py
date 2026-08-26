"""Unit tests for plan building — pure filename lists, no filesystem."""

from gamevisual_fixer.planner import build_plan

LIBRARY = [
    "GU604VY_10DE_E5090B74.icm",
    "GU604VY_8086_E5090B74.icm",
    "GU604VY_8086_E5090B74_CMDEF.icm",
    "GX650PY_1002_B8511603_CMDEF.icm",
    "ASUS_DCIP3.icm",
    "ASUS_DisplayP3.icm",
    "ASUS_sRGB.icm",
    "readme.txt",
]

SYSTEM = [
    "FX507ZM_8086_6F0E0B74.icm",
    "FX507ZM_10DE_6F0E0B74.icm",
    "ASUS_sRGB.icm",
]


def _dst_files(plan):  # type: ignore[no-untyped-def]
    return [action.dst_file for action in plan.actions]


def test_library_match_renames_model_and_routes_cmdef() -> None:
    """Given bundled profiles for the same panel id, When planned, Then renamed to host model and CMDEF also goes to spool."""
    plan = build_plan("FX507ZM", "E5090B74", "0B74", LIBRARY, SYSTEM)
    dsts = _dst_files(plan)
    assert "FX507ZM_10DE_E5090B74.icm" in dsts
    assert "FX507ZM_8086_E5090B74.icm" in dsts
    cmdef_actions = [a for a in plan.actions if a.dst_file == "FX507ZM_8086_E5090B74_CMDEF.icm"]
    assert len(cmdef_actions) == 1
    assert cmdef_actions[0].extra_dst_dir == "spool"
    # different monitor_part must NOT be picked up even though CMDEF matches shape
    assert all("B8511603" not in d for d in dsts)


def test_misnamed_system_file_is_repaired() -> None:
    """Given only misnamed system files (wrong vendor prefix), When planned, Then corrected-name copy emitted from that file."""
    plan = build_plan("FX507ZM", "770E150F", "150F", [], ["FX507ZM_8086_6F0E150F.icm"])
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.src_dir == "system"
    assert action.src_name == "FX507ZM_8086_6F0E150F.icm"
    assert action.dst_file == "FX507ZM_8086_770E150F.icm"


def test_gamut_trio_added_only_when_missing() -> None:
    """Given gamut files bundled and one already on system, When planned, Then only missing ones are copied."""
    plan = build_plan("FX507ZM", "E5090B74", "0B74", LIBRARY, SYSTEM)
    gamut_dsts = [d for d in _dst_files(plan) if d.startswith("ASUS_")]
    assert sorted(gamut_dsts) == ["ASUS_DCIP3.icm", "ASUS_DisplayP3.icm"]


def test_no_match_yields_empty_plan() -> None:
    """Given library without this panel, When planned, Then no actions at all."""
    plan = build_plan("FX507ZM", "99999999", "9999", LIBRARY, SYSTEM)
    assert plan.actions == ()


def test_shapes_without_gpu_segment_are_ignored() -> None:
    """Given non-icm or malformed names in inputs, When planned, Then they never produce actions."""
    plan = build_plan(
        "FX507ZM",
        "770E150F",
        "150F",
        ["ASUS_sRGB.icm", "random.icm", "A_B_C_D.icm"],
        ["notanicm.txt"],
    )
    for action in plan.actions:
        assert action.reason != ""
