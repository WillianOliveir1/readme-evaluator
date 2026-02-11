"""Router for saving evaluation results to disk."""
from __future__ import annotations

import json as _json
import logging
import os

log = logging.getLogger(__name__)
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.models import SaveFileRequest

router = APIRouter(tags=["files"])


@router.post("/save-to-file")
def save_result_to_file(request: SaveFileRequest):
    """Save evaluation result to disk with proper naming convention.

    Supports three naming modes:
    1. Custom filename (if provided): sanitized to basename only
    2. Owner + Repo: generates ``{owner}-{repo}-{timestamp}.json``
    3. Auto-extract: extracts from ``result['parsed']['metadata']['repository_name']``
    """
    # Validate custom_filename BEFORE the try/except so HTTPException
    # is not swallowed by the generic handler.
    if request.custom_filename:
        filename = os.path.basename(request.custom_filename)
        if not filename or filename.startswith("."):
            raise HTTPException(status_code=400, detail="Invalid filename")

    try:
        processed_dir = Path("data/processed")
        processed_dir.mkdir(exist_ok=True, parents=True)

        if request.custom_filename:
            filename = os.path.basename(request.custom_filename)
        elif request.owner and request.repo:
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
            owner_clean = request.owner.lower().replace(" ", "-")
            repo_clean = request.repo.lower().replace(" ", "-")
            filename = f"{owner_clean}-{repo_clean}-{timestamp}.json"
        else:
            try:
                repo_name = (
                    request.result.get("parsed", {})
                    .get("metadata", {})
                    .get("repository_name", "evaluation")
                )
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                repo_clean = repo_name.lower().replace(" ", "-")
                filename = f"{repo_clean}-{timestamp}.json"
            except Exception:
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                filename = f"evaluation-{timestamp}.json"

        file_path = processed_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            _json.dump(request.result, f, indent=2, ensure_ascii=False)

        log.info("Evaluation saved to %s", file_path)

        return {
            "status": "success",
            "message": "Result saved to disk",
            "file_path": str(file_path),
            "filename": filename,
        }

    except Exception as e:
        log.exception("Error saving result to file: %s", e)
        raise HTTPException(status_code=500, detail=f"Error saving to file: {str(e)}")
