"""Run log: record every step to a timestamped file on the user's Desktop.

Helps diagnose issues when remote users share the log back.  Each run
creates a new file; previous runs are never overwritten.

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


class RunLog:
    """Append-only in-memory log that flushes to Desktop on :meth:`finish`."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._success: bool = True
        self._summary: str = ""
        # Build a timestamped filename up-front so it stays constant
        self._stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._filename = f"GameVisual修复日志_{self._stamp}.log"
        # Current user's Desktop (resolves correctly under UAC elevation)
        self._desktop = self._resolve_desktop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_desktop() -> Path:
        """Return the *current user's* Desktop path, even under UAC elevation."""
        # expanduser("~") always points to the logged-in user, not SYSTEM.
        return Path(os.path.expanduser("~")) / "Desktop"

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ------------------------------------------------------------------
    # Public API — call these from cli / applier
    # ------------------------------------------------------------------

    def log(self, text: str) -> None:
        """Append a plain text line with a timestamp prefix."""
        self._lines.append(f"[{self._ts()}] {text}")

    def log_kv(self, key: str, value: str) -> None:
        """Append a indented key-value pair (no extra timestamp)."""
        self._lines.append(f"[{self._ts()}]   {key}: {value}")

    def log_section(self, title: str) -> None:
        """Append a visible section divider."""
        self._lines.append("")
        self._lines.append(f"[{self._ts()}] {'=' * 44}")
        self._lines.append(f"[{self._ts()}]  {title}")
        self._lines.append(f"[{self._ts()}] {'=' * 44}")

    def log_error(self, detail: str) -> None:
        """Append an error line (sets the run as failed)."""
        self._success = False
        self._lines.append(f"[{self._ts()}] ✖ 错误: {detail}")

    def log_exception(self, exc: BaseException) -> None:
        """Append a full traceback (sets the run as failed)."""
        self._success = False
        self._lines.append(f"[{self._ts()}] ✖ 未捕获异常:")
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
            self._lines.append(line.rstrip())

    def set_summary(self, text: str) -> None:
        """Override the auto-generated summary line."""
        self._summary = text

    # ------------------------------------------------------------------
    # Flushing — always called at process exit
    # ------------------------------------------------------------------

    def finish(self) -> Path:
        """Write the log to Desktop and return the file path.

        Always succeeds — if writing to Desktop fails, falls back to
        the script's own directory.
        """
        self.log_section("执行结果")
        status = "成功" if self._success else "失败"
        self.log(f"  状态: {status}")
        if self._summary:
            self.log(f"  说明: {self._summary}")
        self.log(f"  运行环境: {platform.platform()} | Python {platform.python_version()}")
        self.log(f"  时间: {self._stamp}")

        content = "\n".join(self._lines)
        text = f"{_BOM}{content}\n"

        # Primary: user's Desktop
        path = self._desktop / self._filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return path
        except OSError:
            pass

        # Fallback: next to this script file
        fallback = Path(__file__).resolve().parent.parent / self._filename
        fallback.write_text(text, encoding="utf-8")
        return fallback
