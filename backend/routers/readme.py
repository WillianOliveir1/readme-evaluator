"""Router for README download endpoint."""

import os
import logging

log = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Request

from backend.download.download import ReadmeDownloader
from backend.models import ReadmeRequest
from backend.rate_limit import limiter, EXPENSIVE_LIMIT

router = APIRouter(tags=["readme"])


@router.post("/readme")
@limiter.limit(EXPENSIVE_LIMIT)
async def readme_endpoint(request: Request, req: ReadmeRequest):
    """Download a README from a GitHub repository."""
    log.info(
        "readme_endpoint: called with repo_url=%s branch=%s",
        req.repo_url,
        req.branch,
    )
    dl = ReadmeDownloader()
    try:
        path = dl.download(req.repo_url, branch=req.branch)
        with open(path, "rb") as f:
            data = f.read()
        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("utf-8", errors="replace")
        filename = os.path.basename(path)
        return {"filename": filename, "content": text, "saved_path": path}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
