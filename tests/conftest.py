"""Shared fixtures for the readme-evaluator test suite."""
from __future__ import annotations

import json
import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "taxonomia.schema.json"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def schema_path() -> str:
    return str(SCHEMA_PATH)


@pytest.fixture
def schema_text() -> str:
    """Raw JSON Schema text."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def schema_obj() -> dict:
    """Parsed JSON Schema dict."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Sample README content
# ---------------------------------------------------------------------------

SAMPLE_README = """\
# My Project

A sample project for testing.

## Installation

```bash
pip install my-project
```

## Usage

```python
import my_project
my_project.run()
```

## License

MIT License
"""


@pytest.fixture
def sample_readme() -> str:
    return SAMPLE_README


# ---------------------------------------------------------------------------
# Minimal valid evaluation JSON (matches taxonomia.schema.json structure)
# ---------------------------------------------------------------------------

def _make_quality_dimension(note: int = 3) -> dict:
    return {"note": note, "evidences": [], "justifications": []}


def _make_standard_category(
    checklist_fields: list[str],
    quality_fields: list[str],
) -> dict:
    return {
        "checklist": {f: True for f in checklist_fields},
        "quality": {f: _make_quality_dimension() for f in quality_fields},
        "evidences": [],
        "justifications": [],
        "suggested_improvements": [],
    }


def _make_other_category() -> dict:
    return {
        "checklist": {"generic_sections": True, "placeholders": False},
        "action": {"reclassify": False, "suggest_removal": False},
        "evidences": [],
        "suggested_improvements": [],
    }


def make_minimal_evaluation() -> dict:
    """Build a minimal valid evaluation dict conforming to the schema."""
    return {
        "metadata": {
            "repository_name": "test-repo",
            "repository_link": "https://github.com/test/repo",
            "readme_raw_link": "https://raw.githubusercontent.com/test/repo/main/README.md",
            "evaluation_date": "2025-01-01",
            "evaluator": "test",
            "general_notes": "Test evaluation",
        },
        "structural_summary": {
            "detected_sections": ["Installation", "Usage"],
            "present_categories": {
                "what": True,
                "why": True,
                "how_installation": True,
                "how_usage": True,
                "how_config_requirements": False,
                "when": False,
                "who": False,
                "license": True,
                "contribution": False,
                "references": False,
                "other": None,
            },
            "organization_notes": "Well organized",
        },
        "categories": {
            "what": _make_standard_category(
                ["clear_description", "features_scope", "target_audience"],
                ["clarity", "understandability", "conciseness", "consistency"],
            ),
            "why": _make_standard_category(
                ["explicit_purpose", "benefits_vs_alternatives", "use_cases"],
                ["clarity", "effectiveness", "appeal"],
            ),
            "how_installation": _make_standard_category(
                ["reproducible_commands", "compatibility_requirements", "dependencies"],
                ["structure", "readability", "clarity"],
            ),
            "how_usage": _make_standard_category(
                ["minimal_working_example", "io_examples", "api_commands_context"],
                ["understandability", "code_readability", "effectiveness"],
            ),
            "how_config_requirements": _make_standard_category(
                ["documented_configuration", "parameters_options", "troubleshooting"],
                ["clarity", "structure", "conciseness"],
            ),
            "when": _make_standard_category(
                ["current_status", "roadmap", "changelog"],
                ["clarity", "consistency"],
            ),
            "who": _make_standard_category(
                ["authors_maintainers", "contact_channels", "code_of_conduct"],
                ["clarity", "consistency"],
            ),
            "license": {
                "checklist": {"license_type": True, "license_link": True},
                "quality": {"clarity": 4, "consistency": 4},
                "evidences": [],
                "justifications": [],
                "suggested_improvements": [],
            },
            "contribution": _make_standard_category(
                ["contributing_link", "contribution_steps", "standards"],
                ["structure", "clarity", "readability"],
            ),
            "references": _make_standard_category(
                ["docs_link", "relevant_references", "faq_support"],
                ["effectiveness", "clarity"],
            ),
            "other": _make_other_category(),
        },
        "dimensions_summary": {
            "quality": _make_quality_dimension(4),
            "appeal": _make_quality_dimension(3),
            "readability": _make_quality_dimension(4),
            "understandability": _make_quality_dimension(4),
            "structure": _make_quality_dimension(3),
            "cohesion": _make_quality_dimension(3),
            "conciseness": _make_quality_dimension(4),
            "effectiveness": _make_quality_dimension(3),
            "consistency": _make_quality_dimension(4),
            "clarity": _make_quality_dimension(4),
            "global_notes": "Overall decent documentation.",
        },
        "executive_summary": {
            "strengths": ["Good installation instructions"],
            "weaknesses": ["Missing contribution guide"],
            "critical_gaps": [],
            "priority_recommendations": ["Add a CONTRIBUTING.md"],
        },
    }


@pytest.fixture
def minimal_evaluation() -> dict:
    return make_minimal_evaluation()
