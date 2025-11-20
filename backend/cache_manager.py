"""Cache manager for temporary files in processing/ and processed/ folders.

This module provides utilities to manage temporary cache files that are created
during evaluation. These files serve as temporary storage and debugging aids,
but MongoDB remains the source of truth for all persistent data.

The cache is organized as:
  - processing/: Temporary files during active processing (READMEs, prompts, status files)
  - processed/: Temporary files after processing completes (result JSONs, backup files)

Cache files are automatically cleaned based on age or can be manually cleared.
"""
from __future__ import annotations

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List

LOG = logging.getLogger(__name__)


class CacheManager:
    """Manage temporary cache files in processing/ and processed/ directories."""

    def __init__(self, base_dir: Optional[str] = None, max_age_hours: int = 24):
        """Initialize cache manager.

        Args:
            base_dir: Base project directory (defaults to current working directory)
            max_age_hours: Maximum age of cache files before cleanup (default 24 hours)
        """
        self.base_dir = base_dir or os.getcwd()
        self.processing_dir = os.path.join(self.base_dir, "processing")
        self.processed_dir = os.path.join(self.base_dir, "processed")
        self.max_age_hours = max_age_hours
        self.max_age_seconds = max_age_hours * 3600

    def get_stats(self) -> Dict[str, any]:
        """Get cache statistics (size, file count, oldest file).

        Returns:
            Dictionary with cache stats for both directories
        """
        stats = {
            "processing": self._get_dir_stats(self.processing_dir),
            "processed": self._get_dir_stats(self.processed_dir),
        }
        return stats

    def _get_dir_stats(self, directory: str) -> Dict[str, any]:
        """Get statistics for a single directory."""
        if not os.path.exists(directory):
            return {"exists": False, "file_count": 0, "total_size_mb": 0, "oldest_file": None}

        stats = {"exists": True, "file_count": 0, "total_size_bytes": 0, "oldest_file": None, "oldest_mtime": None}

        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        size = os.path.getsize(filepath)
                        mtime = os.path.getmtime(filepath)
                        stats["file_count"] += 1
                        stats["total_size_bytes"] += size

                        # Track oldest file
                        if stats["oldest_mtime"] is None or mtime < stats["oldest_mtime"]:
                            stats["oldest_mtime"] = mtime
                            stats["oldest_file"] = filepath
                    except OSError:
                        continue

            # Convert bytes to MB
            stats["total_size_mb"] = round(stats["total_size_bytes"] / (1024 * 1024), 2)
            
            # Format oldest file timestamp
            if stats["oldest_mtime"]:
                stats["oldest_file_age_hours"] = (datetime.utcnow().timestamp() - stats["oldest_mtime"]) / 3600
                stats["oldest_file_date"] = datetime.fromtimestamp(stats["oldest_mtime"]).isoformat()
            
            del stats["oldest_mtime"]
        except Exception as e:
            LOG.error(f"Error getting stats for {directory}: {e}")

        return stats

    def cleanup_old_files(self, dry_run: bool = False) -> Dict[str, List[str]]:
        """Clean up cache files older than max_age_hours.

        Args:
            dry_run: If True, only report what would be deleted, don't actually delete

        Returns:
            Dictionary with lists of deleted (or would-be deleted) files
        """
        now = datetime.utcnow().timestamp()
        cutoff_time = now - self.max_age_seconds

        deleted = {"processing": [], "processed": []}

        for directory_name, directory_path in [
            ("processing", self.processing_dir),
            ("processed", self.processed_dir),
        ]:
            if not os.path.exists(directory_path):
                continue

            try:
                for root, dirs, files in os.walk(directory_path):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            mtime = os.path.getmtime(filepath)
                            if mtime < cutoff_time:
                                age_hours = (now - mtime) / 3600
                                if not dry_run:
                                    os.remove(filepath)
                                    LOG.info(f"Deleted old cache file ({age_hours:.1f}h): {filepath}")
                                deleted[directory_name].append(filepath)
                        except OSError as e:
                            LOG.warning(f"Could not process file {filepath}: {e}")
            except Exception as e:
                LOG.error(f"Error cleaning up {directory_path}: {e}")

        return deleted

    def cleanup_all(self, keep_jobs_dir: bool = True, dry_run: bool = False) -> Dict[str, any]:
        """Clear all cache files, optionally preserving processing/jobs/ for active jobs.

        Args:
            keep_jobs_dir: If True, preserve processing/jobs/ directory (for active job status)
            dry_run: If True, only report what would be deleted

        Returns:
            Dictionary with cleanup results and stats
        """
        result = {"deleted_files": [], "preserved": [], "errors": []}

        # Clean processed/
        if os.path.exists(self.processed_dir):
            try:
                if not dry_run:
                    shutil.rmtree(self.processed_dir)
                    os.makedirs(self.processed_dir, exist_ok=True)
                    LOG.info(f"Cleared cache directory: {self.processed_dir}")
                result["deleted_files"].append(self.processed_dir)
            except Exception as e:
                LOG.error(f"Error clearing {self.processed_dir}: {e}")
                result["errors"].append(str(e))

        # Clean processing/ (but keep jobs/ if requested)
        if os.path.exists(self.processing_dir):
            jobs_dir = os.path.join(self.processing_dir, "jobs")

            # Backup jobs directory if needed
            jobs_backup = None
            if keep_jobs_dir and os.path.exists(jobs_dir):
                jobs_backup = os.path.join(self.processing_dir, ".jobs_backup")
                try:
                    if os.path.exists(jobs_backup):
                        shutil.rmtree(jobs_backup)
                    shutil.copytree(jobs_dir, jobs_backup)
                except Exception as e:
                    LOG.warning(f"Could not backup jobs directory: {e}")
                    jobs_backup = None

            # Remove processing directory
            try:
                if not dry_run:
                    shutil.rmtree(self.processing_dir)
                    os.makedirs(self.processing_dir, exist_ok=True)
                    LOG.info(f"Cleared cache directory: {self.processing_dir}")
                result["deleted_files"].append(self.processing_dir)
            except Exception as e:
                LOG.error(f"Error clearing {self.processing_dir}: {e}")
                result["errors"].append(str(e))

            # Restore jobs directory
            if jobs_backup and os.path.exists(jobs_backup):
                try:
                    jobs_target = os.path.join(self.processing_dir, "jobs")
                    if not dry_run:
                        shutil.move(jobs_backup, jobs_target)
                    result["preserved"].append(jobs_target)
                except Exception as e:
                    LOG.warning(f"Could not restore jobs directory: {e}")

        return result

    def cleanup_job(self, job_id: str, dry_run: bool = False) -> Dict[str, any]:
        """Clean up files associated with a specific job.

        Args:
            job_id: Job ID to clean up
            dry_run: If True, only report what would be deleted

        Returns:
            Dictionary with cleanup results
        """
        result = {"deleted_files": [], "errors": []}

        patterns_to_remove = [
            f"{job_id}-readme.md",
            f"{job_id}-prompt.txt",
            f"{job_id}-backup.jsonl",
            f"{job_id}-result-*.json",
        ]

        for directory in [self.processing_dir, self.processed_dir]:
            if not os.path.exists(directory):
                continue

            for root, dirs, files in os.walk(directory):
                for file in files:
                    filepath = os.path.join(root, file)
                    # Check if file matches job patterns
                    should_delete = any(
                        pattern.replace("*", job_id) in file or
                        (pattern.startswith(job_id) and file.startswith(job_id))
                        for pattern in patterns_to_remove
                    )

                    if should_delete:
                        try:
                            if not dry_run:
                                os.remove(filepath)
                                LOG.info(f"Deleted job cache file: {filepath}")
                            result["deleted_files"].append(filepath)
                        except OSError as e:
                            LOG.error(f"Could not delete {filepath}: {e}")
                            result["errors"].append(str(e))

        return result

    def get_temp_processing_path(self, filename: str) -> str:
        """Get a temporary file path in processing/ directory.

        Args:
            filename: Name of the temporary file

        Returns:
            Full path to the temporary file
        """
        os.makedirs(self.processing_dir, exist_ok=True)
        return os.path.join(self.processing_dir, filename)

    def get_temp_processed_path(self, filename: str) -> str:
        """Get a temporary file path in processed/ directory.

        Args:
            filename: Name of the temporary file

        Returns:
            Full path to the temporary file
        """
        os.makedirs(self.processed_dir, exist_ok=True)
        return os.path.join(self.processed_dir, filename)


# Global instance (lazy initialized)
_global_cache_manager: Optional[CacheManager] = None


def get_cache_manager(base_dir: Optional[str] = None, max_age_hours: int = 24) -> CacheManager:
    """Get or create global cache manager instance.

    Args:
        base_dir: Base project directory
        max_age_hours: Maximum age of cache files

    Returns:
        CacheManager instance
    """
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager(base_dir=base_dir, max_age_hours=max_age_hours)
    return _global_cache_manager
