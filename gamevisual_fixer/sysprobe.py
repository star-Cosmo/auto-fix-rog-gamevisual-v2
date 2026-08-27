"""Windows-only system probes: panels via registry EDID, board model, elevation.

Every probe returns typed values (``PanelInfo``/``ProbeIssue``) instead of
raising, so the CLI can render a complete report.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import re
import sys
from dataclasses import dataclass
from typing import Final

from .edid import EdidError, EdidInfo, parse_edid

_ENUM_DISPLAY: Final = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
_SYSTEM_INFO_KEY: Final = r"SYSTEM\CurrentControlSet\Control\SystemInformation"
_BIOS_KEY: Final = r"HARDWARE\DESCRIPTION\System\BIOS"

# ASUS model codes look like FX507ZM / GU603ZW / G733ZW / FA507RM.
_ASUS_MODEL_RE: Final = re.compile(r"\b[A-Z]{1,2}\d{3}[A-Z]{1,3}\b")


@dataclass(frozen=True, slots=True)
class PanelInfo:
    """One internal/external panel whose EDID parsed successfully."""

    pnp_name: str
    info: EdidInfo


@dataclass(frozen=True, slots=True)
class ProbeIssue:
    """A probe that could not be completed, reported instead of raised."""

    source: str
    detail: str


def is_windows() -> bool:
    """True when running on Windows."""
    return sys.platform == "win32"


def list_panels() -> list[PanelInfo | ProbeIssue]:
    """Enumerate displays under Enum\\DISPLAY and decode each EDID."""
    if not is_windows():
        return [ProbeIssue(source="panels", detail="not running on Windows")]
    import winreg  # noqa: PLC0415 — stdlib import kept local for cross-platform import

    results: list[PanelInfo | ProbeIssue] = []
    seen_pnp: set[str] = set()
    try:
        display_root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _ENUM_DISPLAY)
    except OSError as exc:
        return [ProbeIssue(source="panels", detail=f"cannot open {_ENUM_DISPLAY}: {exc}")]
    with display_root:
        pnp_index = 0
        while True:
            try:
                pnp_name = winreg.EnumKey(display_root, pnp_index)
            except OSError:
                break
            pnp_index += 1
            panel = _read_panel_edid(pnp_name)
            if isinstance(panel, PanelInfo) and panel.pnp_name in seen_pnp:
                continue
            if isinstance(panel, PanelInfo):
                seen_pnp.add(panel.pnp_name)
            results.append(panel)
    return results


def _read_panel_edid(pnp_name: str) -> PanelInfo | ProbeIssue:
    """Read+parse one panel's EDID from its first instance that has one."""
    import winreg  # noqa: PLC0415

    base = f"{_ENUM_DISPLAY}\\{pnp_name}"
    try:
        instance_root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError as exc:
        return ProbeIssue(source=pnp_name, detail=f"cannot open instance key: {exc}")
    with instance_root:
        instance_index = 0
        while True:
            try:
                instance = winreg.EnumKey(instance_root, instance_index)
            except OSError:
                break
            instance_index += 1
            params_path = f"{base}\\{instance}\\Device Parameters"
            raw = _query_binary(params_path, "EDID")
            if raw is None:
                continue
            try:
                return PanelInfo(pnp_name=pnp_name, info=parse_edid(raw))
            except EdidError as exc:
                return ProbeIssue(source=pnp_name, detail=exc.detail)
    return ProbeIssue(source=pnp_name, detail="no instance exposes an EDID value")


def _query_binary(key_path: str, value_name: str) -> bytes | None:
    """Read a REG_BINARY value; None when absent."""
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, value_type = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    if value_type != winreg.REG_BINARY or not isinstance(value, bytes):
        return None
    return value


def _query_str(key_path: str, value_name: str) -> str | None:
    """Read a REG_SZ value; None when absent."""
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, value_type = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    if value_type != winreg.REG_SZ or not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _extract_model(raw: str) -> str | None:
    """Pull the clean ASUS model code out of a marketing string."""
    match = _ASUS_MODEL_RE.search(raw.upper())
    return match.group(0) if match else None


def board_product() -> str | ProbeIssue:
    """Motherboard/system model as a clean code, e.g. ``FX507ZM``.

    Registry often stores marketing names like ``ASUS TUF Gaming F15
    FX507ZM_FX507ZM``; the model code is extracted from each candidate.
    """
    sources = (
        (_BIOS_KEY, "BaseBoardProduct"),
        (_SYSTEM_INFO_KEY, "SystemProductName"),
    )
    fallback_raw: str | None = None
    for path, name in sources:
        raw = _query_str(path, name) if is_windows() else None
        if raw is None:
            continue
        extracted = _extract_model(raw)
        if extracted is not None:
            return extracted
        if fallback_raw is None:
            fallback_raw = raw
    if fallback_raw is not None:
        return fallback_raw
    detail = "BaseBoardProduct/SystemProductName not found in registry"
    return ProbeIssue(source="board", detail=detail)


def is_admin() -> bool:
    """True when the current process has administrator rights."""
    if not is_windows():
        return False
    return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]


def try_elevate(script_args: list[str]) -> bool:
    """Relaunch self elevated; True when a UAC launch was started.

    The elevated process is wrapped in ``cmd /k`` so the console window
    stays open after the fix finishes — otherwise non-technical users
    never see the result (or the disconnect-network instructions) before
    the window closes.
    """
    if not is_windows():
        return False
    script = sys.argv[0]
    params = " ".join([f'"{script}"', *script_args, "--elevated"])
    cmd = f'/k "{sys.executable}" {params}'
    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None, "runas", "cmd.exe", cmd, None, 1
    )
    return int(result) > 32
