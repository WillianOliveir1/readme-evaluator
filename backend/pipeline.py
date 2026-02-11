"""Minimal pipeline runner that executes extraction pipeline as a job and
writes a status file per job so the frontend can poll progress step-by-step.

This is intentionally small and file-based to avoid adding external
dependencies (queues/databases). It writes job status to
`processing/jobs/{job_id}.json` and result files to `processed/`.
"""
from __future__ import annotations

import json
import os
import uuid
import shutil
import logging
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from backend.download.download import ReadmeDownloader
from backend.evaluate.extractor import extract_json_from_readme
from backend.db.mongodb_handler import MongoDBHandler
from backend.cache_manager import get_cache_manager
from backend.config import SCHEMA_PATH, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Concurrency control
# ---------------------------------------------------------------------------

MAX_CONCURRENT_PIPELINES = int(os.environ.get("MAX_CONCURRENT_PIPELINES", "3"))
"""Maximum number of pipeline jobs running simultaneously."""

_pipeline_semaphore = threading.Semaphore(MAX_CONCURRENT_PIPELINES)
"""Limits how many pipeline executions can happen at the same time."""

_active_jobs: set[str] = set()
_active_jobs_lock = threading.Lock()
"""Prevents the same job from being executed twice concurrently."""

_file_locks: dict[str, threading.Lock] = {}
_file_locks_lock = threading.Lock()
"""Per-job file lock for thread-safe JSON writes."""


def _get_file_lock(job_id: str) -> threading.Lock:
    """Return (or create) a lock specific to *job_id*."""
    with _file_locks_lock:
        if job_id not in _file_locks:
            _file_locks[job_id] = threading.Lock()
        return _file_locks[job_id]


