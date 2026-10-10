"""Execute a FixPlan against real directories: backup first, then copy."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .edid import Chromaticity
from .iccgen import build_icc
from .logger import detail
from .planner import (
    SOURCE_GENERATED,
    SOURCE_LIBRARY,
    SOURCE_SYSTEM,
    FixPlan,
)


class ApplyError(Exception):
    """The plan could not be executed."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class AppliedReport:
    """Outcome of one apply run."""

    copied: int
    skipped: int
    backup_path: Path | None


def backup_gamevisual(gv_dir: Path) -> Path:
    """Snapshot the whole GameVisual dir next to itself; returns backup path."""
    if not gv_dir.is_dir():
        raise ApplyError(f"GameVisual directory does not exist: {gv_dir}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = gv_dir.parent / f"{gv_dir.name}_backup_{stamp}"
    shutil.copytree(gv_dir, backup_dir)
    detail(f"备份 GameVisual 目录 -> {backup_dir}")
    return backup_dir


def apply(
    plan: FixPlan,
    gv_dir: Path,
    library_dir: Path,
    spool_dir: Path,
    *,
    create_backup: bool = True,
    chromaticity: Chromaticity | None = None,
) -> AppliedReport:
    """Copy every planned file; skip actions whose destination already exists.

    ``chromaticity`` is required only when the plan contains actions with
    ``src_dir == SOURCE_GENERATED`` — those ICC files are synthesised at
    apply time straight into the GameVisual directory.
    """
    gv_dir.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if create_backup:
        backup_path = backup_gamevisual(gv_dir)

    copied = 0
    skipped = 0
    for action in plan.actions:
        dst = gv_dir / action.dst_file
        if dst.exists():
            skipped += 1
            detail(f"跳过(已存在): {action.dst_file}")
            continue
        if action.src_dir == SOURCE_GENERATED:
            if chromaticity is None:
                raise ApplyError(
                    "plan contains a generated ICC action but no chromaticity was provided"
                )
            src = None  # generated: bytes come from build_icc
            icc_bytes = build_icc(chromaticity)
            dst.write_bytes(icc_bytes)
            copied += 1
            detail(f"生成: {action.dst_file}（{len(icc_bytes)} 字节）")
            continue
        src_root = {SOURCE_LIBRARY: library_dir, SOURCE_SYSTEM: gv_dir}[action.src_dir]
        src = src_root / action.src_name
        if not src.is_file():
            raise ApplyError(f"source vanished before copy: {src}")
        shutil.copy2(src, dst)
        copied += 1
        detail(f"复制: {action.src_name} -> {action.dst_file}")
        if action.extra_dst_dir == "spool":
            spool_dst = spool_dir / action.dst_file
            if not spool_dst.exists():
                spool_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, spool_dst)
                copied += 1
                detail(f"同时复制到系统色彩目录: {action.dst_file}")
    return AppliedReport(copied=copied, skipped=skipped, backup_path=backup_path)
