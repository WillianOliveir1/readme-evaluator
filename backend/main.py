"""FastAPI application — README Evaluator backend.

This module wires together the routers and middleware.  Business logic
lives in the ``routers/`` package; request/response models live in
``backend.models``.
"""
from __future__ import annotations

import logging
from pathlib import Path

# Load .env from repository root (if present) so GEMINI_API_KEY and other
# developer secrets can be set in a local .env file during development.
try:
    from dotenv import load_dotenv
    _proj_root = Path(__file__).resolve().parents[1]
    load_dotenv(_proj_root / ".env")
except Exception:
    pass

from backend.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from google import genai

from backend.config import API_KEY, LLM_PROVIDER
from backend.rate_limit import limiter
from backend.routers import readme, extract, render, generate, jobs, cache, files, export_pdf

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

if LLM_PROVIDER == "gemini":
    _gemini_key = os.environ.get("GEMINI_API_KEY")
    if not _gemini_key:
        log.warning(
            "GEMINI_API_KEY is not set. Endpoints that call the Gemini model "
            "(e.g. /extract-json, /generate) will not work."
        )
    else:
        log.info("GEMINI_API_KEY detected — Gemini endpoints enabled.")
elif LLM_PROVIDER == "ollama":
    log.info(
        "LLM_PROVIDER=ollama — using local Ollama at %s",
        os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
else:
    log.warning("Unknown LLM_PROVIDER '%s' — endpoints may not work.", LLM_PROVIDER)

if not os.environ.get("GITHUB_TOKEN"):
    log.info(
        "GITHUB_TOKEN is not set. GitHub API rate limit will be 60 req/h "
        "(unauthenticated). Set GITHUB_TOKEN to increase to 5 000 req/h."
    )

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Readme Evaluator API")

# Rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# CORS — allow local Next.js dev server and Docker network by default
_cors_env = os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API key authentication middleware.
# When API_KEY env var is set, every request (except health-check and CORS
# preflight) must carry a matching X-API-Key header.
@app.middleware("http")
async def authenticate(request: Request, call_next):
    if API_KEY:
        # Always allow the health-check root and CORS preflight requests
        is_public = request.url.path in ("/", "/health") or request.method == "OPTIONS"
        if not is_public:
            provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if provided != API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
    return await call_next(request)


# Lightweight request/response logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.info("Incoming request: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        log.exception(
            "Error handling request %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        raise
    log.info(
        "Response %s for %s %s",
        response.status_code,
        request.method,
        request.url.path,
    )
    return response


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Service info endpoint."""
    return {
        "service": "readme-evaluator backend",
        "endpoints": [
            {"path": "/health", "method": "GET", "desc": "deep health check"},
            {"path": "/readme", "method": "POST", "desc": "download README from GitHub"},
            {"path": "/extract-json", "method": "POST", "desc": "extract structured JSON from README"},
            {"path": "/extract-json-stream", "method": "POST", "desc": "extract JSON with progress streaming (SSE)"},
            {"path": "/render", "method": "POST", "desc": "render JSON to human text"},
            {"path": "/render-evaluation", "method": "POST", "desc": "transform evaluation JSON to natural language text"},
            {"path": "/generate", "method": "POST", "desc": "call LLM (provider set via LLM_PROVIDER env var)"},
            {"path": "/cache/stats", "method": "GET", "desc": "get cache statistics"},
            {"path": "/cache/cleanup", "method": "POST", "desc": "manually cleanup old cache files"},
            {"path": "/cache/cleanup-job/{job_id}", "method": "DELETE", "desc": "cleanup files for specific job"},
            {"path": "/jobs", "method": "GET", "desc": "list jobs with pagination and filters"},
            {"path": "/jobs", "method": "POST", "desc": "create pipeline job"},
            {"path": "/jobs/{job_id}", "method": "GET", "desc": "get job status"},
            {"path": "/export-pdf", "method": "POST", "desc": "export evaluation as PDF"},
        ],
    }


@app.get("/health")
async def health_check():
    """Deep health check — probes external dependencies.

    Returns HTTP 200 when the service is operational, with per-component
    status so monitoring tools can pinpoint failures.
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # --- LLM Provider ---
    checks["llm_provider"] = {"provider": LLM_PROVIDER}

    # --- Gemini API ---
    if LLM_PROVIDER == "gemini":
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                client = genai.Client(api_key=gemini_key)
                models = list(client.models.list())
                checks["gemini"] = {"status": "ok", "models_available": len(models)}
            except Exception as exc:
                checks["gemini"] = {"status": "error", "detail": str(exc)}
                overall_ok = False
        else:
            checks["gemini"] = {"status": "not_configured"}

    # --- Ollama ---
    if LLM_PROVIDER == "ollama":
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            import requests as _requests
            resp = _requests.get(f"{ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            checks["ollama"] = {
                "status": "ok",
                "base_url": ollama_url,
                "models_available": len(models),
            }
        except Exception as exc:
            checks["ollama"] = {"status": "error", "base_url": ollama_url, "detail": str(exc)}
            overall_ok = False

    # --- MongoDB ---
    mongodb_uri = os.environ.get("MONGODB_URI")
    if mongodb_uri:
        try:
            from pymongo import MongoClient as _MongoClient
            _client: _MongoClient = _MongoClient(mongodb_uri, serverSelectionTimeoutMS=3000)  # type: ignore[type-arg]
            _client.admin.command("ping")
            _client.close()
            checks["mongodb"] = {"status": "ok"}
        except Exception as exc:
            checks["mongodb"] = {"status": "error", "detail": str(exc)}
            overall_ok = False
    else:
        checks["mongodb"] = {"status": "not_configured"}

    # --- Data directories ---
    data_dirs = ["data/processing", "data/processed"]
    dirs_ok = all(os.path.isdir(d) for d in data_dirs)
    checks["data_dirs"] = {"status": "ok" if dirs_ok else "missing", "paths": data_dirs}
    if not dirs_ok:
        # Not critical — they are created on demand
        pass

    # --- Pipeline concurrency ---
    from backend.pipeline import get_active_jobs, MAX_CONCURRENT_PIPELINES
    active = get_active_jobs()
    checks["pipeline"] = {
        "active_jobs": len(active),
        "max_concurrent": MAX_CONCURRENT_PIPELINES,
        "active_job_ids": list(active),
    }

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_ok else "degraded",
            "checks": checks,
        },
    )


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.include_router(readme.router)
app.include_router(extract.router)
app.include_router(render.router)
app.include_router(generate.router)
app.include_router(jobs.router)
app.include_router(cache.router)
app.include_router(files.router)
app.include_router(export_pdf.router)

