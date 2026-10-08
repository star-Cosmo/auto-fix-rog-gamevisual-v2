"""Generate a minimal valid ICC v2 display profile from panel chromaticity.

The bundled ``color/`` library cannot cover every panel ever made; when no
profile matches, the EDID chromaticity block (primaries + white point +
gamma) is enough material to synthesise a *functional* ICC profile that
Armoury Crate accepts — GameVisual works again, with colourimetry close to
the panel's physical characteristics (not factory-calibrated, but usable).

Structure follows the community-verified minimal v2 matrix profile layout
(confirmed against Microsoft's Compact-ICC-Profiles micro binaries and the
Hydrus pure-Python generator):

    header(128) + tag_table + data
    9 tags: desc, cprt, wtpt, rXYZ, gXYZ, bXYZ, rTRC, gTRC, bTRC

Pure standard library (``struct`` only), zero third-party dependencies.

Reference: ICC.1:2001-04 spec v2, VESA EDID 1.4 chromaticity block.
"""

from __future__ import annotations

import struct
from typing import Final

from .edid import Chromaticity

_PROFILE_CLASS_MNTR: Final = b"mntr"
_COLOR_SPACE_RGB: Final = b"RGB "
_PCS_XYZ: Final = b"XYZ "
_ACSP: Final = b"acsp"
_CMM_LCMS: Final = b"lcms"  # LittleCMS tag: widest compatibility
_PLATFORM_MSFT: Final = b"MSFT"
_CREATOR_NONE: Final = b"none"
_VERSION: Final = b"\x02\x10\x00\x00"  # ICC v2.1

# PCS illuminant is always D50 in the header, regardless of device white.
_D50_ILLUMINANT: Final = (0xF6D6, 0x10000, 0xD32D)  # (0.9642, 1.0, 0.8249)

_TAG_RGB: Final = (b"rXYZ", b"gXYZ", b"bXYZ")
_TAG_TRC: Final = (b"rTRC", b"gTRC", b"bTRC")
_TAG_WHITE: Final = b"wtpt"
_TAG_DESC: Final = b"desc"
_TAG_CPRT: Final = b"cprt"

_HEADER_SIZE = 128
_TAG_SIZE = 12
_XYZ_TYPE_HEADER = 8  # 'XYZ ' type + 4 reserved bytes, then 12 bytes data
_XYZ_TAG_SIZE = 20
_CURV_TAG_SIZE = 16  # 'curv' + reserved + count(1) + gamma u8Fixed8 + pad


def _fix1616(value: float) -> int:
    """Convert a float to ICC 16.16 fixed point (rounds to nearest)."""
    return int(value * 65536.0 + 0.5)


def _u8f8(value: float) -> int:
    """Convert a float (0..~4) to ICC u8Fixed8Number (byte + fraction)."""
    return int(round(value * 256.0)) & 0xFFFF


def _solve3x3(
    a: tuple[tuple[float, float, float], ...], b: tuple[float, float, float]
) -> tuple[float, float, float] | None:
    """Solve ``a @ x == b`` by Gaussian elimination; None when singular."""
    aug = [
        [a[0][0], a[0][1], a[0][2], b[0]],
        [a[1][0], a[1][1], a[1][2], b[1]],
        [a[2][0], a[2][1], a[2][2], b[2]],
    ]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        inv = 1.0 / aug[col][col]
        for r in range(col + 1, 3):
            factor = aug[r][col] * inv
            for c in range(col, 4):
                aug[r][c] -= factor * aug[col][c]
    x = [0.0, 0.0, 0.0]
    for row in range(2, -1, -1):
        s = aug[row][3] - sum(aug[row][c] * x[c] for c in range(row + 1, 3))
        x[row] = s / aug[row][row]
    return x[0], x[1], x[2]


def _valid_xy(p: tuple[float, float]) -> bool:
    """A sane chromaticity coordinate: strictly inside the 0..1 square, x+y<1."""
    return 0.0 < p[0] < 1.0 and 0.0 < p[1] < 1.0 and p[0] + p[1] < 1.0


# sRGB primaries + D65 white — the safe fallback for corrupt/absent EDID data.
_SRGB_PRIMARIES: Final = ((0.64, 0.33), (0.30, 0.60), (0.15, 0.06))
_SRGB_WHITE: Final = (0.3127, 0.3290)


