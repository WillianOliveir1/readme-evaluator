import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.present.renderer import render_from_json
from backend.config import DEFAULT_MAX_TOKENS, RENDER_TEMPERATURE, DEFAULT_MODEL

def main():
    parser = argparse.ArgumentParser(description="Test the renderer module")
    parser.add_argument("--input", "-i", default="data/samples/gemini-evaluation/pandas.json", help="Path to input JSON file")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-model", action="store_true", help="Skip model call, just show prompt")
    parser.add_argument("--debug", "-d", action="store_true", help="Show detailed debug output (full prompt, etc.)")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return

    print(f"Loaded JSON from {input_path}")
    if args.debug:
        print(f"JSON Keys: {list(data.keys())}")
    
    model = None if args.no_model else args.model
    
    print(f"Rendering with model: {model if model else 'NONE (Prompt check only)'}...")
    
    start_time = time.time()
    try:
        result = render_from_json(
            data,
            style_instructions="Make it very concise.",
            model=model,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=RENDER_TEMPERATURE
        )
        elapsed = time.time() - start_time
        
        print("\n" + "="*40)
        print("RENDER RESULT")
        print("="*40)
        print(f"Time elapsed: {elapsed:.2f}s")
        
        if "prompt" in result:
            print(f"\n[PROMPT LENGTH]: {len(result['prompt'])} chars")
            if args.debug:
                print("\n" + "-"*20 + " FULL PROMPT " + "-"*20)
                print(result["prompt"])
                print("-"*53)
            else:
                print("\n[PROMPT PREVIEW (first 500 chars)]:")
                print(result["prompt"][:500] + "...")
        
        print("\n[RENDERED TEXT]:")
        print(result.get("text", "NO TEXT GENERATED"))
        
        if "model_output" in result:
             print(f"\n[RAW MODEL OUTPUT LENGTH]: {len(result['model_output'])}")
             if args.debug:
                 print("\n[RAW MODEL OUTPUT]:")
                 print(result['model_output'])

    except Exception as e:
        print(f"\nError during rendering: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
