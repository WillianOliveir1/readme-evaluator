"""Centralized configuration for the backend application.

This module contains all default settings, paths, and model configurations
to avoid hardcoded values scattered across the codebase.
"""
import os
from pathlib import Path

# Try to load .env file from project root
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

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
RENDERER_PROMPT_PATH = os.path.join("backend", "prompts", "renderer_system_prompt.txt")
EXAMPLE_JSON_PATH = "data/samples/example1_output.json"

# Cache Configuration
CACHE_MAX_AGE_HOURS = 24

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB", "readme_evaluator")
MONGODB_COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "evaluations")

# GitHub Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# API Authentication
# When set, every request (except GET /) must include the header:
#   X-API-Key: <value>
# When unset the API runs without authentication (convenient for local dev).
API_KEY = os.getenv("API_KEY")

# LLM Provider Configuration
# Supported: "gemini" (default), "ollama"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

# Ollama Configuration (only used when LLM_PROVIDER=ollama)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
