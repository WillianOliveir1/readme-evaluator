"""Small runner to build prompts (extraction + render) and optionally call Hugging Face Inference.

Usage examples:
  python backend/run_pipeline.py --readme backend/examples/example1_readme.md --schema schemas/taxonomia.schema.json
  python backend/run_pipeline.py --readme path/to/README.md --call-model --model qwen2.5-7b-instruct
"""
import argparse
import json
import os
from pathlib import Path

from backend import prompt_builder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", required=True, help="Path to README file to extract from")
    parser.add_argument("--schema", default="schemas/taxonomia.schema.json", help="Path to JSON Schema file")
    parser.add_argument("--example", default="backend/examples/example1_output.json", help="Optional example JSON (few-shot)")
    parser.add_argument("--model", default="qwen2.5-7b-instruct", help="Model name for HF inference")
    parser.add_argument("--call-model", action="store_true", help="If set, call the Hugging Face Inference API (requires HUGGINGFACE_API_TOKEN env var)")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.0)
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

    # Prefer PromptBuilder to produce labeled sections (schema, readme, example_json)
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

    print("--- Extraction prompt preview (first 2000 chars) ---")
    print(prompt[:2000])

    if args.call_model:
        token = os.getenv("HUGGINGFACE_API_TOKEN")
        if not token:
            print("HUGGINGFACE_API_TOKEN not found in environment. Aborting model call.")
            return

        # lazy import to avoid requiring HF client when not calling model
        try:
            from backend.hf_client import HuggingFaceClient
        except ImportError as e:
            print("Could not import HuggingFaceClient:", e)
            return

        client = HuggingFaceClient(token=token)
        print("Calling model... this may take a few seconds")
        resp = client.generate(prompt, model=args.model, max_tokens=args.max_tokens, temperature=args.temperature)
        # The HF client returns a string (best effort)
        print("--- Model response ---")
        print(resp)
    else:
        print("Run with --call-model to send the prompt to a model (requires HUGGINGFACE_API_TOKEN env var)")


if __name__ == "__main__":
    main()
