"""Tool: run_full_pipeline

Downloads a README from GitHub, builds the extraction prompt, optionally
calls the model (Gemini) and saves a JSON result containing prompt,
model_output and parsed JSON (if any).

Usage (from repo root):
  python tools/run_full_pipeline.py --repo https://github.com/owner/repo -o out.json --model gemini-2.5-flash

If --model is not provided the script will only build and save the prompt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run full README->JSON pipeline (download, prompt, optional model)")
    parser.add_argument("--repo", required=True, help="GitHub repo URL (e.g. https://github.com/owner/repo)")
    parser.add_argument("--branch", default=None, help="Optional branch name to download from")
    parser.add_argument("--schema", default="schemas/taxonomia.schema.json", help="Path to schema file used by PromptBuilder")
    parser.add_argument("--example", default=None, help="Optional JSON example file to include as few-shot example")
    parser.add_argument("--model", default=None, help="Model id to call (e.g. gemini-2.5-flash). If omitted, only the prompt is saved")
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--system-prompt-file", default=None, help="Path to a SYSTEM prompt file to include at top of prompt")
    parser.add_argument("--system-prompt", default=None, help="Inline system prompt text (alternative to file)")
    parser.add_argument("-o", "--output", default=None, help="Output JSON file path (default: ./backend/examples/<owner>-<repo>-result.json)")

    args = parser.parse_args(argv)

    # Import project internals (expect to be run from repo root)
    try:
        from backend.download.download import ReadmeDownloader
        from backend.evaluate.extractor import extract_json_from_readme
        from backend.prompt_builder import PromptBuilder
    except Exception as exc:
        print("Error importing backend modules. Make sure to run this from the project root and activate the venv.", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2

    out = {
        "repo_url": args.repo,
        "branch": args.branch,
        "schema_path": args.schema,
        "model": args.model,
        # use timezone-aware UTC timestamp
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    dl = ReadmeDownloader()
    try:
        path = dl.download(args.repo, dest_path=None, branch=args.branch)
    except Exception as exc:
        print(f"Failed to download README from {args.repo}: {exc}", file=sys.stderr)
        out["error"] = str(exc)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        return 3

    # read content
    with open(path, "rb") as f:
        raw = f.read()
    try:
        readme_text = raw.decode("utf-8")
    except Exception:
        readme_text = raw.decode("utf-8", errors="replace")

    out["filename"] = os.path.basename(path)
    out["readme_text_snippet"] = readme_text[:4000]
    # also include full readme text in the output (useful for debugging / local runs)
    out["readme_text"] = readme_text

    # Save a separate README file next to the JSON output so you can inspect it easily
    try:
        owner_repo = args.repo.rstrip("/\n ")
        if owner_repo.endswith('.git'):
            owner_repo = owner_repo[:-4]
        parts = owner_repo.split("/")[-2:]
        owner = parts[0] if len(parts) > 0 else "repo"
        repo = parts[1] if len(parts) > 1 else "repo"
        readme_filename = f"{owner}-{repo}-README.md"
        # if output dir known, place README there; otherwise backend/examples
        if args.output:
            readme_out_dir = os.path.dirname(args.output) or os.path.join("backend", "examples")
        else:
            readme_out_dir = os.path.join("backend", "examples")
        os.makedirs(readme_out_dir, exist_ok=True)
        readme_out_path = os.path.join(readme_out_dir, readme_filename)
        with open(readme_out_path, "w", encoding="utf-8") as rf:
            rf.write(readme_text)
        out["readme_saved_path"] = readme_out_path
    except Exception:
        # non-fatal; continue
        pass

    # Load optional example json
    example_json = None
    if args.example:
        try:
            with open(args.example, "r", encoding="utf-8") as f:
                example_json = json.load(f)
        except Exception as exc:
            print(f"Could not read example JSON {args.example}: {exc}", file=sys.stderr)

    # Load optional system prompt (separate from example handling)
    system_prompt_text = None
    if args.system_prompt_file:
        try:
            with open(args.system_prompt_file, "r", encoding="utf-8") as spf:
                system_prompt_text = spf.read()
        except Exception as exc:
            print(f"Could not read system prompt file {args.system_prompt_file}: {exc}", file=sys.stderr)
    elif args.system_prompt:
        system_prompt_text = args.system_prompt

    # If a model was requested but the GEMINI_API_KEY is missing, skip the model call
    if args.model and not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set; skipping model call. The prompt will be saved instead.", file=sys.stderr)
        out["model_skipped"] = True
        out["model_skipped_reason"] = "GEMINI_API_KEY not set"
        model_to_call = None
    else:
        model_to_call = args.model

    # Use the extractor helper which builds the prompt and optionally calls model
    try:
        res = extract_json_from_readme(
            readme_text=readme_text,
            schema_path=args.schema,
            example_json=example_json,
            model=model_to_call,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            system_prompt=system_prompt_text,
        )
    except Exception as exc:
        print(f"Extraction/model call failed: {exc}", file=sys.stderr)
        out["error"] = str(exc)
        res = {"prompt": None, "model_output": None, "parsed": None}

    out["result"] = res

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        # craft default filename from repo URL
        owner_repo = args.repo.rstrip("/\n ")
        if owner_repo.endswith('.git'):
            owner_repo = owner_repo[:-4]
        owner_repo = owner_repo.split("/")[-2:]
        owner = owner_repo[0] if len(owner_repo) > 0 else "repo"
        repo = owner_repo[1] if len(owner_repo) > 1 else "repo"
        safe = f"{owner}-{repo}-result.json"
        out_path = os.path.join("backend", "examples", safe)

    # Ensure output dir exists
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Saved pipeline result to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
