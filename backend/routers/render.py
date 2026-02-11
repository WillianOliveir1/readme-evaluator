"""Router for render / render-evaluation endpoints."""

import logging

log = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Request

from backend.config import DEFAULT_MAX_TOKENS, RENDER_TEMPERATURE
from backend.models import EvaluationRequest, RenderRequest
from backend.present.renderer import render_from_json
from backend.rate_limit import limiter, EXPENSIVE_LIMIT

router = APIRouter(tags=["render"])


@router.post("/render")
@limiter.limit(EXPENSIVE_LIMIT)
def render_endpoint(request: Request, req: RenderRequest):
    """Render a JSON object into human-readable text via Gemini."""
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


@router.post("/render-evaluation")
@limiter.limit(EXPENSIVE_LIMIT)
def render_evaluation_endpoint(request: Request, req: EvaluationRequest):
    """Transform evaluation JSON into natural language text."""
    try:
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
        log.exception("Error in render-evaluation endpoint")
        raise HTTPException(status_code=500, detail=str(exc))
