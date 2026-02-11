"""Tests for backend.evaluate.json_postprocessor — pure logic, no mocking."""
from __future__ import annotations

import copy
import pytest

from backend.evaluate.json_postprocessor import (
    fix_string_arrays_in_json,
    remove_disallowed_category_fields,
    normalize_present_categories,
    validate_and_fix_json,
    CATEGORY_SCHEMAS,
)


# =====================================================================
# fix_string_arrays_in_json
# =====================================================================

class TestFixStringArrays:
    """Ensure string-to-array coercion works for known fields."""

    def test_string_justifications_becomes_list(self):
        data = {"justifications": "single string"}
        result = fix_string_arrays_in_json(data)
        assert result["justifications"] == ["single string"]

    def test_string_evidences_becomes_list(self):
        data = {"evidences": "evidence text"}
        result = fix_string_arrays_in_json(data)
        assert result["evidences"] == ["evidence text"]

    def test_string_suggested_improvements_becomes_list(self):
        data = {"suggested_improvements": "improve this"}
        result = fix_string_arrays_in_json(data)
        assert result["suggested_improvements"] == ["improve this"]

    def test_list_stays_list(self):
        data = {"justifications": ["a", "b"]}
        result = fix_string_arrays_in_json(data)
        assert result["justifications"] == ["a", "b"]

    def test_list_items_coerced_to_str(self):
        data = {"evidences": [1, 2, 3]}
        result = fix_string_arrays_in_json(data)
        assert result["evidences"] == ["1", "2", "3"]

    def test_nested_dicts_processed_recursively(self):
        data = {
            "categories": {
                "what": {
                    "justifications": "nested string",
                    "evidences": ["ok"],
                }
            }
        }
        result = fix_string_arrays_in_json(data)
        assert result["categories"]["what"]["justifications"] == ["nested string"]
        assert result["categories"]["what"]["evidences"] == ["ok"]

    def test_lists_processed_recursively(self):
        data = [{"justifications": "in list"}]
        result = fix_string_arrays_in_json(data)
        assert result[0]["justifications"] == ["in list"]

    def test_reclassify_string_true(self):
        for truthy in ["true", "True", "yes", "sim", "1"]:
            data = {"reclassify": truthy}
            result = fix_string_arrays_in_json(data)
            assert result["reclassify"] is True, f"Failed for '{truthy}'"

    def test_reclassify_string_false(self):
        for falsy in ["false", "no", "não", "0"]:
            data = {"reclassify": falsy}
            result = fix_string_arrays_in_json(data)
            assert result["reclassify"] is False, f"Failed for '{falsy}'"

    def test_reclassify_int(self):
        assert fix_string_arrays_in_json({"reclassify": 1})["reclassify"] is True
        assert fix_string_arrays_in_json({"reclassify": 0})["reclassify"] is False

    def test_suggest_removal_boolean_coercion(self):
        data = {"suggest_removal": "true"}
        result = fix_string_arrays_in_json(data)
        assert result["suggest_removal"] is True

    def test_unrelated_keys_untouched(self):
        data = {"name": "hello", "count": 42}
        result = fix_string_arrays_in_json(data)
        assert result == {"name": "hello", "count": 42}

    def test_empty_dict(self):
        assert fix_string_arrays_in_json({}) == {}

    def test_empty_list(self):
        assert fix_string_arrays_in_json([]) == []

    def test_non_dict_non_list_passthrough(self):
        assert fix_string_arrays_in_json("plain string") == "plain string"
        assert fix_string_arrays_in_json(42) == 42
        assert fix_string_arrays_in_json(None) is None


# =====================================================================
# normalize_present_categories
# =====================================================================

class TestNormalizePresentCategories:
    """Ensure present_categories values are coerced to bool/None."""

    def _wrap(self, present_cats: dict) -> dict:
        return {
            "structural_summary": {
                "present_categories": present_cats,
            }
        }

    def test_string_present_becomes_true(self):
        data = self._wrap({"what": "present"})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is True

    def test_string_absent_becomes_false(self):
        data = self._wrap({"what": "absent"})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is False

    def test_string_true_becomes_true(self):
        data = self._wrap({"what": "true"})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is True

    def test_string_false_becomes_false(self):
        data = self._wrap({"what": "false"})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is False

    def test_string_na_becomes_none(self):
        data = self._wrap({"what": "N/A"})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is None

    def test_int_1_becomes_true(self):
        data = self._wrap({"what": 1})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is True

    def test_int_0_becomes_false(self):
        data = self._wrap({"what": 0})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is False

    def test_bool_passthrough(self):
        data = self._wrap({"what": True, "why": False})
        result = normalize_present_categories(data)
        assert result["structural_summary"]["present_categories"]["what"] is True
        assert result["structural_summary"]["present_categories"]["why"] is False

    def test_no_structural_summary_no_error(self):
        result = normalize_present_categories({"other_key": 1})
        assert result == {"other_key": 1}

    def test_non_dict_returns_unchanged(self):
        assert normalize_present_categories([1, 2]) == [1, 2]


# =====================================================================
# remove_disallowed_category_fields
# =====================================================================

