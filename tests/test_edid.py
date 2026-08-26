"""Unit tests for EDID parsing against five real vendor fixtures."""

import pytest

from gamevisual_fixer.edid import EdidError, parse_edid


def _edif_with_id(edid_id: bytes) -> bytes:
    """Build minimal EDID bytes with the target id at offset 8..11."""
    return bytes(8) + edid_id + bytes(32)


VENDOR_FIXTURES = [
    # (bytes at edid[8..11], vendor, product_code, hardware_id/filename part)
    (bytes.fromhex("0E770F15"), "CSW", "150F", "770E150F"),  # real FX507ZM unit
    (bytes.fromhex("09E5070A"), "BOE", "0A07", "E5090A07"),
    (bytes.fromhex("06AFA2D2"), "AUO", "D2A2", "AF06D2A2"),
    (bytes.fromhex("30E46305"), "LGD", "0563", "E4300563"),
    (bytes.fromhex("0DAE3C15"), "CMN", "153C", "AE0D153C"),
]


@pytest.mark.parametrize(
    ("edid_id", "vendor", "product_code", "hardware_id"),
    VENDOR_FIXTURES,
)
def test_parse_vendor_fixtures(
    edid_id: bytes, vendor: str, product_code: str, hardware_id: str
) -> None:
    """Given raw EDID of a known panel, When parsed, Then fields match the verified convention."""
    info = parse_edid(_edif_with_id(edid_id))
    assert info.vendor == vendor
    assert info.product_code == product_code
    assert info.hardware_id == hardware_id


def test_short_edid_raises() -> None:
    """Given truncated EDID, When parsed, Then EdidError names the length problem."""
    with pytest.raises(EdidError) as excinfo:
        parse_edid(bytes(4))
    assert "too short" in excinfo.value.detail
