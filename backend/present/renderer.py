"""Presentation utilities: render validated JSON into human readable text.

This module uses ``backend.prompt_builder`` to create a render prompt and
optionally calls the configured LLM via ``backend.llm_factory``.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional
import os

from backend import prompt_builder
from backend.llm_factory import get_llm_client
from backend.config import RENDER_MAX_TOKENS, RENDER_TEMPERATURE, RENDERER_PROMPT_PATH


def render_from_json(
    json_obj: Dict[str, Any],
    style_instructions: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = RENDER_MAX_TOKENS,
    temperature: float = RENDER_TEMPERATURE,
) -> Dict[str, Any]:
    """Render a natural-language text from a validated JSON object.

    Returns dict with keys 'prompt' and 'model_output' (if model used) and
    'text' as final rendered text (fallback simple serializer if no model).
    """
    json_text = json.dumps(json_obj, ensure_ascii=False, indent=2)

    # Load system prompt from file
    try:
        with open(RENDERER_PROMPT_PATH, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except Exception:
        system_prompt = "You are a multi-format writer. Convert the JSON data into a readable Markdown report."

    # Build render prompt using PromptBuilder
    pb = prompt_builder.PromptBuilder(template_header=system_prompt)
    pb.add_part("EVALUATION_DATA_JSON", json_text)
    
    if style_instructions:
        pb.add_part("ADDITIONAL_STYLE_INSTRUCTIONS", style_instructions)

    # Use empty footer to disable the default JSON-specific footer from PromptBuilder
    prompt = pb.build(instruction="Generate the Markdown report.", footer="")
    result = {"prompt": prompt}

    if model:
        client = get_llm_client()
        out = client.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        result["model_output"] = out
        result["text"] = out
    else:
        # Simple fallback: convert key fields to readable text
        lines = []
        if isinstance(json_obj, dict):
            for k, v in json_obj.items():
                lines.append(f"**{k}**: {v}")
        else:
            lines.append(str(json_obj))
        result["text"] = "\n\n".join(lines)

    return result
