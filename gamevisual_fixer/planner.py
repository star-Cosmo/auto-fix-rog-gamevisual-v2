"""Build a copy plan from filename lists — pure logic, no I/O.

Fixes the upstream tool's substring false-positive bug: candidates are parsed
by exact ``_`` segments instead of ``filename.find(code)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

_GPU_SEGMENTS: Final[tuple[str, ...]] = ("8086", "10DE", "1002")
_CMDEF_SEGMENT: Final = "CMDEF"
_ICM_SUFFIX: Final = ".icm"

GAMUT_FILES: Final[tuple[str, ...]] = (
    "ASUS_DCIP3.icm",
    "ASUS_DisplayP3.icm",
    "ASUS_sRGB.icm",
)

SOURCE_LIBRARY: Final = "library"
SOURCE_SYSTEM: Final = "system"
EXTRA_SPOOL: Final = "spool"


@dataclass(frozen=True, slots=True)
class IcmName:
    """Parsed shape of an ASUS icm filename."""

    model: str
    gpu: str
    monitor_part: str
    cmdef: bool
    raw: str


@dataclass(frozen=True, slots=True)
class CopyAction:
    """One file to place into the GameVisual directory."""

    src_name: str
    src_dir: str  # SOURCE_LIBRARY or SOURCE_SYSTEM
    dst_file: str  # plain filename inside the GameVisual dir
    extra_dst_dir: str | None  # EXTRA_SPOOL when CMDEF must also reach spool dir
    reason: str


@dataclass(frozen=True, slots=True)
class FixPlan:
    """Ordered actions; empty means nothing to do."""

    actions: tuple[CopyAction, ...]


def parse_icm(name: str) -> IcmName | None:
    """Parse ``Model_Gpu_Monitor[_CMDEF].icm``; return None for other shapes."""
    if not name.lower().endswith(_ICM_SUFFIX):
        return None
    segments = name[: -len(_ICM_SUFFIX)].split("_")
    cmdef = bool(segments) and segments[-1] == _CMDEF_SEGMENT
    core = segments[:-1] if cmdef else segments
    if len(core) < 3 or core[1] not in _GPU_SEGMENTS:
        return None
    return IcmName(model=core[0], gpu=core[1], monitor_part=core[2], cmdef=cmdef, raw=name)


def _dst_name(model: str, icm: IcmName, monitor_part: str) -> str:
    """Target filename for a matched profile, preserving the CMDEF marker."""
    base = f"{model}_{icm.gpu}_{monitor_part}.icm"
    if icm.cmdef:
        return base.replace(_ICM_SUFFIX, f"_CMDEF{_ICM_SUFFIX}")
    return base


def build_plan(
    model: str,
    expected_hardware_id: str,
    expected_product_code: str,
    library_names: list[str],
    system_names: list[str],
) -> FixPlan:
    """Compute all copies needed so GameVisual finds this panel's profiles.

    When no profile matches the panel at all, the plan stays empty: gamut
    files alone cannot make GameVisual pass its validation.
    """
    actions: list[CopyAction] = []
    seen_dst: set[str] = set()
    matched_any = False

    def add(action: CopyAction) -> None:
        if action.dst_file not in seen_dst and action.dst_file not in system_names:
            seen_dst.add(action.dst_file)
            actions.append(action)

    # 1) bundled library matches (primary exact id, fallback by product code)
    for name in library_names:
        icm = parse_icm(name)
        if icm is None:
            continue
        if icm.monitor_part == expected_hardware_id:
            reason = "bundled profile matches panel hardware id"
        elif icm.monitor_part.endswith(expected_product_code):
            reason = "fallback: same panel product code, different vendor prefix"
        else:
            continue
        matched_any = True
        dst = _dst_name(model, icm, icm.monitor_part)
        add(
            CopyAction(
                src_name=name,
                src_dir=SOURCE_LIBRARY,
                dst_file=dst,
                extra_dst_dir=EXTRA_SPOOL if icm.cmdef else None,
                reason=reason,
            )
        )

    # 2) repair misnamed files already on the system (e.g. wrong vendor prefix)
    for name in system_names:
        icm = parse_icm(name)
        if icm is None or icm.model != model:
            continue
        if icm.monitor_part == expected_hardware_id:
            continue
        if not icm.monitor_part.endswith(expected_product_code):
            continue
        # repairing a wrong vendor prefix still covers the panel itself
        matched_any = True
        dst = _dst_name(model, icm, expected_hardware_id)
        add(
            CopyAction(
                src_name=name,
                src_dir=SOURCE_SYSTEM,
                dst_file=dst,
                extra_dst_dir=EXTRA_SPOOL if icm.cmdef else None,
                reason=f"repair misnamed id {icm.monitor_part} -> {expected_hardware_id}",
            )
        )

    # 3) gamut-switch trio when bundled but missing on system; only useful
    #    once the panel itself is covered, otherwise keep the plan empty
    if matched_any:
        system_set = set(system_names)
        for gamut in GAMUT_FILES:
            if gamut in library_names and gamut not in system_set:
                add(
                    CopyAction(
                        src_name=gamut,
                        src_dir=SOURCE_LIBRARY,
                        dst_file=gamut,
                        extra_dst_dir=None,
                        reason="gamut switch profile missing on system",
                    )
                )

    return FixPlan(actions=tuple(actions))
