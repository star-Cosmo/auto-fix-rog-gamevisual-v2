"""EDID parsing: derive the ASUS GameVisual ICC filename id from raw EDID bytes.

Naming rule verified against five panel vendors (BOE/AUO/LGD/CMN/CSW):

    hardware_id = hex(edid[9]) hex(edid[8]) hex(edid[11]) hex(edid[10])

Example (real FX507ZM unit): edid[8..11] = 0E 77 0F 15 -> "770E150F".
"""

from __future__ import annotations

from dataclasses import dataclass

_MIN_EDID_LEN = 13


class EdidError(Exception):
    """Raw EDID bytes cannot be parsed."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class EdidInfo:
    """Decoded identification data of one display panel."""

    vendor: str
    product_code: str
    hardware_id: str


def parse_edid(raw: bytes) -> EdidInfo:
    """Parse raw EDID bytes into vendor/product/filename-id info."""
    if len(raw) < _MIN_EDID_LEN:
        raise EdidError(f"EDID too short: got {len(raw)} bytes, need >= {_MIN_EDID_LEN}")
    mfr_word: int = (raw[8] << 8) | raw[9]
    vendor = "".join(chr(65 - 1 + ((mfr_word >> shift) & 0x1F)) for shift in (10, 5, 0))
    # EDID stores the product code little-endian at bytes 10..11; the ASUS
    # filename shows the VALUE high-byte-first.
    product_word: int = (raw[11] << 8) | raw[10]
    product_code = f"{product_word:04X}"
    hardware_id = f"{raw[9]:02X}{raw[8]:02X}{raw[11]:02X}{raw[10]:02X}"
    return EdidInfo(vendor=vendor, product_code=product_code, hardware_id=hardware_id)


def pnp_name(info: EdidInfo) -> str:
    """Reconstruct the Windows PnP display name, e.g. ``CSW150F``."""
    return f"{info.vendor}{info.product_code}"
