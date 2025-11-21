"""Small FastAPI app that exposes the ReadmeDownloader via HTTP.

Endpoint:
  POST /readme  -> { "repo_url": "https://github.com/owner/repo", "branch": "optional" }

Response:
  200: { "filename": "...", "content": "..." }
  400/500: { "detail": "error message" }
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional
from pathlib import Path

# Load .env from repository root (if present) so GEMINI_API_KEY and other
# developer secrets can be set in a local .env file during development.
try:
    from dotenv import load_dotenv
    _proj_root = Path(__file__).resolve().parents[1]
    load_dotenv(_proj_root / ".env")
except Exception:
    # If python-dotenv is not installed or loading fails, continue silently.
    pass

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import logging
import shutil
from datetime import datetime

from backend.download.download import ReadmeDownloader
from backend.evaluate.extractor import extract_json_from_readme
from backend.evaluate.progress import ProgressUpdate
from backend.present.renderer import render_from_json
from backend.db.persistence import save_to_file, save_to_mongo, save_with_mongo_fallback
from backend.db.mongodb_handler import MongoDBHandler
from backend.gemini_client import GeminiClient
from backend.cache_manager import get_cache_manager
import json as _json
from backend.pipeline import PipelineRunner
from fastapi.responses import StreamingResponse
import asyncio
import queue
from backend.config import (
    DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE,
    GENERATION_MAX_TOKENS, GENERATION_TEMPERATURE,
    RENDER_MAX_TOKENS, RENDER_TEMPERATURE,
    SCHEMA_PATH, SYSTEM_PROMPT_PATH,
    CACHE_MAX_AGE_HOURS
)


class JobRequest(BaseModel):
    repo_url: Optional[str] = None
    readme_text: Optional[str] = None
    schema_path: Optional[str] = SCHEMA_PATH
    example_json: Optional[dict] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = DEFAULT_TEMPERATURE
    branch: Optional[str] = None


class ReadmeRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    # When true the downloaded README will be saved under backend/examples so
    # it is easy to inspect on disk. Default True to aid development/debugging.
    save_to_examples: Optional[bool] = True


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    max_tokens: Optional[int] = GENERATION_MAX_TOKENS
    temperature: Optional[float] = GENERATION_TEMPERATURE


class ExtractRequest(BaseModel):
    # Either provide `repo_url` to download, or `readme_text` directly.
    repo_url: Optional[str] = None
    readme_text: Optional[str] = None
    schema_path: Optional[str] = SCHEMA_PATH
    example_json: Optional[dict] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = DEFAULT_TEMPERATURE


class RenderRequest(BaseModel):
    json_object: dict
    model: Optional[str] = None
    style_instructions: Optional[str] = None
    max_tokens: Optional[int] = RENDER_MAX_TOKENS
    temperature: Optional[float] = RENDER_TEMPERATURE


class EvaluationRequest(BaseModel):
    evaluation_json: dict
    style_instructions: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = RENDER_TEMPERATURE


app = FastAPI(title="Readme Downloader API")

# Lightweight request logging middleware to aid debugging of 404/Not Found
import logging


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info("Incoming request: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        logging.exception("Error handling request %s %s: %s", request.method, request.url.path, exc)
        raise
    logging.info("Response %s for %s %s", response.status_code, request.method, request.url.path)
    return response



@app.get("/")
async def root():
    """Simple health/info endpoint to make browsing the API root friendlier.

    Visiting the server root in a browser previously returned 404 because the
    service exposes only POST endpoints. This returns a short JSON with useful
    links to the main endpoints.
    """
    return {
        "service": "readme-evaluator backend",
        "endpoints": [
            {"path": "/readme", "method": "POST", "desc": "download README from GitHub"},
            {"path": "/extract-json", "method": "POST", "desc": "extract structured JSON from README"},
            {"path": "/extract-json-stream", "method": "POST", "desc": "extract JSON with progress streaming (SSE)"},
            {"path": "/render", "method": "POST", "desc": "render JSON to human text"},
            {"path": "/render-evaluation", "method": "POST", "desc": "transform evaluation JSON to natural language text"},
            {"path": "/generate", "method": "POST", "desc": "call Gemini model (requires GEMINI_API_KEY)"},
            {"path": "/cache/stats", "method": "GET", "desc": "get cache statistics"},
            {"path": "/cache/cleanup", "method": "POST", "desc": "manually cleanup old cache files"},
            {"path": "/cache/cleanup-job/{job_id}", "method": "DELETE", "desc": "cleanup files for specific job"},
        ],
    }

# Allow local Next.js dev server by default
app.add_middleware(
    CORSMiddleware,
    # allow both localhost and 127.0.0.1 variants to avoid CORS preflight failures
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/readme")
async def readme_endpoint(req: ReadmeRequest):
    logging.info("readme_endpoint: called with repo_url=%s branch=%s", getattr(req, 'repo_url', None), getattr(req, 'branch', None))
    dl = ReadmeDownloader()
    try:
        # download writes a file and returns its path (saved to temp directory)
        path = dl.download(req.repo_url, branch=req.branch)
        # read file as text (try utf-8, fallback with replacement)
        with open(path, "rb") as f:
            data = f.read()
        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("utf-8", errors="replace")
        filename = os.path.basename(path)
        # Return the path where the downloader saved the file so clients can inspect it
        resp = {"filename": filename, "content": text, "saved_path": path}
        return resp
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/generate")
def generate_endpoint(req: GenerateRequest):
    """Simple endpoint to call a Gemini model (Google GenAI).

    Expects GEMINI_API_KEY in the environment. The endpoint mirrors the prior
    behavior but uses the GeminiClient implementation.
    """
    try:
        client = GeminiClient()
        output = client.generate(req.prompt, model=req.model, max_tokens=req.max_tokens or 256, temperature=req.temperature or 0.0)
        return {"model": req.model or client.default_model, "output": output}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/extract-json")
def extract_endpoint(req: ExtractRequest):
    """Endpoint to extract structured JSON from a README.

    Either `repo_url` or `readme_text` must be provided. If `model` is set the
    endpoint will call the model; otherwise it will return the built prompt.
    """
    readme_text = None
    path = None
    if req.repo_url:
        logging.info("extract-json: received repo_url=%s", req.repo_url)
        dl = ReadmeDownloader()
        try:
            logging.info("extract-json: starting download for %s", req.repo_url)
            path = dl.download(req.repo_url, branch=None)
            logging.info("extract-json: downloaded README to %s", path)
        except Exception as exc:
            logging.exception("extract-json: failed to download README for %s: %s", req.repo_url, exc)
            # propagate an HTTP error so the client sees the failure
            raise HTTPException(status_code=502, detail=f"Failed to download README: {exc}")
        with open(path, "rb") as f:
            data = f.read()
        try:
            readme_text = data.decode("utf-8")
        except Exception:
            readme_text = data.decode("utf-8", errors="replace")
        # Keep the downloaded file in processing/ so the pipeline and developers can inspect it.
        logging.info("extract-json: using README downloaded from repo_url; length=%d saved_path=%s", len(readme_text) if readme_text else 0, path)
    elif req.readme_text:
        readme_text = req.readme_text
        logging.info("extract-json: using readme_text provided in request; length=%d", len(readme_text) if readme_text else 0)
    else:
        raise HTTPException(status_code=400, detail="Either repo_url or readme_text must be provided")

    # Determine system prompt: prefer provided text, otherwise try to load a local template
    system_prompt_text = None
    if req.system_prompt:
        system_prompt_text = req.system_prompt
    else:
        local_path = SYSTEM_PROMPT_PATH
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as spf:
                    system_prompt_text = spf.read()
            except Exception:
                system_prompt_text = None

    # If the client requested a model call but GEMINI_API_KEY is not set,
    # skip calling the model to avoid initializing the Gemini client which
    # would raise a runtime error. Return the built prompt and note that
    # the model call was skipped.
    if req.model and not os.environ.get("GEMINI_API_KEY"):
        result = extract_json_from_readme(
            readme_text,
            schema_path=req.schema_path,
            example_json=req.example_json,
            model=None,
            system_prompt=system_prompt_text,
            readme_path=path,
            max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
            temperature=req.temperature or DEFAULT_TEMPERATURE,
        )
        result_dict = result.to_dict()
        result_dict["model_skipped"] = True
        result_dict["model_skipped_reason"] = "GEMINI_API_KEY not set on server"
        return result_dict

    result = extract_json_from_readme(
        readme_text,
        schema_path=req.schema_path,
        example_json=req.example_json,
        model=req.model,
        system_prompt=system_prompt_text,
        readme_path=path,
        max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
        temperature=req.temperature or DEFAULT_TEMPERATURE,
    )

    result_dict = result.to_dict()

    # Include the saved_path (where the README was written) for traceability
    try:
        if 'path' in locals() and path:
            result_dict['saved_path'] = path
    except Exception:
        pass

    # After processing, move the README to a `processed/` folder and save the
    # resulting JSON there for auditability. Only act when a downloaded file
    # path is available (i.e., repo_url was used).
    try:
        processed_dir = os.path.join(os.getcwd(), "data", "processed")
        os.makedirs(processed_dir, exist_ok=True)

        # If a downloaded README file exists, move it to processed/
        if 'path' in locals() and path:
            try:
                dest_readme = os.path.join(processed_dir, os.path.basename(path))
                shutil.move(path, dest_readme)
                result_dict['processed_readme'] = dest_readme
                # update saved_path to point to the new location
                result_dict['saved_path'] = dest_readme
            except Exception:
                logging.exception("Failed to move README %s to processed/", path)

        # Save the extraction result as JSON in processed/
        try:
            base_name = os.path.splitext(os.path.basename(result_dict.get('saved_path', 'result')))[0]
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            result_json_name = f"{base_name}-result-{timestamp}.json"
            result_json_path = os.path.join(processed_dir, result_json_name)
            with open(result_json_path, "w", encoding="utf-8") as jf:
                _json.dump(result_dict, jf, ensure_ascii=False, indent=2)
            result_dict['result_path'] = result_json_path
        except Exception:
            logging.exception("Failed to write result JSON to processed/")
    except Exception:
        logging.exception("Error while moving files to processed/")

    return result_dict


@app.post("/extract-json-stream")
async def extract_stream_endpoint(req: ExtractRequest):
    """Endpoint to extract structured JSON with progress streaming via SSE.
    
    Returns Server-Sent Events with progress updates and final result.
    """
    async def progress_generator():
        progress_queue = queue.Queue()
        
        def on_progress(update: ProgressUpdate):
            progress_queue.put(update.to_dict())
        
        # Run extraction in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        
        try:
            readme_text = None
            path = None
            owner = None
            repo = None
            readme_raw_link = None
            
            if req.repo_url:
                logging.info("extract-stream: received repo_url=%s", req.repo_url)
                
                # Yield initial download progress
                yield f"data: {_json.dumps({'type': 'progress', 'stage': 'downloading', 'status': 'in_progress', 'percentage': 10, 'message': 'Downloading README...'})}\n\n"
                
                # Extract owner/repo from URL
                import re
                # Clean URL
                clean_url = req.repo_url.strip().rstrip("/")
                # Regex to match owner and repo, handling optional .git and subpaths
                # Matches:
                # https://github.com/owner/repo
                # https://github.com/owner/repo.git
                # https://github.com/owner/repo/tree/main
                # https://github.com/owner/repo/blob/main/README.md
                match = re.match(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)", clean_url)
                
                if match:
                    owner = match.group("owner")
                    repo = match.group("repo")
                    # Remove .git if present in repo name
                    if repo.endswith(".git"):
                        repo = repo[:-4]
                    logging.info("Extracted owner=%s, repo=%s", owner, repo)
                else:
                    logging.warning("Failed to extract owner/repo from URL: %s", req.repo_url)
                
                dl = ReadmeDownloader()
                try:
                    logging.info("extract-stream: starting download for %s", req.repo_url)
                    # Run download in executor to avoid blocking the loop
                    path = await loop.run_in_executor(None, dl.download, req.repo_url, None)
                    logging.info("extract-stream: downloaded README to %s", path)
                    
                    # Yield download complete progress
                    yield f"data: {_json.dumps({'type': 'progress', 'stage': 'downloading', 'status': 'completed', 'percentage': 20, 'message': 'Download complete'})}\n\n"
                    
                    # Use the actual URL from the downloader if available
                    if dl.readme_url:
                        readme_raw_link = dl.readme_url
                    elif owner and repo:
                        # Fallback construction
                        readme_raw_link = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{os.path.basename(path)}"
                except Exception as exc:
                    logging.exception("extract-stream: failed to download: %s", exc)
                    yield f"data: {_json.dumps({'error': str(exc), 'type': 'error'})}\n\n"
                    return
                
                with open(path, "rb") as f:
                    data = f.read()
                try:
                    readme_text = data.decode("utf-8")
                except Exception:
                    readme_text = data.decode("utf-8", errors="replace")
            elif req.readme_text:
                readme_text = req.readme_text
            else:
                yield f"data: {_json.dumps({'error': 'Either repo_url or readme_text required', 'type': 'error'})}\n\n"
                return
            
            # Load system prompt
            system_prompt_text = None
            if req.system_prompt:
                system_prompt_text = req.system_prompt
            else:
                local_path = SYSTEM_PROMPT_PATH
                if os.path.exists(local_path):
                    try:
                        with open(local_path, "r", encoding="utf-8") as spf:
                            system_prompt_text = spf.read()
                    except Exception:
                        pass
            
            # Run extraction with progress callback
            # We use run_in_executor but we don't await it immediately so we can poll the queue
            logging.info(f"Calling extract_json_from_readme with owner={owner}, repo={repo}, readme_raw_link={readme_raw_link}")
            future = loop.run_in_executor(
                None,
                extract_json_from_readme,
                readme_text,
                req.schema_path,
                req.example_json,
                req.model,
                system_prompt_text,
                path,
                req.max_tokens or DEFAULT_MAX_TOKENS,
                req.temperature or DEFAULT_TEMPERATURE,
                on_progress,
                owner,
                repo,
                readme_raw_link,
            )
            
            # Poll queue while future is running
            while not future.done():
                while not progress_queue.empty():
                    try:
                        update = progress_queue.get_nowait()
                        yield f"data: {_json.dumps({'type': 'progress', **update})}\n\n"
                    except queue.Empty:
                        break
                await asyncio.sleep(0.1)
            
            # Yield any remaining updates after future completes
            while not progress_queue.empty():
                try:
                    update = progress_queue.get_nowait()
                    yield f"data: {_json.dumps({'type': 'progress', **update})}\n\n"
                except queue.Empty:
                    break
            
            # Get result (or raise exception if failed)
            result = await future
            
            # Yield final result
            result_dict = result.to_dict()
            if path:
                result_dict['saved_path'] = path
            
            # Save to MongoDB + File backup with proper naming
            # MongoDB is primary storage (source of truth)
            # File backup is automatic as failsafe with owner-repo-timestamp naming
            try:
                logging.info("Attempting to save result to MongoDB and file backup...")
                
                # Extract repository info for proper file naming
                repo_name = result_dict.get("parsed", {}).get("metadata", {}).get("repository_name", "evaluation")
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                repo_clean = repo_name.lower().replace(" ", "-")
                filename = f"{repo_clean}-{timestamp}.json"
                
                # Save to MongoDB using MongoDBHandler
                try:
                    handler = MongoDBHandler()
                    mongo_id = handler.insert_one(result_dict)
                    handler.disconnect()
                    
                    result_dict["mongo_id"] = mongo_id
                    if mongo_id:
                        logging.info(f"✓ Result saved to MongoDB with ID: {mongo_id}")
                        yield f"data: {_json.dumps({'type': 'database', 'status': 'saved', 'mongo_id': mongo_id})}\n\n"
                    else:
                        logging.warning("MongoDB save failed")
                        yield f"data: {_json.dumps({'type': 'database', 'status': 'failed', 'message': 'Failed to save to MongoDB'})}\n\n"
                except ValueError as e:
                    logging.warning(f"MongoDB configuration error: {e}")
                    yield f"data: {_json.dumps({'type': 'database', 'status': 'skipped', 'message': str(e)})}\n\n"
                except Exception as mongo_exc:
                    logging.exception(f"MongoDB save failed: {mongo_exc}")
                    yield f"data: {_json.dumps({'type': 'database', 'status': 'failed', 'error': str(mongo_exc)})}\n\n"
                
                # Save to file as backup with proper naming
                try:
                    processed_dir = Path("data/processed")
                    processed_dir.mkdir(exist_ok=True, parents=True)
                    file_path = processed_dir / filename
                    with open(file_path, "w", encoding="utf-8") as f:
                        _json.dump(result_dict, f, indent=2, ensure_ascii=False)
                    logging.info(f"✓ Result also saved to file: {file_path}")
                    yield f"data: {_json.dumps({'type': 'file_backup', 'status': 'saved', 'filename': filename, 'path': str(file_path)})}\n\n"
                except Exception as file_exc:
                    logging.warning(f"Error saving file backup: {file_exc}")
                    yield f"data: {_json.dumps({'type': 'file_backup', 'status': 'failed', 'error': str(file_exc)})}\n\n"
                
            except Exception as db_exc:
                logging.exception("Error in save process: %s", db_exc)
                yield f"data: {_json.dumps({'type': 'database_error', 'error': str(db_exc)})}\n\n"
            
            # Auto-render the evaluation to natural language as final step
            if result_dict.get('validation_ok') and result_dict.get('parsed'):
                try:
                    # Yield rendering progress
                    yield f"data: {_json.dumps({'type': 'progress', 'stage': 'rendering', 'status': 'in_progress', 'percentage': 90, 'message': 'Generating report...'})}\n\n"

                    # Use the same style as render-evaluation
                    default_style = (
                        "Create a professional, clear summary of this README evaluation. "
                        "Organize by category with scores and key insights. "
                        "Make it concise and suitable for sharing with developers."
                    )
                    
                    rendered = render_from_json(
                        result_dict['parsed'],
                        style_instructions=default_style,
                        model=req.model,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        temperature=RENDER_TEMPERATURE,
                    )
                    
                    # Yield rendered text
                    yield f"data: {_json.dumps({'type': 'rendered', 'rendered': rendered})}\n\n"
                except Exception as render_exc:
                    logging.exception("Error rendering evaluation in extract-stream")
                    yield f"data: {_json.dumps({'type': 'render_error', 'error': str(render_exc)})}\n\n"
            
            # Yield final result LAST so progress hits 100% only when everything is done
            yield f"data: {_json.dumps({'type': 'result', 'result': result_dict})}\n\n"
            
        except Exception as exc:
            logging.exception("Error in extract-stream")
            yield f"data: {_json.dumps({'error': str(exc), 'type': 'error'})}\n\n"
    
    return StreamingResponse(progress_generator(), media_type="text/event-stream")


@app.post("/render")
def render_endpoint(req: RenderRequest):
    try:
        result = render_from_json(
            req.json_object,
            style_instructions=req.style_instructions,
            model=req.model,
            max_tokens=req.max_tokens or 512,
            temperature=req.temperature or 0.1,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/render-evaluation")
def render_evaluation_endpoint(req: EvaluationRequest):
    """Transform evaluation JSON into natural language text.
    
    This endpoint takes the structured evaluation result and converts it to
    human-readable text that can be displayed in the frontend.
    
    Args:
        evaluation_json: The structured evaluation result from /extract-json
        style_instructions: Optional custom style instructions for the LLM
        model: Optional model name (if None, uses fallback text generation)
        max_tokens: Maximum tokens for the response
        temperature: Temperature for model generation
    
    Returns:
        {
            "text": "Human-readable evaluation text",
            "prompt": "The prompt used to generate the text (if model was called)",
            "model_output": "Raw model output (if model was called)"
        }
    """
    try:
        # Default style instructions for evaluation rendering
        default_style = (
            "Create a professional, clear summary of this README evaluation. "
            "Organize by category with scores and key insights. "
            "Make it concise and suitable for sharing with developers."
        )
        
        style = req.style_instructions or default_style
        
        result = render_from_json(
            req.evaluation_json,
            style_instructions=style,
            model=req.model,
            max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
            temperature=req.temperature or RENDER_TEMPERATURE,
        )
        return result
    except Exception as exc:
        logging.exception("Error in render-evaluation endpoint")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/jobs")
def create_job_endpoint(req: JobRequest, background_tasks: BackgroundTasks):
    """Create a job and run the pipeline in background. Returns job id and initial status file path."""
    runner = PipelineRunner()
    params = req.model and req.dict() or req.dict()
    job = runner.new_job(params)
    job_id = job["id"]
    # schedule background execution
    background_tasks.add_task(runner.run, job_id, params)
    return {"job_id": job_id, "status_path": os.path.join("data", "processing", "jobs", f"{job_id}.json")}


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    path = os.path.join(os.getcwd(), "data", "processing", "jobs", f"{job_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Cache Management Endpoints


@app.get("/cache/stats")
def get_cache_stats():
    """Get statistics about cache directories.

    Returns information about cache usage, file count, and oldest files.
    Useful for monitoring cache growth.
    """
    cache_mgr = get_cache_manager()
    return cache_mgr.get_stats()


@app.post("/cache/cleanup")
def cleanup_cache(older_than_hours: int = CACHE_MAX_AGE_HOURS, keep_jobs: bool = True):
    """Clean up old cache files (default: older than 24 hours).

    Args:
        older_than_hours: Only delete files older than this many hours
        keep_jobs: If true, preserve processing/jobs/ directory for active jobs

    Returns:
        Cleanup results and statistics
    """
    cache_mgr = get_cache_manager(max_age_hours=older_than_hours)
    deleted = cache_mgr.cleanup_old_files(dry_run=False)
    stats_after = cache_mgr.get_stats()

    return {
        "status": "cleaned",
        "deleted_count": len(deleted["processing"]) + len(deleted["processed"]),
        "deleted": deleted,
        "stats_after": stats_after,
    }


@app.delete("/cache/cleanup-job/{job_id}")
def cleanup_job_cache(job_id: str):
    """Clean up all files associated with a specific job.

    This removes temporary files created during job execution from
    both processing/ and processed/ directories, but keeps MongoDB records.

    Args:
        job_id: UUID of the job to clean up

    Returns:
        Cleanup results
    """
    cache_mgr = get_cache_manager()
    result = cache_mgr.cleanup_job(job_id, dry_run=False)

    return {
        "status": "cleaned",
        "job_id": job_id,
        "deleted_files": result["deleted_files"],
        "errors": result["errors"],
    }


@app.post("/cache/cleanup-all")
def cleanup_all_cache(keep_jobs: bool = True):
    """Completely clear all cache files.

    Warning: This removes all temporary files from processing/ and processed/.
    MongoDB records are NOT affected - they remain the source of truth.

    Args:
        keep_jobs: If true, preserve processing/jobs/ for active job status

    Returns:
        Cleanup results and statistics
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


