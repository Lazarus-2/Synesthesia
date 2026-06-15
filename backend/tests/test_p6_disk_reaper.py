"""Phase 6 G5 — age-based media reaper + disk-usage guard."""

from __future__ import annotations

import os

from backend.services.disk_reaper import (
    disk_usage_gb,
    reap_orphaned_media,
    storage_over_limit,
)

_NOW = 1_700_000_000.0
_DAY = 86400.0


def _aged_file(path, days_old):
    path.write_bytes(b"x" * 1024)
    t = _NOW - days_old * _DAY
    os.utime(path, (t, t))


def _aged_dir(path, days_old):
    path.mkdir(parents=True, exist_ok=True)
    (path / "vocals.wav").write_bytes(b"y" * 1024)
    t = _NOW - days_old * _DAY
    os.utime(path, (t, t))


class TestReaper:
    def test_removes_old_keeps_recent(self, tmp_path):
        audio = tmp_path / "uploads"
        stems = tmp_path / "stems"
        audio.mkdir()
        stems.mkdir()
        _aged_file(audio / "old_job_song.mp3", 100)
        _aged_file(audio / "recent_job_song.mp3", 10)
        _aged_dir(stems / "old_job", 100)
        _aged_dir(stems / "recent_job", 10)

        removed = reap_orphaned_media(audio, stems, max_age_s=90 * _DAY, now_ts=_NOW)

        assert removed == {"uploads": 1, "stem_dirs": 1}
        assert not (audio / "old_job_song.mp3").exists()
        assert (audio / "recent_job_song.mp3").exists()
        assert not (stems / "old_job").exists()
        assert (stems / "recent_job").exists()

    def test_missing_dirs_are_safe(self, tmp_path):
        removed = reap_orphaned_media(
            tmp_path / "nope", tmp_path / "nada", max_age_s=_DAY, now_ts=_NOW
        )
        assert removed == {"uploads": 0, "stem_dirs": 0}

    def test_nothing_removed_when_all_recent(self, tmp_path):
        audio = tmp_path / "uploads"
        audio.mkdir()
        _aged_file(audio / "a_x.mp3", 1)
        removed = reap_orphaned_media(audio, tmp_path / "s", max_age_s=90 * _DAY, now_ts=_NOW)
        assert removed["uploads"] == 0
        assert (audio / "a_x.mp3").exists()


class TestDiskGuard:
    def test_usage_and_limit(self, tmp_path):
        (tmp_path / "f.bin").write_bytes(b"z" * (2 * 1024 * 1024))  # 2 MB
        gb = disk_usage_gb(tmp_path)
        assert gb > 0
        assert storage_over_limit([tmp_path], max_gb=0) is False  # disabled
        assert storage_over_limit([tmp_path], max_gb=1000) is False  # under
        assert storage_over_limit([tmp_path], max_gb=gb / 2) is True  # over

    def test_missing_dir_is_zero(self, tmp_path):
        assert disk_usage_gb(tmp_path / "nope") == 0.0
