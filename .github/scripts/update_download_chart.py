#!/usr/bin/env python3
"""Fetch release download totals and render an SVG trend chart.

GitHub only exposes a *cumulative* ``download_count`` per release asset; it
offers no per-day history.  So this script records one snapshot per day into a
JSON history file and re-renders a plain-text SVG line chart from it.

Pure standard library (``urllib`` + ``json`` + ``datetime``) — zero third-party
dependencies, matching the project's zero-dependency ethos.

Intended to run daily via ``.github/workflows/download-chart.yml``.  Both the
history JSON and the SVG are committed to a dedicated ``chart`` branch so the
``main`` branch's git history stays clean; the README references the SVG by
absolute raw URL.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REPO = "star-Cosmo/auto-fix-rog-gamevisual-v2"
MAX_POINTS = 365  # keep the trailing year


def fetch_total(repo: str, retries: int = 3) -> int:
    """Return the summed download count of every release asset.

    Retries a few times on transient network/API errors so a flaky runner
    does not turn the daily job red.
    """
    api = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    req = urllib.request.Request(
        api,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "download-chart-bot",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                releases = json.load(resp)
            return sum(
                a.get("download_count", 0)
                for r in releases
                for a in r.get("assets", [])
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(3 * attempt)
    raise SystemExit(f"获取下载量失败（已重试 {retries} 次）: {last_err}")


def load_history(path: Path) -> dict:
    """Load the date -> cumulative-total map; empty on first run/corruption."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _nice_axis(max_value: int, max_ticks: int = 8) -> tuple[int, int]:
    """Pick a regular integer Y step + rounded top for a clean axis.

    Returns ``(step, axis_max)`` where ``step`` is a "nice" number
    (1/2/5 x 10^n) chosen so the axis holds at most ``max_ticks`` intervals,
    and ``axis_max`` is ``max_value`` rounded up to a whole multiple of it.
    A count of 121 thus yields step 20 / top 140 -> 0,20,40,...,140.
    """
    max_value = max(1, int(max_value))
    raw = max_value / max_ticks
    magnitude = 10 ** math.floor(math.log10(max(1.0, raw)))
    while True:
        for factor in (1, 2, 5):
            step = factor * magnitude
            if step < 1:
                continue
            intervals = math.ceil(max_value / step)
            if intervals <= max_ticks:
                return step, intervals * step
        magnitude *= 10


def render_svg(history: dict) -> str:
    """Render an SVG line chart from the history map (latest value in title)."""
    items = sorted(history.items())
    if not items:
        items = [(datetime.now(timezone.utc).date().isoformat(), 0)]
    dates = [d for d, _ in items]
    totals = [int(t) for _, t in items]

    width, height = 720, 340
    pad_left, pad_right, pad_top, pad_bottom = 70, 24, 24, 52
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    peak = max(totals) if totals else 0
    step, axis_max = _nice_axis(peak)

    count = len(items)
    spans_years = bool(dates) and dates[0][:4] != dates[-1][:4]

    def x_at(i: int) -> float:
        return pad_left + plot_w / 2 if count == 1 else pad_left + plot_w * i / (count - 1)

    def y_at(value: float) -> float:
        return pad_top + plot_h * (1 - value / axis_max)

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,Segoe UI,Roboto,Helvetica,Arial,'
        f'Microsoft YaHei,PingFang SC,Noto Sans CJK SC,sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')

    # Y grid + labels (regular integer steps, e.g. 0,20,40,...)
    for value in range(0, axis_max + 1, step):
        gy = y_at(value)
        parts.append(
            f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width - pad_right}" y2="{gy:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_left - 10}" y="{gy + 4:.1f}" text-anchor="end" '
            f'font-size="12" fill="#6b7280">{value}</text>'
        )

    # Axes
    parts.append(
        f'<line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{height - pad_bottom}" '
        f'stroke="#9ca3af" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{pad_left}" y1="{height - pad_bottom}" x2="{width - pad_right}" '
        f'y2="{height - pad_bottom}" stroke="#9ca3af" stroke-width="1"/>'
    )

    points = " ".join(f"{x_at(i):.1f},{y_at(v):.1f}" for i, v in enumerate(totals))

    # Area fill
    area = f"{pad_left},{y_at(0):.1f} " + points + f" {x_at(count - 1):.1f},{y_at(0):.1f}"
    parts.append(f'<polygon points="{area}" fill="#2563eb" opacity="0.08"/>')

    # Line + points
    parts.append(
        f'<polyline points="{points}" fill="none" stroke="#2563eb" '
        f'stroke-width="2.5" stroke-linejoin="round"/>'
    )
    for i, value in enumerate(totals):
        cx, cy = x_at(i), y_at(value)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.2" fill="#2563eb"/>')
        parts.append(
            f'<text x="{cx:.1f}" y="{cy - 9:.1f}" text-anchor="middle" '
            f'font-size="11" font-weight="600" fill="#1d4ed8">{value}</text>'
        )

    # X labels (at most ~7; include year when the span crosses a year boundary)
    label_step = max(1, count // 6)
    shown: set[int] = set()
    for i in range(0, count, label_step):
        label = dates[i][2:] if spans_years else dates[i][5:]
        parts.append(
            f'<text x="{x_at(i):.1f}" y="{height - pad_bottom + 22}" text-anchor="middle" '
            f'font-size="11" fill="#6b7280">{label}</text>'
        )
        shown.add(i)
    if (count - 1) not in shown:
        label = dates[-1][2:] if spans_years else dates[-1][5:]
        parts.append(
            f'<text x="{x_at(count - 1):.1f}" y="{height - pad_bottom + 22}" '
            f'text-anchor="middle" font-size="11" fill="#6b7280">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抓取下载总量并渲染 SVG 趋势图")
    parser.add_argument("--repo", default=os.environ.get("GH_REPO", DEFAULT_REPO))
    parser.add_argument("--history", type=Path, default=Path("docs/download-history.json"))
    parser.add_argument("--chart", type=Path, default=Path("docs/download-chart.svg"))
    args = parser.parse_args(argv)

    total = fetch_total(args.repo)
    history = load_history(args.history)
    today = datetime.now(timezone.utc).date().isoformat()
    history[today] = total

    # keep only the trailing window, oldest -> newest
    keys = sorted(history)[-MAX_POINTS:]
    history = {k: history[k] for k in keys}

    args.history.parent.mkdir(parents=True, exist_ok=True)
    args.history.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.chart.parent.mkdir(parents=True, exist_ok=True)
    args.chart.write_text(render_svg(history), encoding="utf-8")

    print(f"total={total}, points={len(history)} -> {args.chart}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
