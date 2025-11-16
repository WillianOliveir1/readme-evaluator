"""Small runner to build prompts (extraction + render) and optionally call Gemini (GenAI) inference.

Usage examples:
  python backend/run_pipeline.py --readme backend/examples/example1_readme.md --schema schemas/taxonomia.schema.json
  python backend/run_pipeline.py --readme path/to/README.md --call-model --model qwen2.5-7b-instruct
"""
import argparse
import json
import os
from pathlib import Path

from backend import prompt_builder
from pathlib import Path

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
    parser.add_argument("--schema", default="schemas/taxonomia.schema.json", help="Path to JSON Schema file")
    parser.add_argument("--example", default="backend/examples/example1_output.json", help="Optional example JSON (few-shot)")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Model name for Gemini/GenAI inference")
    parser.add_argument("--call-model", action="store_true", help="If set, call the Gemini (GenAI) API (requires GEMINI_API_KEY env var)")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--system-prompt-file", default=None, help="Path to a SYSTEM prompt file to include at top of prompt")
    parser.add_argument("--system-prompt", default=None, help="Inline system prompt text (alternative to file)")
    args = parser.parse_args()

    schema_text = prompt_builder.PromptBuilder.load_schema_text(args.schema)
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

    # Prefer PromptBuilder to produce labeled sections (schema, readme, example_json)
    pb = prompt_builder.PromptBuilder(template_header=system_prompt or None, schema=schema_text, readme=readme_text)
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

    print("--- Extraction prompt preview (first 2000 chars) ---")
    print(prompt[:2000])

    if args.call_model:
        token = os.getenv("GEMINI_API_KEY")
        if not token:
            print("GEMINI_API_KEY not found in environment. Aborting model call.")
            return

        # lazy import to avoid requiring GenAI client when not calling model
        try:
            from backend.gemini_client import GeminiClient
        except ImportError as e:
            print("Could not import GeminiClient:", e)
            return

        client = GeminiClient(api_key=token)
        print("Calling model... this may take a few seconds")
        resp = client.generate(prompt, model=args.model, max_tokens=args.max_tokens, temperature=args.temperature)
        print("--- Model response ---")
        print(resp)
    else:
        print("Run with --call-model to send the prompt to a model (requires GEMINI_API_KEY env var)")


if __name__ == "__main__":
    main()
