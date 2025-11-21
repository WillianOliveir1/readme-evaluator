"""Small runner to build prompts (extraction + render) and optionally call Gemini (GenAI) inference.

Usage examples:
  python backend/run_pipeline.py --readme data/samples/example1_readme.md --schema schemas/taxonomia.schema.json
  python backend/run_pipeline.py --readme path/to/README.md --call-model --model qwen2.5-7b-instruct
"""
import argparse
import json
import os
from pathlib import Path

from backend.evaluate.extractor import extract_json_from_readme
from backend.config import (
    DEFAULT_MODEL, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE,
    SCHEMA_PATH, EXAMPLE_JSON_PATH
)

# Load .env from project root when running the CLI directly so local
# development keys are available (GEMINI_API_KEY etc.).
try:
    from dotenv import load_dotenv
    _proj_root = Path(__file__).resolve().parents[1]
    load_dotenv(_proj_root / ".env")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", required=True, help="Path to README file to extract from")
    parser.add_argument("--schema", default=SCHEMA_PATH, help="Path to JSON Schema file")
    parser.add_argument("--example", default=EXAMPLE_JSON_PATH, help="Optional example JSON (few-shot)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name for Gemini/GenAI inference")
    parser.add_argument("--call-model", action="store_true", help="If set, call the Gemini (GenAI) API (requires GEMINI_API_KEY env var)")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--system-prompt-file", default=None, help="Path to a SYSTEM prompt file to include at top of prompt")
    parser.add_argument("--system-prompt", default=None, help="Inline system prompt text (alternative to file)")
    args = parser.parse_args()

    with open(args.readme, "r", encoding="utf-8") as f:
        readme_text = f.read()

    example_json = None
    if args.example and Path(args.example).exists():
        with open(args.example, "r", encoding="utf-8") as f:
            try:
                example_json = json.load(f)
            except Exception:
                example_json = None

    # Load system prompt if provided
    system_prompt = None
    if args.system_prompt_file:
        try:
            with open(args.system_prompt_file, "r", encoding="utf-8") as spf:
                system_prompt = spf.read()
        except Exception as e:
            print(f"Could not read system prompt file: {e}")
    elif args.system_prompt:
        system_prompt = args.system_prompt

    print(f"--- Processing README: {args.readme} ---")
    
    # Use the centralized extractor logic
    # If --call-model is NOT set, we pass model=None to extract_json_from_readme,
    # which will build the prompt but skip the model call.
    model_to_use = args.model if args.call_model else None
    
    result = extract_json_from_readme(
        readme_text=readme_text,
        schema_path=args.schema,
        example_json=example_json,
        model=model_to_use,
        system_prompt=system_prompt,
        readme_path=args.readme,
        max_tokens=args.max_tokens,
        temperature=args.temperature
    )

    print("\n--- Prompt Preview (first 500 chars) ---")
    print(result.prompt[:500] + "..." if len(result.prompt) > 500 else result.prompt)

    if args.call_model:
        print("\n--- Model Output ---")
        if result.success:
            if result.parsed:
                print(json.dumps(result.parsed, indent=2, ensure_ascii=False))
                print(f"\nValidation Status: {'OK' if result.validation_ok else 'FAILED'}")
                if not result.validation_ok and result.validation_errors:
                    print(f"Validation Errors: {result.validation_errors}")
            else:
                print("Failed to parse JSON from model output.")
                print("Raw output:")
                print(result.model_output)
        else:
            print("Extraction failed.")
            for suggestion in result.recovery_suggestions:
                print(f"- {suggestion}")
    else:
        print("\n[Info] Run with --call-model to execute the model inference.")


if __name__ == "__main__":
    main()