def _resolved_primaries(
    ch: Chromaticity,
) -> tuple[tuple[tuple[float, float], ...], tuple[float, float]]:
    """Return (primaries, white) after validating; falls back to sRGB when
    the EDID chromaticity block is missing or corrupt."""
    primaries = (
        (ch.red_x, ch.red_y),
        (ch.green_x, ch.green_y),
        (ch.blue_x, ch.blue_y),
    )
    white = (ch.white_x, ch.white_y)
    if (
        _valid_xy(white)
        and all(_valid_xy(p) for p in primaries)
        and 0.5 <= ch.gamma <= 3.5
    ):
        return primaries, white
    return _SRGB_PRIMARIES, _SRGB_WHITE


def _primaries_xyz(
    ch: Chromaticity,
) -> tuple[tuple[tuple[float, float, float], ...], tuple[float, float, float]]:
    """Convert xy primaries+white into the three XYZ *columns* of the
    RGB->XYZ matrix, normalised so white maps to Y=1.

    Each primary (x, y) with unknown Y satisfies:
        X = x/y * Y, Z = (1-x-y)/y * Y
    and the white constraint couples the three Y's:
        Yr + Yg + Yb = 1
        (xr/yr)Yr + (xg/yg)Yg + (xb/yb)Yb = xw/yw
        (zr/yr)Yr + (zg/yg)Yg + (zb/yb)Yb = zw/yw
    Solved with Gaussian elimination; invalid EDID data falls back to sRGB.
    Returns (rgb_columns, white_xyz) so callers need no separate fallback.
    """
    primaries, white = _resolved_primaries(ch)

    def _x(p: tuple[float, float]) -> float:
        return p[0] / p[1]

    def _z(p: tuple[float, float]) -> float:
        return (1.0 - p[0] - p[1]) / p[1]

    a = (
        (1.0, 1.0, 1.0),
        (_x(primaries[0]), _x(primaries[1]), _x(primaries[2])),
        (_z(primaries[0]), _z(primaries[1]), _z(primaries[2])),
    )
    solved = _solve3x3(a, (1.0, _x(white), _z(white)))
    if solved is None:
        primaries, white = _SRGB_PRIMARIES, _SRGB_WHITE
        a = (
            (1.0, 1.0, 1.0),
            (_x(primaries[0]), _x(primaries[1]), _x(primaries[2])),
            (_z(primaries[0]), _z(primaries[1]), _z(primaries[2])),
        )
        solved = _solve3x3(a, (1.0, _x(white), _z(white)))
    assert solved is not None
    y_r, y_g, y_b = solved

    def _col(p: tuple[float, float], y: float) -> tuple[float, float, float]:
        return (p[0] / p[1] * y, y, (1.0 - p[0] - p[1]) / p[1] * y)

    cols = (_col(primaries[0], y_r), _col(primaries[1], y_g), _col(primaries[2], y_b))
    white_xyz = (_x(white), 1.0, _z(white))
    return cols, white_xyz


