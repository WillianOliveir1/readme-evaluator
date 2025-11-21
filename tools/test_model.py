"""Test Gemini Model integration.

Usage: python tools/test_model.py
"""
import os
import sys
import logging

# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.gemini_client import GeminiClient
from backend.config import DEFAULT_MODEL

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("Testing Gemini Client...")
    
    # Try to load .env if not set
    if not os.environ.get("GEMINI_API_KEY"):
        try:
            from dotenv import load_dotenv
            env_path = os.path.join(ROOT, ".env")
            load_dotenv(env_path)
        except ImportError:
            pass

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
        print("Please set it in your .env file or environment.")
        return

    try:
        client = GeminiClient()
        prompt = "Say hello in one short sentence."
        print(f"Model: {DEFAULT_MODEL}")
        print(f"Prompt: {prompt}")
        
        response = client.generate(prompt, model=DEFAULT_MODEL)
        print("-" * 20)
        print(f"Response: {response}")
        print("-" * 20)
        print("Success!")
        
    except Exception as e:
        print(f"Error calling Gemini: {e}")

if __name__ == "__main__":
    main()
