"""Centralized configuration for the backend application.

This module contains all default settings, paths, and model configurations
to avoid hardcoded values scattered across the codebase.
"""
import os

# Model Configuration
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_TOKENS = 20480
DEFAULT_TEMPERATURE = 0.0

# Generation Configuration (for generic text generation)
GENERATION_MAX_TOKENS = 25600
GENERATION_TEMPERATURE = 0.1

# Rendering Configuration (for JSON to text)
RENDER_MAX_TOKENS = 512
RENDER_TEMPERATURE = 0.1

# Paths
SCHEMA_PATH = "schemas/taxonomia.schema.json"
SYSTEM_PROMPT_PATH = os.path.join("tools", "prompt_templates", "evaluator_system_prompt.txt")
EXAMPLE_JSON_PATH = "data/samples/example1_output.json"

# Cache Configuration
CACHE_MAX_AGE_HOURS = 24