class TestRemoveDisallowedCategoryFields:
    """Test field removal, renaming, and quality structure normalization."""

    def test_removes_extra_fields_from_category(self):
        data = {
            "categories": {
                "what": {
                    "checklist": {},
                    "quality": {},
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                    "extra_field": "should be removed",
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        assert "extra_field" not in result["categories"]["what"]

    def test_keeps_allowed_fields(self):
        data = {
            "categories": {
                "what": {
                    "checklist": {},
                    "quality": {},
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        assert set(result["categories"]["what"].keys()) == {
            "checklist", "quality", "evidences", "justifications", "suggested_improvements"
        }

    def test_renames_organization_observations(self):
        data = {
            "structural_summary": {
                "organization_observations": "some notes",
            }
        }
        result = remove_disallowed_category_fields(data)
        assert "organization_notes" in result["structural_summary"]
        assert "organization_observations" not in result["structural_summary"]

    def test_renames_general_observations_in_metadata(self):
        data = {
            "metadata": {
                "general_observations": "some notes",
            }
        }
        result = remove_disallowed_category_fields(data)
        assert "general_notes" in result["metadata"]
        assert "general_observations" not in result["metadata"]

    def test_checklist_string_present_becomes_true(self):
        data = {
            "categories": {
                "what": {
                    "checklist": {"clear_description": "present"},
                    "quality": {},
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        assert result["categories"]["what"]["checklist"]["clear_description"] is True

    def test_checklist_string_absent_becomes_false(self):
        data = {
            "categories": {
                "what": {
                    "checklist": {"clear_description": "absent"},
                    "quality": {},
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        assert result["categories"]["what"]["checklist"]["clear_description"] is False

    def test_license_quality_becomes_integer(self):
        """License quality fields must be plain integers, not objects."""
        data = {
            "categories": {
                "license": {
                    "checklist": {"license_type": True, "license_link": True},
                    "quality": {
                        "clarity": {"note": 4, "evidences": [], "justifications": []},
                        "consistency": {"note": 5, "evidences": [], "justifications": []},
                    },
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        assert result["categories"]["license"]["quality"]["clarity"] == 4
        assert result["categories"]["license"]["quality"]["consistency"] == 5

    def test_non_license_quality_becomes_object(self):
        """Non-license quality fields that are plain ints get wrapped in an object."""
        data = {
            "categories": {
                "what": {
                    "checklist": {},
                    "quality": {"clarity": 4},
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        q = result["categories"]["what"]["quality"]["clarity"]
        assert isinstance(q, dict)
        assert q["note"] == 4
        assert q["evidences"] == []
        assert q["justifications"] == []

    def test_quality_object_gets_missing_fields_added(self):
        data = {
            "categories": {
                "what": {
                    "checklist": {},
                    "quality": {
                        "clarity": {"note": 3},  # missing evidences + justifications
                    },
                    "evidences": [],
                    "justifications": [],
                    "suggested_improvements": [],
                }
            }
        }
        result = remove_disallowed_category_fields(data)
        q = result["categories"]["what"]["quality"]["clarity"]
        assert "evidences" in q
        assert "justifications" in q

    def test_dimensions_summary_int_to_object(self):
        data = {
            "dimensions_summary": {"clarity": 4}
        }
        result = remove_disallowed_category_fields(data)
        dim = result["dimensions_summary"]["clarity"]
        assert isinstance(dim, dict)
        assert dim["note"] == 4

    def test_dimensions_summary_string_evidences_to_array(self):
        data = {
            "dimensions_summary": {
                "clarity": {"note": 3, "evidences": "a string", "justifications": "another"}
            }
        }
        result = remove_disallowed_category_fields(data)
        dim = result["dimensions_summary"]["clarity"]
        assert dim["evidences"] == ["a string"]
        assert dim["justifications"] == ["another"]

    def test_unknown_category_skipped(self):
        """Categories not in CATEGORY_SCHEMAS should pass through untouched."""
        data = {
            "categories": {
                "unknown_cat": {"foo": "bar"}
            }
        }
        result = remove_disallowed_category_fields(data)
        assert result["categories"]["unknown_cat"] == {"foo": "bar"}

    def test_non_dict_input_returns_unchanged(self):
        assert remove_disallowed_category_fields("string") == "string"
        assert remove_disallowed_category_fields(42) == 42


# =====================================================================
# validate_and_fix_json (integration-style with real schema)
# =====================================================================

class TestValidateAndFixJson:
    """Integration test: fix + validate against the real schema."""

    def test_valid_json_passes_first_try(self, schema_path, minimal_evaluation):
        ok, msg = validate_and_fix_json(minimal_evaluation, schema_path)
        assert ok is True

    def test_fixable_json_passes_after_fix(self, schema_path, minimal_evaluation):
        # Introduce fixable issues
        broken = copy.deepcopy(minimal_evaluation)
        broken["categories"]["what"]["justifications"] = "string instead of array"
        broken["structural_summary"]["present_categories"]["what"] = "present"

        ok, msg = validate_and_fix_json(broken, schema_path)
        assert ok is True
        assert "corrigido" in msg or "sucesso" in msg
