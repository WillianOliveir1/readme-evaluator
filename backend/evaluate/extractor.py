"""Evaluation utilities: extract structured JSON from README text using prompts + LLM."""
from __future__ import annotations

import json
from typing import Optional, Any, Dict

from backend import prompt_builder
from backend.hf_client import HuggingFaceClient


def extract_json_from_readme(
    readme_text: str,
    schema_path: str,
    example_json: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Build extraction prompt and call model (if model provided).

    Returns a dict with keys:
      - prompt: the built prompt string
      - model_output: raw model response (if model provided)
      - parsed: parsed JSON object if output was valid JSON, else None
    """
    schema_text = prompt_builder.PromptBuilder.load_schema_text(schema_path)

    # Use PromptBuilder with explicit labels so the prompt sections are clearly named
    pb = prompt_builder.PromptBuilder(schema=schema_text, readme=readme_text)
    if example_json is not None:
        try:
            example_str = json.dumps(example_json, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            example_str = str(example_json)
        pb.add_part("example_json", example_str)

    footer = (
        "IMPORTANT: The model must output a single JSON object, valid according to the schema above. "
        "No surrounding backticks, no markdown, no commentary."
    )

    prompt = pb.build(instruction=None, footer=footer)

    result = {"prompt": prompt}

    if model:
        client = HuggingFaceClient()
        raw = client.generate(prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        result["model_output"] = raw
        # try to parse JSON
        try:
            parsed = json.loads(raw)
            result["parsed"] = parsed
        except Exception:
            result["parsed"] = None

    return result
