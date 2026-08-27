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
