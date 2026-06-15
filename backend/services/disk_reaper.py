"""Age-based reaper for orphaned media files (Phase 6 G5 / OPS-01).

The Mongo TTL expires *documents* after 90 days but leaves the on-disk
upload + stem files behind forever — unbounded growth for both anonymous and
owned analyses. This reaper deletes upload files and per-job stem directories
whose modification time is older than the same retention window. It keys on
**age**, not ownership, so anonymous and owned files age out identically and
nothing readable within the window is touched.

Pure filesystem + stdlib so it is unit-testable without Mongo/Redis; the
Taskiq wrapper in ``backend.tasks`` schedules it, and a deployment cron/
scheduler triggers that task daily (documented in the worker setup).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def reap_orphaned_media(
    audio_dir: Path,
    stems_dir: Path,
    max_age_s: float,
    now_ts: float,
) -> dict[str, int]:
    """Delete upload files + stem dirs older than ``max_age_s``.

    ``now_ts`` is the reference time (``time.time()`` in production; passed in
    so tests are deterministic). Returns ``{"uploads": n, "stem_dirs": n}``.
    Never raises on a single bad entry — it logs and continues so one
    permission error can't stall the whole sweep.
    """
    cutoff = now_ts - max_age_s
    removed = {"uploads": 0, "stem_dirs": 0}

    if audio_dir.is_dir():
        for entry in audio_dir.iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed["uploads"] += 1
            except OSError as e:  # pragma: no cover - defensive
                logger.warning("disk_reaper: could not remove upload %s: %s", entry, e)

    if stems_dir.is_dir():
        for entry in stems_dir.iterdir():
            try:
                if entry.is_dir() and entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed["stem_dirs"] += 1
            except OSError as e:  # pragma: no cover - defensive
                logger.warning("disk_reaper: could not remove stem dir %s: %s", entry, e)

    if removed["uploads"] or removed["stem_dirs"]:
        logger.info(
            "disk_reaper: removed %d uploads, %d stem dirs older than %.0f days",
            removed["uploads"],
            removed["stem_dirs"],
            max_age_s / 86400.0,
        )
    return removed


def disk_usage_gb(path: Path) -> float:
    """Total size (GB) of all files under ``path`` (0.0 when missing)."""
    if not path.is_dir():
        return 0.0
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:  # pragma: no cover - defensive
            continue
    return total / (1024.0**3)


def storage_over_limit(dirs: list[Path], max_gb: float) -> bool:
    """True when combined usage across ``dirs`` exceeds ``max_gb`` (0 = disabled)."""
    if max_gb <= 0:
        return False
    return sum(disk_usage_gb(d) for d in dirs) >= max_gb