class SaveFileRequest(BaseModel):
    """Request model for saving evaluation results to disk."""
    result: dict
    owner: Optional[str] = None
    repo: Optional[str] = None
    custom_filename: Optional[str] = None


@app.post("/save-to-file")
def save_result_to_file(request: SaveFileRequest):
    """Save evaluation result to disk with proper naming convention.
    
    Supports three naming modes:
    1. Custom filename (if provided): uses as-is
    2. Owner + Repo: generates "{owner}-{repo}-{timestamp}.json"
    3. Auto-extract: extracts from result['parsed']['metadata']['repository_name']
    
    Args:
        result: Evaluation result dictionary (from /extract-json-stream)
        owner: Optional repository owner (e.g., "keras-team")
        repo: Optional repository name (e.g., "keras")
        custom_filename: Optional custom filename (overrides other naming modes)
    
    Returns:
        Success status with file path
        
    Example:
        POST /save-to-file
        {
            "result": {...},
            "owner": "keras-team",
            "repo": "keras"
        }
    """
    try:
        # Create processed directory if it doesn't exist
        processed_dir = Path("data/processed")
        processed_dir.mkdir(exist_ok=True, parents=True)
        
        # Determine filename
        if request.custom_filename:
            filename = request.custom_filename
        elif request.owner and request.repo:
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
            owner_clean = request.owner.lower().replace(" ", "-")
            repo_clean = request.repo.lower().replace(" ", "-")
            filename = f"{owner_clean}-{repo_clean}-{timestamp}.json"
        else:
            # Extract repository name from result metadata
            try:
                repo_name = request.result.get("parsed", {}).get("metadata", {}).get("repository_name", "evaluation")
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                repo_clean = repo_name.lower().replace(" ", "-")
                filename = f"{repo_clean}-{timestamp}.json"
            except Exception:
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                filename = f"evaluation-{timestamp}.json"
        
        # Save to file
        file_path = processed_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            _json.dump(request.result, f, indent=2, ensure_ascii=False)
        
        logging.info(f"Evaluation saved to {file_path}")
        
        return {
            "status": "success",
            "message": f"Result saved to disk",
            "file_path": str(file_path),
            "filename": filename
        }
    
    except Exception as e:
        logging.exception(f"Error saving result to file: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving to file: {str(e)}")
