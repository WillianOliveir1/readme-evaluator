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

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from backend.readme_downloader import ReadmeDownloader


class ReadmeRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None


app = FastAPI(title="Readme Downloader API")

# Allow local Next.js dev server by default
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
