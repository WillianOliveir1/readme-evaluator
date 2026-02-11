"""Router for cache management endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from backend.cache_manager import get_cache_manager
from backend.config import CACHE_MAX_AGE_HOURS

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats")
def get_cache_stats():
    """Get statistics about cache directories."""
    cache_mgr = get_cache_manager()
    return cache_mgr.get_stats()


@router.post("/cleanup")
def cleanup_cache(older_than_hours: int = CACHE_MAX_AGE_HOURS, keep_jobs: bool = True):
    """Clean up old cache files (default: older than configured max age)."""
    cache_mgr = get_cache_manager(max_age_hours=older_than_hours)
    deleted = cache_mgr.cleanup_old_files(dry_run=False)
    stats_after = cache_mgr.get_stats()
    return {
        "status": "cleaned",
        "deleted_count": len(deleted["processing"]) + len(deleted["processed"]),
        "deleted": deleted,
        "stats_after": stats_after,
    }


@router.delete("/cleanup-job/{job_id}")
def cleanup_job_cache(job_id: str):
    """Clean up all files associated with a specific job."""
    cache_mgr = get_cache_manager()
    result = cache_mgr.cleanup_job(job_id, dry_run=False)
    return {
        "status": "cleaned",
        "job_id": job_id,
        "deleted_files": result["deleted_files"],
        "errors": result["errors"],
    }


@router.post("/cleanup-all")
def cleanup_all_cache(keep_jobs: bool = True):
    """Completely clear all cache files.

    MongoDB records are NOT affected.
    """
    cache_mgr = get_cache_manager()
    result = cache_mgr.cleanup_all(keep_jobs_dir=keep_jobs, dry_run=False)
    stats_after = cache_mgr.get_stats()
    return {
        "status": "fully_cleaned",
        "deleted_files": result["deleted_files"],
        "preserved": result["preserved"],
        "errors": result["errors"],
        "stats_after": stats_after,
    }
