"""Pydantic request/response models shared across routers."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

from backend.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    RENDER_MAX_TOKENS,
    RENDER_TEMPERATURE,
    SCHEMA_PATH,
)


class ReadmeRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = None
    save_to_examples: Optional[bool] = True


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    max_tokens: Optional[int] = GENERATION_MAX_TOKENS
    temperature: Optional[float] = GENERATION_TEMPERATURE


class ExtractRequest(BaseModel):
    repo_url: Optional[str] = None
    readme_text: Optional[str] = None
    schema_path: Optional[str] = SCHEMA_PATH
    example_json: Optional[dict] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = DEFAULT_TEMPERATURE
    branch: Optional[str] = None


class RenderRequest(BaseModel):
    json_object: dict
    model: Optional[str] = None
    style_instructions: Optional[str] = None
    max_tokens: Optional[int] = RENDER_MAX_TOKENS
    temperature: Optional[float] = RENDER_TEMPERATURE


class EvaluationRequest(BaseModel):
    evaluation_json: dict
    style_instructions: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = RENDER_TEMPERATURE


class JobRequest(BaseModel):
    repo_url: Optional[str] = None
    readme_text: Optional[str] = None
    schema_path: Optional[str] = SCHEMA_PATH
    example_json: Optional[dict] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = DEFAULT_TEMPERATURE
    branch: Optional[str] = None


class SaveFileRequest(BaseModel):
    """Request model for saving evaluation results to disk."""
    result: dict
    owner: Optional[str] = None
    repo: Optional[str] = None
    custom_filename: Optional[str] = None