def _build_desc(description: str) -> bytes:
    """textDescriptionType: 'desc' + reserved + uint32 count + ASCII text.

    The full v2 type also has Unicode and ScriptCode sections; the
    community-verified minimal profiles (Compact-ICC micro, Hydrus) omit
    them and Windows/lcms accept the ASCII-only form.
    """
    ascii_str = description.encode("ascii", errors="replace")
    payload = b"desc" + b"\x00\x00\x00\x00" + struct.pack(">I", len(ascii_str)) + ascii_str
    pad_to = -(-len(payload) // 4) * 4
    return payload + b"\x00" * (pad_to - len(payload))


def _build_cprt(text: str) -> bytes:
    """textType: 'text' + reserved + uint32 count + ASCII text."""
    ascii_str = text.encode("ascii", errors="replace")
    payload = b"text" + b"\x00\x00\x00\x00" + struct.pack(">I", len(ascii_str)) + ascii_str
    pad_to = -(-len(payload) // 4) * 4
    return payload + b"\x00" * (pad_to - len(payload))


def _build_curv_gamma(gamma: float) -> bytes:
    """curveType with a single gamma entry: 'curv' + reserved + count=1 + u8Fixed8."""
    payload = (
        b"curv"
        + b"\x00\x00\x00\x00"
        + struct.pack(">I", 1)
        + struct.pack(">H", _u8f8(gamma))
    )
    pad_to = -(-len(payload) // 4) * 4
    return payload + b"\x00" * (pad_to - len(payload))


def build_icc(
    ch: Chromaticity,
    description: str = "ASUS GameVisual Generated Profile",
    copyright: str = "GPL-3.0, generated from EDID chromaticity",
) -> bytes:
    """Return a complete ICC v2 profile for the given panel chromaticity.

    Contains the eight colourimetry tags required for a matrix display
    profile (rXYZ/gXYZ/bXYZ/wtpt + rTRC/gTRC/bTRC) plus desc and cprt.
    TRC tags share one gamma curve (all three channels use the EDID gamma).
    """
    rgb_cols, white_xyz = _primaries_xyz(ch)
    gamma = ch.gamma if 0.5 <= ch.gamma <= 3.5 else 2.2

    desc_payload = _build_desc(description)
    cprt_payload = _build_cprt(copyright)
    curv_payload = _build_curv_gamma(gamma)

    # tag table layout; XYZ tags 20B, curv tags 16B; desc/cprt variable
    tags = [
        (_TAG_DESC, desc_payload),
        (_TAG_CPRT, cprt_payload),
        (_TAG_WHITE, None, white_xyz),
        (_TAG_RGB[0], None, rgb_cols[0]),
        (_TAG_RGB[1], None, rgb_cols[1]),
        (_TAG_RGB[2], None, rgb_cols[2]),
        (_TAG_TRC[0], curv_payload),
        (_TAG_TRC[1], curv_payload),
        (_TAG_TRC[2], curv_payload),
    ]

    tag_count = len(tags)
    # compute data offsets sequentially
    cursor = _HEADER_SIZE + 4 + tag_count * _TAG_SIZE  # 232, 4-aligned
    offsets: dict[int, int] = {}
    for idx, entry in enumerate(tags):
        sig, *rest = entry
        payload = rest[0] if rest[0] is not None else None
        if payload is not None:
            offsets[idx] = cursor
            cursor += len(payload)
        else:
            offsets[idx] = cursor
            cursor += _XYZ_TAG_SIZE
    profile_size = cursor

    header = bytearray(_HEADER_SIZE)
    struct.pack_into(">I", header, 0, profile_size)          # 0  profile size
    struct.pack_into(">4s", header, 4, _CMM_LCMS)            # 4  preferred CMM type
    struct.pack_into(">4s", header, 8, _VERSION)             # 8  profile version
    struct.pack_into(">4s", header, 12, _PROFILE_CLASS_MNTR)  # 12 class
    struct.pack_into(">4s", header, 16, _COLOR_SPACE_RGB)    # 16 colour space
    struct.pack_into(">4s", header, 20, _PCS_XYZ)            # 20 PCS
    struct.pack_into(">6H", header, 24, 2025, 1, 1, 0, 0, 0)  # 24 datetime (12 bytes)
    struct.pack_into(">4s", header, 36, _ACSP)               # 36 'acsp'
    struct.pack_into(">4s", header, 40, _PLATFORM_MSFT)      # 40 platform
    struct.pack_into(">I", header, 44, 0)                    # 44 flags
    struct.pack_into(">I", header, 48, 0)                    # 48 device manufacturer
    struct.pack_into(">I", header, 52, 0)                    # 52 device model
    struct.pack_into(">Q", header, 56, 0)                    # 56 device attributes (8 bytes)
    struct.pack_into(">I", header, 64, 0)                    # 64 rendering intent
    struct.pack_into(">III", header, 68, *_D50_ILLUMINANT)   # 68 PCS illuminant (D50)
    struct.pack_into(">4s", header, 80, _CREATOR_NONE)       # 80 creator
    # 84..99 profile ID (16 bytes, zero), 100..127 reserved — already zero.

    tag_table = struct.pack(">I", tag_count)
    for idx, entry in enumerate(tags):
        sig = entry[0]
        payload = entry[1]
        size = _XYZ_TAG_SIZE if payload is None else len(payload)
        tag_table += struct.pack(">4sII", sig, offsets[idx], size)

    data = b""
    for entry in tags:
        sig = entry[0]
        if sig in (_TAG_DESC, _TAG_CPRT, _TAG_TRC[0], _TAG_TRC[1], _TAG_TRC[2]):
            data += entry[1]
        else:
            # XYZType: 'XYZ ' + reserved + 3 x s15Fixed16 (signed, positive here)
            col = entry[2]
            data += b"XYZ " + b"\x00\x00\x00\x00"
            data += struct.pack(
                ">3i", _fix1616(col[0]), _fix1616(col[1]), _fix1616(col[2])
            )

    assert len(header) == _HEADER_SIZE, f"header {len(header)} != 128"
    return bytes(header) + tag_table + data