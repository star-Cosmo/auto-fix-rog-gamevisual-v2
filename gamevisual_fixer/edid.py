"""EDID parsing: derive the ASUS GameVisual ICC filename id from raw EDID bytes.

Naming rule verified against five panel vendors (BOE/AUO/LGD/CMN/CSW):

    hardware_id = hex(edid[9]) hex(edid[8]) hex(edid[11]) hex(edid[10])

Example (real FX507ZM unit): edid[8..11] = 0E 77 0F 15 -> "770E150F".
"""

from __future__ import annotations

from dataclasses import dataclass

_MIN_EDID_LEN = 13
# Chromaticity block spans byte 0x17 (gamma) and 0x19..0x21 (xy coords).
_ICC_START = 0x17
_ICC_END = 0x22  # exclusive


class EdidError(Exception):
    """Raw EDID bytes cannot be parsed."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Chromaticity:
    """Panel colourimetry decoded from the EDID chromaticity block.

    xy coordinates are 0..1; ``gamma`` is the transfer function exponent.
    These are the raw materials for generating a minimal ICC profile.
    """

    red_x: float
    red_y: float
    green_x: float
    green_y: float
    blue_x: float
    blue_y: float
    white_x: float
    white_y: float
    gamma: float


@dataclass(frozen=True, slots=True)
class EdidInfo:
    """Decoded identification data of one display panel."""

    vendor: str
    product_code: str
    hardware_id: str
    chromaticity: Chromaticity | None = None


def _parse_chromaticity(raw: bytes) -> Chromaticity | None:
    """Decode bytes 0x17..0x21 into Chromaticity; None when block is missing."""
    if len(raw) < _ICC_END:
        return None
    gamma_byte = raw[_ICC_START]
    gamma = 2.2 if gamma_byte == 0xFF else (gamma_byte + 100) / 100.0
    low = raw[0x19]
    red_x = ((raw[0x1A] << 2) | ((low >> 6) & 0x3)) / 1024.0
    red_y = ((raw[0x1B] << 2) | ((low >> 4) & 0x3)) / 1024.0
    green_x = ((raw[0x1C] << 2) | ((low >> 2) & 0x3)) / 1024.0
    green_y = ((raw[0x1D] << 2) | (low & 0x3)) / 1024.0
    # Blue/white primaries are 8-bit precision in the EDID block.
    blue_x = raw[0x1E] / 256.0
    blue_y = raw[0x1F] / 256.0
    white_x = raw[0x20] / 256.0
    white_y = raw[0x21] / 256.0
    return Chromaticity(
        red_x=red_x, red_y=red_y,
        green_x=green_x, green_y=green_y,
        blue_x=blue_x, blue_y=blue_y,
        white_x=white_x, white_y=white_y,
        gamma=gamma,
    )


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
    return EdidInfo(
        vendor=vendor,
        product_code=product_code,
        hardware_id=hardware_id,
        chromaticity=_parse_chromaticity(raw),
    )


def pnp_name(info: EdidInfo) -> str:
    """Reconstruct the Windows PnP display name, e.g. ``CSW150F``."""
    return f"{info.vendor}{info.product_code}"
