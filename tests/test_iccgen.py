"""Tests for the minimal ICC v2 generator (EDID chromaticity -> profile)."""

import struct

import pytest

from gamevisual_fixer.edid import Chromaticity
from gamevisual_fixer.iccgen import _primaries_xyz, build_icc

# Typical 15.6" notebook panel chromaticity (near-sRGB / CSW style).
_PANEL = Chromaticity(
    red_x=0.669, red_y=0.325,
    green_x=0.289, green_y=0.634,
    blue_x=0.147, blue_y=0.063,
    white_x=0.313, white_y=0.329,
    gamma=2.2,
)

_REQUIRED_SIGS = {b"rXYZ", b"gXYZ", b"bXYZ", b"wtpt", b"desc", b"cprt", b"rTRC", b"gTRC", b"bTRC"}


def _tag_table(icc: bytes) -> list[tuple[bytes, int, int]]:
    """Parse the ICC tag table into [(signature, offset, size), ...]."""
    tag_count = struct.unpack(">I", icc[128:132])[0]
    out = []
    off = 132
    for _ in range(tag_count):
        sig, toff, tsize = struct.unpack(">4sII", icc[off : off + 12])
        off += 12
        out.append((sig, toff, tsize))
    return out


def test_profile_shape() -> None:
    """Given panel chromaticity, When building a profile, Then it is a valid ICC v2 header."""
    icc = build_icc(_PANEL)
    assert len(icc) > 128
    assert icc[36:40] == b"acsp"
    assert icc[8:12] == b"\x02\x10\x00\x00"
    assert icc[12:16] == b"mntr"
    assert icc[16:20] == b"RGB "
    assert icc[20:24] == b"XYZ "
    assert struct.unpack(">I", icc[0:4])[0] == len(icc)


def test_all_required_tags_present() -> None:
    """Then every tag required for a matrix display profile exists."""
    icc = build_icc(_PANEL)
    sigs = {sig for sig, _off, _size in _tag_table(icc)}
    assert _REQUIRED_SIGS <= sigs


def test_tags_are_inside_file_and_4byte_aligned() -> None:
    """Then every tag offset is 4-byte aligned and fully inside the file."""
    icc = build_icc(_PANEL)
    for sig, toff, tsize in _tag_table(icc):
        assert toff % 4 == 0, f"{sig} not aligned"
        assert toff < len(icc)
        assert toff + tsize <= len(icc)


def test_xyz_tags_carry_type_header() -> None:
    """Then each XYZ tag starts with the 'XYZ ' type signature (20-byte payload)."""
    icc = build_icc(_PANEL)
    for sig, toff, tsize in _tag_table(icc):
        if sig in {b"rXYZ", b"gXYZ", b"bXYZ", b"wtpt"}:
            assert tsize == 20
            assert icc[toff : toff + 4] == b"XYZ "


def test_trc_tags_are_curv_gamma() -> None:
    """Then TRC tags are curveType and encode the panel gamma."""
    icc = build_icc(_PANEL)
    for sig, toff, tsize in _tag_table(icc):
        if sig in {b"rTRC", b"gTRC", b"bTRC"}:
            assert icc[toff : toff + 4] == b"curv"
            count = struct.unpack(">I", icc[toff + 8 : toff + 12])[0]
            assert count == 1  # single gamma value form


def test_white_point_y_is_1() -> None:
    """Then the wtpt tag's Y component is 1.0 (16.16 fixed point)."""
    icc = build_icc(_PANEL)
    for sig, toff, _tsize in _tag_table(icc):
        if sig == b"wtpt":
            x, y, z = struct.unpack(">3i", icc[toff + 8 : toff + 20])
            assert y == 0x00010000  # 1.0 in 16.16 fixed point
            return
    pytest.fail("wtpt tag missing")


def test_primaries_y_sum_to_1() -> None:
    """Given primaries + white, When computing the XYZ columns, Then the Y row sums to 1."""
    cols, _white = _primaries_xyz(_PANEL)
    y_sum = cols[0][1] + cols[1][1] + cols[2][1]
    assert abs(y_sum - 1.0) < 1e-6


def test_degenerate_chromaticity_falls_back_to_srgb() -> None:
    """Given a degenerate (zero-ish) chromaticity, When building, Then it still produces a valid profile."""
    bad = Chromaticity(
        red_x=0.0, red_y=0.0,
        green_x=0.0, green_y=0.0,
        blue_x=0.0, blue_y=0.0,
        white_x=0.0, white_y=0.0,
        gamma=2.2,
    )
    icc = build_icc(bad)
    assert icc[36:40] == b"acsp"
    assert struct.unpack(">I", icc[0:4])[0] == len(icc)


def test_header_platform_is_msft() -> None:
    """Then the header declares MSFT platform for broadest Windows compat."""
    icc = build_icc(_PANEL)
    assert icc[40:44] == b"MSFT"
    assert icc[4:8] == b"lcms"