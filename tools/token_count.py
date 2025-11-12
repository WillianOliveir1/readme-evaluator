"""Utility to estimate token counts.

Tries to use tiktoken if installed; otherwise falls back to a heuristic (1 token ≈ 4 chars).
"""
from typing import Optional


def count_tokens(text: str, model: Optional[str] = None) -> int:
    try:
        import tiktoken

        # Choose encoding by model when possible, else fallback to 'gpt2'
        encoding_name = None
        if model:
            try:
                encoding_name = tiktoken.encoding_for_model(model).name
            except Exception:
                encoding_name = None

        enc = tiktoken.get_encoding(encoding_name) if encoding_name else tiktoken.get_encoding("gpt2")
        return len(enc.encode(text))
    except Exception:
        # Fallback heuristic
        return max(1, int(len(text) / 4))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: token_count.py <file> [model_name]")
        sys.exit(2)

    path = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) >= 3 else None
    with open(path, "r", encoding="utf-8") as f:
        t = f.read()
    print(count_tokens(t, model))