def _release_file_lock(job_id: str) -> None:
    """Remove the per-job lock once the job is finished (cleanup)."""
    with _file_locks_lock:
        _file_locks.pop(job_id, None)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class PipelineRunner:
    """Run a small pipeline and persist job status to a file.

    Steps are simple and intended for frontend progress UI.
    """

    def __init__(self, jobs_dir: Optional[str] = None):
        self.jobs_dir = jobs_dir or os.path.join(os.getcwd(), "data", "processing", "jobs")
        os.makedirs(self.jobs_dir, exist_ok=True)

    def _job_path(self, job_id: str) -> str:
        return os.path.join(self.jobs_dir, f"{job_id}.json")

    def _write(self, job: Dict[str, Any]) -> None:
        path = self._job_path(job["id"])
        lock = _get_file_lock(job["id"])
        with lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)

    def new_job(self, params: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        job: Dict[str, Any] = {
            "id": job_id,
            "status": "queued",
            "created_at": _now_iso(),
            "current_step": None,
            "params": params,
            "steps": [],
            "artifacts": {},
            "result": None,
            "error": None,
        }
        self._write(job)
        return job

    def _start_step(self, job: Dict[str, Any], step_name: str) -> Dict[str, Any]:
        step = {"name": step_name, "status": "running", "started_at": _now_iso(), "finished_at": None, "message": None}
        job["steps"].append(step)
        job["current_step"] = step_name
        job["status"] = "running"
        self._write(job)
        return step

    def _finish_step(self, job: Dict[str, Any], step: Dict[str, Any], ok: bool = True, message: Optional[str] = None):
        step["finished_at"] = _now_iso()
        step["status"] = "done" if ok else "failed"
        step["message"] = message
        if not ok:
            job["status"] = "failed"
            job["error"] = message
        self._write(job)

    def run(self, job_id: str, params: Dict[str, Any]) -> None:
        """Execute the pipeline for a previously created job id.

        This method updates the job file at each step to allow polling.
        Concurrency is controlled by a global semaphore (MAX_CONCURRENT_PIPELINES)
        and duplicate execution of the same job is prevented.
        """
        # --- Guard: prevent duplicate execution of the same job ---
        with _active_jobs_lock:
            if job_id in _active_jobs:
                LOG.warning("Job %s is already running — ignoring duplicate request", job_id)
                return
            _active_jobs.add(job_id)

        acquired = _pipeline_semaphore.acquire(timeout=0)
        if not acquired:
            LOG.info(
                "Concurrency limit reached (%d). Job %s waiting for a slot …",
                MAX_CONCURRENT_PIPELINES,
                job_id,
            )
            _pipeline_semaphore.acquire()  # block until a slot opens

        try:
            self._run_inner(job_id, params)
        finally:
            _pipeline_semaphore.release()
            with _active_jobs_lock:
                _active_jobs.discard(job_id)
            _release_file_lock(job_id)

    def _run_inner(self, job_id: str, params: Dict[str, Any]) -> None:
        """Core pipeline logic (called by *run* after concurrency guards)."""
        path = self._job_path(job_id)
        if not os.path.exists(path):
            LOG.error("Job %s not found", job_id)
            return

        with open(path, "r", encoding="utf-8") as f:
            job = json.load(f)

        try:
            # Step 1: download_readme
            step = self._start_step(job, "download_readme")
            repo_url = params.get("repo_url")
            branch = params.get("branch")
            if not repo_url and not params.get("readme_text"):
                raise ValueError("Either repo_url or readme_text must be provided")

            readme_path = None
            if repo_url:
                dl = ReadmeDownloader()
                readme_path = dl.download(repo_url, branch=branch)
                job["artifacts"]["readme_path"] = readme_path
            else:
                # write provided readme_text to a file for bookkeeping
                txt = params.get("readme_text", "")
                out_dir = os.path.join(os.getcwd(), "data", "processing")
                os.makedirs(out_dir, exist_ok=True)
                readme_path = os.path.join(out_dir, f"{job_id}-readme.md")
                with open(readme_path, "w", encoding="utf-8") as rf:
                    rf.write(txt)
                job["artifacts"]["readme_path"] = readme_path

            self._finish_step(job, step, ok=True)

            # read README text
            with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                readme_text = f.read()

            # Step 2: build_prompt
            step = self._start_step(job, "build_prompt")
            prompt_only = extract_json_from_readme(
                readme_text,
                schema_path=params.get("schema_path", SCHEMA_PATH),
                example_json=params.get("example_json"),
                model=None,
                system_prompt=params.get("system_prompt"),
                readme_path=readme_path,
                max_tokens=params.get("max_tokens", DEFAULT_MAX_TOKENS),
                temperature=params.get("temperature", DEFAULT_TEMPERATURE),
            )
            # save prompt to artifact
            prompt_txt = prompt_only.prompt
            if prompt_txt:
                prompt_file = os.path.join(os.path.dirname(readme_path), f"{job_id}-prompt.txt")
                with open(prompt_file, "w", encoding="utf-8") as pf:
                    pf.write(prompt_txt)
                job["artifacts"]["prompt_path"] = prompt_file

            self._finish_step(job, step, ok=True)
            prompt_only_dict = prompt_only.to_dict()

            # Step 3: call_model (may be skipped)
            step = self._start_step(job, "call_model")
            model = params.get("model")
            if model and os.environ.get("GEMINI_API_KEY"):
                called = extract_json_from_readme(
                    readme_text,
                    schema_path=params.get("schema_path", SCHEMA_PATH),
                    example_json=params.get("example_json"),
                    model=model,
                    system_prompt=params.get("system_prompt"),
                    readme_path=readme_path,
                    max_tokens=params.get("max_tokens", DEFAULT_MAX_TOKENS),
                    temperature=params.get("temperature", DEFAULT_TEMPERATURE),
                )
                job["result"] = called.to_dict()
                job["artifacts"]["model_output"] = called.model_output
            else:
                # skipped
                job["result"] = prompt_only_dict
                self._finish_step(job, step, ok=True, message="skipped: no model or GEMINI_API_KEY")
                # continue to validation step which will be skipped too
                # mark call_model as skipped and move on
                # We already finished the step here
                pass

            # If we reached here and model call was executed, finish step
            if job.get("result") is not None and job["result"] is not prompt_only_dict:
                # model executed
                self._finish_step(job, step, ok=True)

            # Step 4: validate_schema (if possible)
            step = self._start_step(job, "validate_schema")
            res = job.get("result")
            validation_ok = None
            validation_errors = None
            if res and res.get("parsed") is not None:
                validation_ok = res.get("validation_ok")
                validation_errors = res.get("validation_errors")
            else:
                validation_ok = None
            job["result"] = res
            job["result"]["validation_ok"] = validation_ok
            job["result"]["validation_errors"] = validation_errors
            self._finish_step(job, step, ok=True)

            # Step 5: save_results (move files to processed/ and write result JSON)
            step = self._start_step(job, "save_results")
            processed_dir = os.path.join(os.getcwd(), "data", "processed")
            os.makedirs(processed_dir, exist_ok=True)
            try:
                if readme_path and os.path.exists(readme_path):
                    dest_readme = os.path.join(processed_dir, os.path.basename(readme_path))
                    shutil.move(readme_path, dest_readme)
                    job["artifacts"]["processed_readme"] = dest_readme
                # write result
                base_name = os.path.splitext(os.path.basename(job["artifacts"].get("processed_readme", job_id)))[0]
                result_json_name = f"{base_name}-result-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
                result_json_path = os.path.join(processed_dir, result_json_name)
                with open(result_json_path, "w", encoding="utf-8") as jf:
                    json.dump(job.get("result", {}), jf, ensure_ascii=False, indent=2)
                job["result_path"] = result_json_path
            except Exception as e:
                LOG.exception("Failed to save results: %s", e)
                self._finish_step(job, step, ok=False, message=str(e))
                return

            self._finish_step(job, step, ok=True)

            # Step 6: save_to_database (MongoDB + file backup)
            step = self._start_step(job, "save_to_database")
            try:
                result_data = job.get("result", {})
                
                # Try to save to MongoDB using MongoDBHandler
                try:
                    handler = MongoDBHandler()
                    mongo_id = handler.insert_one(result_data)
                    handler.disconnect()
                    
                    job["artifacts"]["mongo_id"] = mongo_id
                    if mongo_id:
                        LOG.info(f"Results saved to MongoDB: {mongo_id}")
                    else:
                        LOG.warning("MongoDB save returned None")
                except ValueError as e:
                    LOG.warning(f"MongoDB not configured: {e}")
                except Exception as e:
                    LOG.exception(f"Failed to save to MongoDB: {e}")
                
                # Always save file backup
                try:
                    backup_file = os.path.join(processed_dir, f"{job_id}-backup.json")
                    with open(backup_file, "w", encoding="utf-8") as f:
                        json.dump(result_data, f, indent=2, ensure_ascii=False)
                    job["artifacts"]["backup_file"] = backup_file
                    LOG.info(f"File backup saved: {backup_file}")
                except Exception as file_exc:
                    LOG.exception(f"Failed to save file backup: {file_exc}")
                    
            except Exception as e:
                LOG.exception("Failed to save to database: %s", e)
                self._finish_step(job, step, ok=False, message=str(e))
                return

            self._finish_step(job, step, ok=True)

            # Step 7: cleanup_cache (remove temporary files, keep MongoDB as source of truth)
            step = self._start_step(job, "cleanup_cache")
            try:
                cache_mgr = get_cache_manager()
                cleanup_result = cache_mgr.cleanup_job(job_id, dry_run=False)
                job["artifacts"]["cache_cleanup"] = {
                    "deleted_files": len(cleanup_result["deleted_files"]),
                    "errors": cleanup_result["errors"],
                }
                if cleanup_result["errors"]:
                    LOG.warning(f"Errors during cache cleanup: {cleanup_result['errors']}")
                else:
                    LOG.info(f"Cache cleaned for job {job_id}: {len(cleanup_result['deleted_files'])} files removed")
            except Exception as e:
                LOG.warning(f"Failed to cleanup cache for job {job_id}: {e}")
                job["artifacts"]["cache_cleanup"] = {"error": str(e)}

            self._finish_step(job, step, ok=True)

            # success
            job["status"] = "succeeded"
            job["finished_at"] = _now_iso()
            self._write(job)

        except Exception as exc:
            LOG.exception("Job %s failed: %s", job_id, exc)
            # mark last step failed
            try:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["finished_at"] = _now_iso()
                self._write(job)
            except Exception:
                pass


def get_active_jobs() -> set[str]:
    """Return a snapshot of currently running job IDs (for monitoring)."""
    with _active_jobs_lock:
        return _active_jobs.copy()


__all__ = ["PipelineRunner", "get_active_jobs", "MAX_CONCURRENT_PIPELINES"]
