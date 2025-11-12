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

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from backend.download.download import ReadmeDownloader
from backend.evaluate.extractor import extract_json_from_readme
from backend.present.renderer import render_from_json
from backend.db.persistence import save_to_file, save_to_mongo
from backend.hf_client import HuggingFaceClient
import json as _json


class ReadmeRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    max_tokens: Optional[int] = 25600
    temperature: Optional[float] = 0.1


class ExtractRequest(BaseModel):
    # Either provide `repo_url` to download, or `readme_text` directly.
    repo_url: Optional[str] = None
    readme_text: Optional[str] = None
    schema_path: Optional[str] = "schemas/taxonomia.schema.json"
    example_json: Optional[dict] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.0


class RenderRequest(BaseModel):
    json_object: dict
    model: Optional[str] = None
    style_instructions: Optional[str] = None
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.1


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
            {"path": "/render", "method": "POST", "desc": "render JSON to human text"},
            {"path": "/generate", "method": "POST", "desc": "call HF model (requires token)"},
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
    dl = ReadmeDownloader()
    try:
        # download writes a file and returns its path
        path = dl.download(req.repo_url, dest_path=None, branch=req.branch)
        # read file as text (try utf-8, fallback with replacement)
        with open(path, "rb") as f:
            data = f.read()
        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("utf-8", errors="replace")
        filename = os.path.basename(path)
        # cleanup file
        try:
            os.remove(path)
        except Exception:
            pass
        return {"filename": filename, "content": text}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/generate")
def generate_endpoint(req: GenerateRequest):
    """Simple endpoint to call a Hugging Face model via the Inference API.

    Expects HUGGINGFACE_API_TOKEN in the environment. This is minimal scaffolding
    to be expanded later (streaming, async client, model selection, safety
    checks, rate limiting, etc.).
    """
    client = HuggingFaceClient()
    try:
        output = client.generate(req.prompt, model=req.model, max_tokens=req.max_tokens or 256, temperature=req.temperature or 0.0)
        return {"model": req.model or client.default_model, "output": output}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/extract-json")
def extract_endpoint(req: ExtractRequest):
    """Endpoint to extract structured JSON from a README.

    Either `repo_url` or `readme_text` must be provided. If `model` is set the
    endpoint will call the model; otherwise it will return the built prompt.
    """
    readme_text = None
    if req.repo_url:
        dl = ReadmeDownloader()
        path = dl.download(req.repo_url, dest_path=None, branch=None)
        with open(path, "rb") as f:
            data = f.read()
        try:
            readme_text = data.decode("utf-8")
        except Exception:
            readme_text = data.decode("utf-8", errors="replace")
        try:
            os.remove(path)
        except Exception:
            pass
    elif req.readme_text:
        readme_text = req.readme_text
    else:
        raise HTTPException(status_code=400, detail="Either repo_url or readme_text must be provided")

    res = extract_json_from_readme(
        readme_text,
        schema_path=req.schema_path,
        example_json=req.example_json,
        model=req.model,
        max_tokens=req.max_tokens or 2048,
        temperature=req.temperature or 0.0,
    )

    return res


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
