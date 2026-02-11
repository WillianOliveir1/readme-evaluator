"""Tests for backend.llm_base — UsageStats dataclass."""
from __future__ import annotations

from backend.llm_base import UsageStats


class TestUsageStats:
    def test_defaults(self):
        stats = UsageStats()
        assert stats.input_tokens == 0
        assert stats.output_tokens == 0
        assert stats.total_tokens == 0
        assert stats.model == ""
        assert stats.estimated_cost_usd == 0.0

    def test_to_dict(self):
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            model="gemini-2.5-flash",
            estimated_cost_usd=0.000045,
        )
        d = stats.to_dict()
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["total_tokens"] == 150
        assert d["model"] == "gemini-2.5-flash"
        assert d["estimated_cost_usd"] == 0.000045

    def test_to_dict_with_extra(self):
        stats = UsageStats(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            model="llama3",
            extra={"eval_duration_ns": 1234567},
        )
        d = stats.to_dict()
        assert d["eval_duration_ns"] == 1234567
        assert d["model"] == "llama3"

    def test_cost_rounding(self):
        stats = UsageStats(estimated_cost_usd=0.123456789)
        d = stats.to_dict()
        assert d["estimated_cost_usd"] == 0.123457  # rounded to 6 decimals
