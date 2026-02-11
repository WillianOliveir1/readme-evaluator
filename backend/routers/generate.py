"""Router for generate endpoint (LLM call)."""

from fastapi import APIRouter, HTTPException, Request

from backend.llm_factory import get_llm_client
from backend.models import GenerateRequest
from backend.rate_limit import limiter, EXPENSIVE_LIMIT

router = APIRouter(tags=["generate"])


@router.post("/generate")
@limiter.limit(EXPENSIVE_LIMIT)
def generate_endpoint(request: Request, req: GenerateRequest):
    """Call the configured LLM provider (Gemini, Ollama, …).

    The provider is selected by the LLM_PROVIDER env var.
    """
    try:
        client = get_llm_client()
        output = client.generate(
            req.prompt,
            model=req.model,
            max_tokens=req.max_tokens or 256,
            temperature=req.temperature or 0.0,
        )
        return {"model": req.model or client.default_model, "output": output}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
