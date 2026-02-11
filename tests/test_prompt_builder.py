"""Tests for backend.prompt_builder.PromptBuilder — pure logic, no mocking needed."""
from __future__ import annotations

import json
import os
import pytest
import tempfile

from backend.prompt_builder import PromptBuilder


# =====================================================================
# Construction
# =====================================================================

class TestPromptBuilderConstruction:
    """Test that PromptBuilder can be initialized in various ways."""

    def test_default_header(self):
        pb = PromptBuilder()
        assert pb.template_header == "You are a JSON extraction assistant."
        assert pb.parts == []

    def test_custom_header(self):
        pb = PromptBuilder(template_header="Custom header")
        assert pb.template_header == "Custom header"

    def test_kwargs_become_parts(self):
        pb = PromptBuilder(schema="the schema", readme="the readme")
        labels = [label for label, _ in pb.parts]
        assert "schema" in labels
        assert "readme" in labels

    def test_parts_preserve_order(self):
        pb = PromptBuilder()
        pb.add_part("A", "text A")
        pb.add_part("B", "text B")
        pb.add_part("C", "text C")
        labels = [label for label, _ in pb.parts]
        assert labels == ["A", "B", "C"]

    def test_extend_parts(self):
        pb = PromptBuilder()
        pb.extend_parts([("X", "x text"), ("Y", "y text")])
        assert len(pb.parts) == 2


# =====================================================================
# load_schema_text
# =====================================================================

class TestLoadSchemaText:
    """Test the static helper that reads a schema file."""

    def test_loads_existing_schema(self, schema_path):
        text = PromptBuilder.load_schema_text(schema_path)
        assert len(text) > 0
        # Should be valid JSON
        obj = json.loads(text)
        assert "properties" in obj

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            PromptBuilder.load_schema_text("/nonexistent/schema.json")


# =====================================================================
# build()
# =====================================================================

class TestPromptBuilderBuild:
    """Test prompt rendering."""

    def test_build_includes_header(self):
        pb = PromptBuilder(template_header="HEADER_TEXT")
        prompt = pb.build()
        assert "HEADER_TEXT" in prompt

    def test_build_includes_instruction(self):
        pb = PromptBuilder()
        prompt = pb.build(instruction="DO SOMETHING")
        assert "DO SOMETHING" in prompt

    def test_build_includes_parts(self):
        pb = PromptBuilder()
        pb.add_part("MY_SECTION", "section content here")
        prompt = pb.build()
        assert "MY_SECTION:" in prompt
        assert "section content here" in prompt

    def test_build_default_footer(self):
        pb = PromptBuilder()
        prompt = pb.build()
        assert "IMPORTANT" in prompt
        assert "single JSON object" in prompt

    def test_build_custom_footer(self):
        pb = PromptBuilder()
        prompt = pb.build(footer="CUSTOM FOOTER")
        assert "CUSTOM FOOTER" in prompt
        # Default footer should NOT be present
        assert "IMPORTANT: The model must output" not in prompt

    def test_build_empty_footer_suppresses_default(self):
        pb = PromptBuilder()
        prompt = pb.build(footer="")
        assert "IMPORTANT: The model must output" not in prompt

    def test_header_placeholder_substitution(self):
        """When the header contains {schema} or {readme}, they get filled."""
        pb = PromptBuilder(
            template_header="Schema: {schema}\nReadme: {readme}",
            schema="SCHEMA_CONTENT",
            readme="README_CONTENT",
        )
        prompt = pb.build()
        assert "Schema: SCHEMA_CONTENT" in prompt
        assert "Readme: README_CONTENT" in prompt

    def test_header_missing_placeholder_replaced_with_empty(self):
        """Placeholders not matching any part become empty strings."""
        pb = PromptBuilder(template_header="Value: {missing_key}")
        prompt = pb.build()
        assert "Value: " in prompt

    def test_build_with_real_schema_and_readme(self, schema_text, sample_readme):
        pb = PromptBuilder(schema=schema_text, readme=sample_readme)
        prompt = pb.build()
        assert "My Project" in prompt  # From sample README
        assert "properties" in prompt  # From schema
        assert len(prompt) > 1000


# =====================================================================
# save()
# =====================================================================

class TestPromptBuilderSave:
    """Test saving prompt to disk."""

    def test_save_creates_file(self, tmp_path):
        pb = PromptBuilder()
        pb.add_part("DATA", "hello world")
        out = tmp_path / "prompt.txt"
        pb.save(str(out))
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "hello world" in content
