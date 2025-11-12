"""Presentation utilities: render validated JSON into human readable text.

This module uses `backend.prompt_builder` to create a render prompt and
optionally calls an LLM via `backend.hf_client`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from backend import prompt_builder
from backend.hf_client import HuggingFaceClient


def render_from_json(
    json_obj: Dict[str, Any],
    style_instructions: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """Render a natural-language text from a validated JSON object.

    Returns dict with keys 'prompt' and 'model_output' (if model used) and
    'text' as final rendered text (fallback simple serializer if no model).
    """
    json_text = json.dumps(json_obj, ensure_ascii=False, indent=2)

    # Build render prompt using PromptBuilder so the JSON section is labeled
    pb = prompt_builder.PromptBuilder(template_header="You are a multi-format writer.")
    pb.add_part("INPUT_JSON", json_text)
    instr = style_instructions or "Render a clear, friendly README-style summary from the JSON. Keep it concise and human-readable."
    footer = "Produce the requested text output. Do not include the JSON again."
    prompt = pb.build(instruction=f"Style instructions: {instr}", footer=footer)
    result = {"prompt": prompt}

    if model:
        client = HuggingFaceClient()
        out = client.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        result["model_output"] = out
        result["text"] = out
    else:
        # Simple fallback: convert key fields to readable text
        lines = []
        if isinstance(json_obj, dict):
            for k, v in json_obj.items():
                lines.append(f"{k}: {v}")
        else:
            lines.append(str(json_obj))
        result["text"] = "\n".join(lines)

    return result
