#!/usr/bin/env python3
"""Test script to verify repository metadata is being captured and passed correctly."""
import asyncio
import json
from backend.evaluate.extractor import extract_json_from_readme

# Sample minimal README
SAMPLE_README = """# Test Project

## What

This is a test project for evaluating READMEs.

## Why

We want to extract structured information from README files.

## How to Install

```bash
pip install test-project
```

## How to Use

```python
import test_project
test_project.run()
```

## References

- [GitHub](https://github.com/test/project)
"""

async def test_metadata_flow():
    """Test that metadata (owner, repo, readme_raw_link) flows through extraction."""
    print("Testing metadata capture in extraction flow...")
    
    # Simulate parameters that would come from main.py
    owner = "test-owner"
    repo = "test-repo"
    readme_raw_link = "https://raw.githubusercontent.com/test-owner/test-repo/main/README.md"
    
    print(f"\nInput parameters:")
    print(f"  owner: {owner}")
    print(f"  repo: {repo}")
    print(f"  readme_raw_link: {readme_raw_link}")
    
    # Call extractor without model (fast test, no API calls)
    result = extract_json_from_readme(
        readme_text=SAMPLE_README,
        schema_path="schemas/taxonomia.schema.json",
        model=None,  # No model call for this test
        owner=owner,
        repo=repo,
        readme_raw_link=readme_raw_link,
    )
    
    print(f"\nExtraction result:")
    print(f"  success: {result.success}")
    print(f"  parsed: {result.parsed is not None}")
    
    if result.parsed and "metadata" in result.parsed:
        metadata = result.parsed["metadata"]
        print(f"\nMetadata extracted:")
        print(f"  repository_owner: {metadata.get('repository_owner', 'NOT SET')}")
        print(f"  repository_name: {metadata.get('repository_name', 'NOT SET')}")
        print(f"  repository_link: {metadata.get('repository_link', 'NOT SET')}")
        print(f"  readme_raw_link: {metadata.get('readme_raw_link', 'NOT SET')}")
        
        # Verify values
        assert metadata.get("repository_owner") == owner, "Owner mismatch!"
        assert metadata.get("repository_name") == repo, "Repo name mismatch!"
        assert metadata.get("repository_link") == f"https://github.com/{owner}/{repo}", "Repo link mismatch!"
        assert metadata.get("readme_raw_link") == readme_raw_link, "Raw link mismatch!"
        
        print("\n✓ All metadata fields set correctly!")
        return True
    else:
        print("\n✗ No metadata in parsed result!")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_metadata_flow())
    exit(0 if success else 1)
