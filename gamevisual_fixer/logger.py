"""Run log: record every step to a timestamped file on the user's Desktop.

Two-tier logging:

- **常驻 tier** (``log`` / ``log_kv`` / ``detail`` / errors): step boundaries,
  key-value pairs, swallowed-exception details, decision rejections — always
  written, so a remote support request has the full "what happened" trail.
- **调试 tier** (``trace``): raw EDID bytes, per-file scan listings, registry
  paths — written only when ``debug=True`` **or** when the run failed. This
  keeps a successful run's log short while a failed run ships every detail.

Module-level bus (``activate`` / ``deactivate`` / ``detail`` / ``trace``) lets
the core I/O modules (``sysprobe`` / ``applier``) log without holding a
reference to the run log — a no-op when no run is active, so pure logic stays
unit-testable without mocking.

UAC two-process flow: the non-elevated parent writes its log and exposes the
path via the ``GVFIX_LOG_FILE`` environment variable before relaunching; the
elevated child builds ``RunLog(append_to=...)`` so **both processes share one
log file**.

File naming: ``GameVisual修复日志_YYYY-MM-DD_HHMMSS.log``
Encoding: UTF-8 with BOM (so Windows Notepad renders Chinese correctly).
"""

from __future__ import annotations

import os
import platform
import traceback
from datetime import datetime
from pathlib import Path
from typing import Final

_BOM: Final = "\ufeff"

# Module-level active run log; None until cli.main() activates one.
_active: "RunLog | None" = None


def activate(log: "RunLog") -> None:
    """Point the module-level bus at the active run log."""
    global _active
    _active = log


def deactivate() -> None:
    """Detach the active run log (no-op afterwards)."""
    global _active
    _active = None


def detail(text: str) -> None:
    """Always-on diagnostic line; no-op when no run is active."""
    if _active is not None:
        _active.detail(text)


def trace(text: str) -> None:
    """Debug-tier diagnostic line; no-op when no run is active."""
    if _active is not None:
        _active.trace(text)


class RunLog:
    """Append-only log that buffers tiers and flushes to Desktop on finish."""

    def __init__(
        self,
        *,
        debug: bool = False,
        append_to: Path | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self._lines: list[tuple[bool, str]] = []  # (is_debug, text)
        self._success: bool = True
        self._summary: str = ""
        self._debug = debug
        self._append_to = append_to
        # Build a timestamped filename up-front so it stays constant.
        self._stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._filename = f"GameVisual修复日志_{self._stamp}.log"
        # log_dir overrides the Desktop (used by tests); default = current user.
        self._desktop = log_dir if log_dir is not None else self._resolve_desktop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Target file path (the shared parent path in append mode)."""
        if self._append_to is not None:
            return self._append_to
        return self._desktop / self._filename

    @staticmethod
    def _resolve_desktop() -> Path:
        """Return the *current user's* Desktop path, even under UAC elevation."""
        # expanduser("~") always points to the logged-in user, not SYSTEM.
        return Path(os.path.expanduser("~")) / "Desktop"

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _add(self, text: str, is_debug: bool = False) -> None:
        self._lines.append((is_debug, text))

    # ------------------------------------------------------------------
    # Public API — call these from cli / sysprobe / applier
    # ------------------------------------------------------------------

    def log(self, text: str) -> None:
        """Append a plain line with a timestamp prefix (always tier)."""
        self._add(f"[{self._ts()}] {text}")

    def detail(self, text: str) -> None:
        """Append an indented always-on diagnostic line (decision / swallow)."""
        self._add(f"[{self._ts()}]     · {text}")

    def trace(self, text: str) -> None:
        """Append an indented debug-tier line (raw bytes / full listings)."""
        self._add(f"[{self._ts()}]     · [调试] {text}", is_debug=True)

    def log_kv(self, key: str, value: str) -> None:
        """Append an indented key-value pair (no extra timestamp)."""
        self._add(f"[{self._ts()}]   {key}: {value}")

    def log_section(self, title: str) -> None:
        """Append a visible section divider."""
        self._add("")
        self._add(f"[{self._ts()}] {'=' * 44}")
        self._add(f"[{self._ts()}]  {title}")
        self._add(f"[{self._ts()}] {'=' * 44}")

    def log_error(self, detail_text: str) -> None:
        """Append an error line (marks the run as failed)."""
        self._success = False
        self._add(f"[{self._ts()}] ✖ 错误: {detail_text}")

    def log_exception(self, exc: BaseException) -> None:
        """Append a full traceback (marks the run as failed)."""
        self._success = False
        self._add(f"[{self._ts()}] ✖ 未捕获异常:")
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
            self._add(line.rstrip())

    def set_summary(self, text: str) -> None:
        """Override the auto-generated summary line."""
        self._summary = text

    # ------------------------------------------------------------------
    # Rendering & flushing
    # ------------------------------------------------------------------

    def _rendered(self) -> str:
        """Join buffered lines; debug tier included on failure or debug mode."""
        include_debug = self._debug or not self._success
        lines = [text for is_dbg, text in self._lines if (not is_dbg) or include_debug]
        return "\n".join(lines)

    def flush(self) -> Path:
        """Write the current buffer WITHOUT the result section (pre-elevation).

        The elevated parent writes its steps before relaunching so the child
        can append to the same file; the result section is left to whoever
        finishes the run last.
        """
        text = f"{_BOM}{self._rendered()}\n"
        return self._write(text)

    def finish(self) -> Path:
        """Append the result section and write the log.

        In append mode the parent already wrote the BOM and its steps, so we
        append (no second BOM). Otherwise a fresh file is written.
        """
        self.log_section("执行结果")
        status = "成功" if self._success else "失败"
        self.log(f"  状态: {status}")
        if self._summary:
            self.log(f"  说明: {self._summary}")
        self.log(f"  运行环境: {platform.platform()} | Python {platform.python_version()}")
        self.log(f"  时间: {self._stamp}")

        content = self._rendered()
        if self._append_to is not None:
            try:
                self._append_to.parent.mkdir(parents=True, exist_ok=True)
                with self._append_to.open("a", encoding="utf-8") as fh:
                    fh.write("\n" + content + "\n")
                return self._append_to
            except OSError:
                pass  # fall through to a fresh standalone file
        return self._write(f"{_BOM}{content}\n")

    def _write(self, text: str) -> Path:
        """Write ``text`` to the Desktop, falling back next to this script."""
        path = self._desktop / self._filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return path
        except OSError:
            pass
        fallback = Path(__file__).resolve().parent.parent / self._filename
        fallback.write_text(text, encoding="utf-8")
        return fallback
