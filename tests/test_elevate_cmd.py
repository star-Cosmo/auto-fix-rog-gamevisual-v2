"""Regression tests for the UAC elevation command construction.

The old code produced ``cmd /k "py" "script" --elevated`` — with four
quotes cmd.exe strips the first and last one, leaving a mid-path quote
that fails with 「文件名、目录名或卷标语法不正确」.  The fixed payload
wraps everything in one extra outer quote pair, uses ``/c`` and ends
with ``& pause`` so the elevated window closes on any keypress.
"""

from __future__ import annotations

import sys

from gamevisual_fixer.sysprobe import build_elevate_cmd


def _count(payload: str) -> int:
    return payload.count('"')


def test_payload_wrapped_in_outer_quote_pair() -> None:
    payload = build_elevate_cmd([])
    assert payload.startswith('/c ""')
    assert payload.endswith('" & pause')
    # minimum: outer pair (2) + executable pair (2); args add more if spaced
    assert _count(payload) >= 4


def test_stripping_leaves_valid_command() -> None:
    """Simulate cmd.exe quote stripping: drop first+last quote."""
    body = build_elevate_cmd([])[len("/c ") :]
    stripped = body[1 : body.rindex('"')] + body[body.rindex('"') + 1 :]
    assert stripped.startswith(f'"{sys.executable}"')
    # the pause tail survives stripping as the second command
    assert stripped.endswith("& pause")


def test_spaces_in_args_stay_quoted() -> None:
    payload = build_elevate_cmd(["--library", "E:\\my lib dir"])
    # the space-bearing argument must be individually quoted, not the tail
    assert '"E:\\my lib dir"' in payload


def test_elevated_flag_appended_once() -> None:
    payload = build_elevate_cmd(["--dry-run"])
    body = payload[len("/c ") :]
    assert body.count("--elevated") == 1
    assert "--dry-run" in body
