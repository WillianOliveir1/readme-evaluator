"""Test script for MongoDB Handler with .env support.

Execute este script para testar a conexão MongoDB usando variáveis do .env:
    python run_mongodb_test.py
"""
import os
import sys
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv

# Find and load .env file
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ Loaded environment from: {env_path}")
else:
    print(f"⚠ .env file not found at: {env_path}")

# Now import and run tests
from test_mongodb_handler import main

if __name__ == "__main__":
    main()
