"""Router for background job management."""

import json as _json
import os
import re as _re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from backend.models import JobRequest
from backend.pipeline import PipelineRunner, get_active_jobs
from backend.rate_limit import limiter, EXPENSIVE_LIMIT

router = APIRouter(tags=["jobs"])

_JOBS_DIR = os.path.join(os.getcwd(), "data", "processing", "jobs")

# -----------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------

def _load_job(path: str) -> Optional[dict]:
    """Safely load a single job JSON file (returns *None* on error)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return None


# -----------------------------------------------------------------------
# POST /jobs  —  create a new pipeline job
# -----------------------------------------------------------------------

@router.post("/jobs")
@limiter.limit(EXPENSIVE_LIMIT)
def create_job_endpoint(request: Request, req: JobRequest, background_tasks: BackgroundTasks):
    """Create a job and run the pipeline in the background."""
    runner = PipelineRunner()
    params = req.dict()
    job = runner.new_job(params)
    job_id = job["id"]
    background_tasks.add_task(runner.run, job_id, params)
    return {
        "job_id": job_id,
        "status_path": os.path.join("data", "processing", "jobs", f"{job_id}.json"),
    }


# -----------------------------------------------------------------------
# GET /jobs  —  list jobs with pagination + filters
# -----------------------------------------------------------------------

@router.get("/jobs")
def list_jobs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status (queued, running, succeeded, failed)"),
    sort: str = Query("created_at", description="Sort field (created_at or status)"),
    order: str = Query("desc", description="Sort order (asc or desc)"),
):
    """List all known pipeline jobs with pagination and optional filters."""
    jobs_dir = _JOBS_DIR
    if not os.path.isdir(jobs_dir):
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 0}

    # Load all jobs
    all_jobs: list[dict] = []
    for fname in os.listdir(jobs_dir):
        if not fname.endswith(".json"):
            continue
        data = _load_job(os.path.join(jobs_dir, fname))
        if data:
            all_jobs.append(data)

    # Filter by status
    if status:
        allowed = {s.strip().lower() for s in status.split(",")}
        all_jobs = [j for j in all_jobs if j.get("status", "").lower() in allowed]

    # Sort
    reverse = order.lower() != "asc"
    sort_key = sort if sort in ("created_at", "status") else "created_at"
    all_jobs.sort(key=lambda j: j.get(sort_key, ""), reverse=reverse)

    total = len(all_jobs)
    pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    items = all_jobs[start : start + page_size]

    # Annotate running jobs
    active = get_active_jobs()
    for item in items:
        item["is_active"] = item.get("id", "") in active

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


# -----------------------------------------------------------------------
# GET /jobs/{job_id}  —  single job status
# -----------------------------------------------------------------------

@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Return the current status of a background job."""
    # Sanitize: only allow alphanumeric, hyphens, and underscores (UUID format)
    if not _re.fullmatch(r"[a-zA-Z0-9_-]+", job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    path = os.path.join(_JOBS_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
