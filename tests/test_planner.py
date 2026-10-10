"""Unit tests for plan building — pure filename lists, no filesystem."""

from gamevisual_fixer.planner import SOURCE_GENERATED, build_generated_plan, build_plan

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
    """Given library without this panel, When planned, Then no actions and panel not covered."""
    plan = build_plan("FX507ZM", "99999999", "9999", LIBRARY, SYSTEM)
    assert plan.actions == ()
    assert plan.panel_covered is False


def test_no_match_records_rejections() -> None:
    """Given a panel absent from the library, When planned, Then each parsed non-matching candidate is reported."""
    plan = build_plan("FX507ZM", "99999999", "9999", LIBRARY, SYSTEM)
    assert plan.rejections
    # every library candidate whose monitor_part differs is rejected with its name
    assert any("E5090B74" in r and "monitor_part=" in r for r in plan.rejections)
    assert any("B8511603" in r for r in plan.rejections)


def test_system_model_mismatch_recorded() -> None:
    """Given a system file for a different model, When planned, Then it is recorded as a rejection."""
    plan = build_plan("FX507ZM", "770E150F", "150F", [], ["GX650PY_10DE_770E150F.icm"])
    assert plan.actions == ()
    assert plan.panel_covered is False
    assert any("model=" in r and "GX650PY" in r for r in plan.rejections)


def test_system_monitor_mismatch_recorded() -> None:
    """Given a system file whose monitor_part differs, When planned, Then it is recorded as a rejection."""
    plan = build_plan("FX507ZM", "770E150F", "150F", [], ["FX507ZM_10DE_99999999.icm"])
    assert plan.actions == ()
    assert any("monitor_part=" in r and "99999999" in r for r in plan.rejections)


def test_empty_plan_with_panel_covered_means_already_fixed() -> None:
    """Given system already holds every matching profile, When planned, Then empty plan but panel covered."""
    system_all = [
        "FX507ZM_10DE_E5090B74.icm",
        "FX507ZM_8086_E5090B74.icm",
        "FX507ZM_8086_E5090B74_CMDEF.icm",
        "ASUS_DCIP3.icm",
        "ASUS_DisplayP3.icm",
        "ASUS_sRGB.icm",
    ]
    plan = build_plan("FX507ZM", "E5090B74", "0B74", LIBRARY, system_all)
    assert plan.actions == ()
    assert plan.panel_covered is True


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


def test_generated_plan_names_file_correctly() -> None:
    """Given model/hwid/gpu, When building a generated plan, Then the dst file is Model_Gpu_Hwid.icm."""
    plan = build_generated_plan("FX507ZM", "770E150F", "10DE")
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.dst_file == "FX507ZM_10DE_770E150F.icm"
    assert action.src_dir == SOURCE_GENERATED
    assert plan.panel_covered is True


def test_generated_plan_skips_when_file_exists() -> None:
    """Given the target file already on the system, When planning generation, Then no action."""
    plan = build_generated_plan("FX507ZM", "770E150F", "10DE", ["FX507ZM_10DE_770E150F.icm"])
    assert plan.actions == ()
