"""Router for JSON extraction endpoints (sync and SSE stream)."""

import asyncio
import functools
import json as _json
import logging
import os

log = logging.getLogger(__name__)
import queue
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.requests import Request
from fastapi.responses import StreamingResponse

from backend.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    RENDER_TEMPERATURE,
    SCHEMA_PATH,
    SYSTEM_PROMPT_PATH,
)
from backend.db.mongodb_handler import MongoDBHandler
from backend.download.download import ReadmeDownloader
from backend.evaluate.extractor import extract_json_from_readme
from backend.evaluate.progress import ProgressUpdate
from backend.models import ExtractRequest
from backend.present.renderer import render_from_json
from backend.rate_limit import limiter, EXPENSIVE_LIMIT

router = APIRouter(tags=["extract"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_system_prompt(custom: str | None) -> str | None:
    """Return system prompt text from request or default file."""
    if custom:
        return custom
    if os.path.exists(SYSTEM_PROMPT_PATH):
        try:
            with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# POST /extract-json
# ---------------------------------------------------------------------------

@router.post("/extract-json")
@limiter.limit(EXPENSIVE_LIMIT)
def extract_endpoint(request: Request, req: ExtractRequest):
    """Extract structured JSON from a README.

    Either ``repo_url`` or ``readme_text`` must be provided.  When ``model``
    is set the endpoint calls the model; otherwise it returns the built prompt.
    """
    readme_text = None
    path = None

    if req.repo_url:
        log.info("extract-json: received repo_url=%s", req.repo_url)
        dl = ReadmeDownloader()
        try:
            path = dl.download(req.repo_url, branch=req.branch)
            log.info("extract-json: downloaded README to %s", path)
        except Exception as exc:
            log.exception("extract-json: download failed for %s", req.repo_url)
            raise HTTPException(status_code=502, detail=f"Failed to download README: {exc}")
        with open(path, "rb") as f:
            data = f.read()
        try:
            readme_text = data.decode("utf-8")
        except Exception:
            readme_text = data.decode("utf-8", errors="replace")
        log.info(
            "extract-json: README length=%d saved_path=%s",
            len(readme_text) if readme_text else 0,
            path,
        )
    elif req.readme_text:
        readme_text = req.readme_text
    else:
        raise HTTPException(status_code=400, detail="Either repo_url or readme_text must be provided")

    system_prompt_text = _load_system_prompt(req.system_prompt)

    # If the client requested a model call but GEMINI_API_KEY is not set,
    # skip calling the model.
    if req.model and not os.environ.get("GEMINI_API_KEY"):
        result = extract_json_from_readme(
            readme_text,
            schema_path=req.schema_path or SCHEMA_PATH,
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
        schema_path=req.schema_path or SCHEMA_PATH,
        example_json=req.example_json,
        model=req.model,
        system_prompt=system_prompt_text,
        readme_path=path,
        max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
        temperature=req.temperature or DEFAULT_TEMPERATURE,
    )

    result_dict = result.to_dict()

    if path:
        result_dict["saved_path"] = path

    # Move README and result to processed/ for auditability.
    try:
        processed_dir = os.path.join(os.getcwd(), "data", "processed")
        os.makedirs(processed_dir, exist_ok=True)

        if path:
            try:
                dest_readme = os.path.join(processed_dir, os.path.basename(path))
                shutil.move(path, dest_readme)
                result_dict["processed_readme"] = dest_readme
                result_dict["saved_path"] = dest_readme
            except Exception:
                log.exception("Failed to move README %s to processed/", path)

        try:
            base_name = os.path.splitext(
                os.path.basename(result_dict.get("saved_path", "result"))
            )[0]
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            result_json_name = f"{base_name}-result-{timestamp}.json"
            result_json_path = os.path.join(processed_dir, result_json_name)
            with open(result_json_path, "w", encoding="utf-8") as jf:
                _json.dump(result_dict, jf, ensure_ascii=False, indent=2)
            result_dict["result_path"] = result_json_path
        except Exception:
            log.exception("Failed to write result JSON to processed/")
    except Exception:
        log.exception("Error while moving files to processed/")

    return result_dict


# ---------------------------------------------------------------------------
# POST /extract-json-stream  (SSE)
# ---------------------------------------------------------------------------

@router.post("/extract-json-stream")
@limiter.limit(EXPENSIVE_LIMIT)
async def extract_stream_endpoint(request: Request, req: ExtractRequest):
    """Extract structured JSON with progress streaming via SSE."""

    async def progress_generator():
        progress_queue: queue.Queue = queue.Queue()

        def on_progress(update: ProgressUpdate):
            progress_queue.put(update.to_dict())

        loop = asyncio.get_event_loop()

        try:
            readme_text = None
            path = None
            owner = None
            repo = None
            readme_raw_link = None

            if req.repo_url:
                log.info("extract-stream: received repo_url=%s", req.repo_url)

                yield f"data: {_json.dumps({'type': 'progress', 'stage': 'downloading', 'status': 'in_progress', 'percentage': 10, 'message': 'Downloading README...'})}\n\n"

                clean_url = req.repo_url.strip().rstrip("/")
                match = re.match(
                    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)",
                    clean_url,
                )
                if match:
                    owner = match.group("owner")
                    repo = match.group("repo")
                    if repo.endswith(".git"):
                        repo = repo[:-4]

                dl = ReadmeDownloader()
                try:
                    path = await loop.run_in_executor(
                        None, functools.partial(dl.download, req.repo_url)
                    )
                    yield f"data: {_json.dumps({'type': 'progress', 'stage': 'downloading', 'status': 'completed', 'percentage': 20, 'message': 'Download complete'})}\n\n"

                    if dl.readme_url:
                        readme_raw_link = dl.readme_url
                    elif owner and repo:
                        readme_raw_link = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{os.path.basename(path)}"
                except Exception as exc:
                    log.exception("extract-stream: failed to download: %s", exc)
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

            system_prompt_text = _load_system_prompt(req.system_prompt)

            future = loop.run_in_executor(
                None,
                functools.partial(
                    extract_json_from_readme,
                    readme_text,
                    schema_path=req.schema_path or SCHEMA_PATH,
                    example_json=req.example_json,
                    model=req.model,
                    system_prompt=system_prompt_text,
                    readme_path=path,
                    max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
                    temperature=req.temperature or DEFAULT_TEMPERATURE,
                    progress_callback=on_progress,
                    owner=owner,
                    repo=repo,
                    readme_raw_link=readme_raw_link,
                ),
            )

            while not future.done():
                while not progress_queue.empty():
                    try:
                        update = progress_queue.get_nowait()
                        yield f"data: {_json.dumps({'type': 'progress', **update})}\n\n"
                    except queue.Empty:
                        break
                await asyncio.sleep(0.1)

            while not progress_queue.empty():
                try:
                    update = progress_queue.get_nowait()
                    yield f"data: {_json.dumps({'type': 'progress', **update})}\n\n"
                except queue.Empty:
                    break

            result = await future
            result_dict = result.to_dict()
            if path:
                result_dict["saved_path"] = path

            # Persist ---------------------------------------------------------
            try:
                repo_name = (
                    result_dict.get("parsed", {})
                    .get("metadata", {})
                    .get("repository_name", "evaluation")
                )
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                repo_clean = repo_name.lower().replace(" ", "-")
                filename = f"{repo_clean}-{timestamp}.json"

                # MongoDB
                try:
                    handler = MongoDBHandler()
                    mongo_id = handler.insert_one(result_dict)
                    handler.disconnect()
                    result_dict["mongo_id"] = mongo_id
                    if mongo_id:
                        yield f"data: {_json.dumps({'type': 'database', 'status': 'saved', 'mongo_id': mongo_id})}\n\n"
                    else:
                        yield f"data: {_json.dumps({'type': 'database', 'status': 'failed', 'message': 'Failed to save to MongoDB'})}\n\n"
                except ValueError as e:
                    yield f"data: {_json.dumps({'type': 'database', 'status': 'skipped', 'message': str(e)})}\n\n"
                except Exception as mongo_exc:
                    log.exception("MongoDB save failed: %s", mongo_exc)
                    yield f"data: {_json.dumps({'type': 'database', 'status': 'failed', 'error': str(mongo_exc)})}\n\n"

                # File backup
                try:
                    processed_dir = Path("data/processed")
                    processed_dir.mkdir(exist_ok=True, parents=True)
                    file_path = processed_dir / filename
                    with open(file_path, "w", encoding="utf-8") as out_f:
                        _json.dump(result_dict, out_f, indent=2, ensure_ascii=False)
                    yield f"data: {_json.dumps({'type': 'file_backup', 'status': 'saved', 'filename': filename, 'path': str(file_path)})}\n\n"
                except Exception as file_exc:
                    yield f"data: {_json.dumps({'type': 'file_backup', 'status': 'failed', 'error': str(file_exc)})}\n\n"

            except Exception as db_exc:
                log.exception("Error in save process: %s", db_exc)
                yield f"data: {_json.dumps({'type': 'database_error', 'error': str(db_exc)})}\n\n"

            # Auto-render -----------------------------------------------------
            if result_dict.get("validation_ok") and result_dict.get("parsed"):
                try:
                    yield f"data: {_json.dumps({'type': 'progress', 'stage': 'rendering', 'status': 'in_progress', 'percentage': 90, 'message': 'Generating report...'})}\n\n"

                    default_style = (
                        "Create a professional, clear summary of this README evaluation. "
                        "Organize by category with scores and key insights. "
                        "Make it concise and suitable for sharing with developers."
                    )
                    rendered = render_from_json(
                        result_dict["parsed"],
                        style_instructions=default_style,
                        model=req.model,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        temperature=RENDER_TEMPERATURE,
                    )
                    yield f"data: {_json.dumps({'type': 'rendered', 'rendered': rendered})}\n\n"
                except Exception as render_exc:
                    log.exception("Error rendering evaluation in extract-stream")
                    yield f"data: {_json.dumps({'type': 'render_error', 'error': str(render_exc)})}\n\n"

            yield f"data: {_json.dumps({'type': 'result', 'result': result_dict})}\n\n"

        except Exception as exc:
            log.exception("Error in extract-stream")
            yield f"data: {_json.dumps({'error': str(exc), 'type': 'error'})}\n\n"

    return StreamingResponse(progress_generator(), media_type="text/event-stream")
