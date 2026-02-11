"""Tests for backend.cache_manager — uses tmp_path for filesystem isolation."""
from __future__ import annotations

import os
import time
import pytest

from backend.cache_manager import CacheManager


# =====================================================================
# Helpers
# =====================================================================

def _create_file(path: str, content: str = "test") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# =====================================================================
# Stats
# =====================================================================

class TestCacheManagerStats:
    """Test get_stats and _get_dir_stats."""

    def test_stats_empty_dirs(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        stats = cm.get_stats()
        # Dirs don't exist yet
        assert stats["processing"]["exists"] is False
        assert stats["processed"]["exists"] is False

    def test_stats_with_files(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        processing = os.path.join(str(tmp_path), "data", "processing")
        _create_file(os.path.join(processing, "a.txt"), "hello")
        _create_file(os.path.join(processing, "b.txt"), "world!!")

        stats = cm.get_stats()
        assert stats["processing"]["exists"] is True
        assert stats["processing"]["file_count"] == 2
        assert stats["processing"]["total_size_bytes"] > 0


# =====================================================================
# Cleanup old files
# =====================================================================

class TestCleanupOldFiles:
    """Test time-based cleanup."""

    def test_dry_run_does_not_delete(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path), max_age_hours=0)  # 0 hours = everything is old
        processing = os.path.join(str(tmp_path), "data", "processing")
        f = _create_file(os.path.join(processing, "old.txt"))

        deleted = cm.cleanup_old_files(dry_run=True)
        assert len(deleted["processing"]) == 1
        # File should still exist
        assert os.path.exists(f)

    def test_real_cleanup_deletes_old(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path), max_age_hours=0)
        processing = os.path.join(str(tmp_path), "data", "processing")
        f = _create_file(os.path.join(processing, "old.txt"))

        deleted = cm.cleanup_old_files(dry_run=False)
        assert len(deleted["processing"]) == 1
        assert not os.path.exists(f)

    def test_recent_files_not_deleted(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path), max_age_hours=999)
        processing = os.path.join(str(tmp_path), "data", "processing")
        f = _create_file(os.path.join(processing, "recent.txt"))

        deleted = cm.cleanup_old_files(dry_run=False)
        assert len(deleted["processing"]) == 0
        assert os.path.exists(f)


# =====================================================================
# Cleanup all
# =====================================================================

class TestCleanupAll:
    """Test full cache clear."""

    def test_cleanup_all_removes_processed(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        processed = os.path.join(str(tmp_path), "data", "processed")
        _create_file(os.path.join(processed, "result.json"))

        result = cm.cleanup_all(dry_run=False)
        assert len(result["deleted_files"]) >= 1
        # Directory itself is recreated empty
        assert os.path.isdir(processed)
        assert len(os.listdir(processed)) == 0

    def test_cleanup_all_preserves_jobs_dir(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        processing = os.path.join(str(tmp_path), "data", "processing")
        jobs_dir = os.path.join(processing, "jobs")
        _create_file(os.path.join(jobs_dir, "job.json"))
        _create_file(os.path.join(processing, "temp.md"))

        result = cm.cleanup_all(keep_jobs_dir=True, dry_run=False)
        # jobs/ preserved
        assert os.path.exists(os.path.join(jobs_dir, "job.json"))
        # temp.md deleted
        assert not os.path.exists(os.path.join(processing, "temp.md"))
        assert jobs_dir in result["preserved"]

    def test_cleanup_all_removes_jobs_when_not_kept(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        processing = os.path.join(str(tmp_path), "data", "processing")
        jobs_dir = os.path.join(processing, "jobs")
        _create_file(os.path.join(jobs_dir, "job.json"))

        result = cm.cleanup_all(keep_jobs_dir=False, dry_run=False)
        assert not os.path.exists(os.path.join(jobs_dir, "job.json"))


# =====================================================================
# Cleanup job
# =====================================================================

class TestCleanupJob:
    """Test per-job file cleanup."""

    def test_deletes_matching_files(self, tmp_path):
        job_id = "abc-123"
        cm = CacheManager(base_dir=str(tmp_path))
        processing = os.path.join(str(tmp_path), "data", "processing")
        f1 = _create_file(os.path.join(processing, f"{job_id}-readme.md"))
        f2 = _create_file(os.path.join(processing, f"{job_id}-prompt.txt"))

        result = cm.cleanup_job(job_id, dry_run=False)
        assert len(result["deleted_files"]) == 2
        assert not os.path.exists(f1)
        assert not os.path.exists(f2)

    def test_does_not_delete_unrelated(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        processing = os.path.join(str(tmp_path), "data", "processing")
        _create_file(os.path.join(processing, "other-file.txt"))

        result = cm.cleanup_job("abc-123", dry_run=False)
        assert len(result["deleted_files"]) == 0
        assert os.path.exists(os.path.join(processing, "other-file.txt"))

    def test_dry_run_reports_but_keeps(self, tmp_path):
        job_id = "def-456"
        cm = CacheManager(base_dir=str(tmp_path))
        processing = os.path.join(str(tmp_path), "data", "processing")
        f = _create_file(os.path.join(processing, f"{job_id}-readme.md"))

        result = cm.cleanup_job(job_id, dry_run=True)
        assert len(result["deleted_files"]) == 1
        assert os.path.exists(f)


# =====================================================================
# Temp path helpers
# =====================================================================

class TestTempPaths:
    """Test get_temp_*_path helpers."""

    def test_get_temp_processing_path(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        p = cm.get_temp_processing_path("test.txt")
        assert p.endswith("test.txt")
        assert "processing" in p
        assert os.path.isdir(os.path.dirname(p))

    def test_get_temp_processed_path(self, tmp_path):
        cm = CacheManager(base_dir=str(tmp_path))
        p = cm.get_temp_processed_path("result.json")
        assert p.endswith("result.json")
        assert "processed" in p
        assert os.path.isdir(os.path.dirname(p))
