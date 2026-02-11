"""Tests for backend.evaluate.progress — pure logic, no mocking."""
from __future__ import annotations

import time
import pytest

from backend.evaluate.progress import (
    ProgressStage,
    ProgressStatus,
    ProgressUpdate,
    ProgressTracker,
    EvaluationResult,
)


# =====================================================================
# ProgressUpdate
# =====================================================================

class TestProgressUpdate:
    """Test the ProgressUpdate dataclass and serialization."""

    def test_to_dict_basic(self):
        update = ProgressUpdate(
            stage=ProgressStage.BUILDING_PROMPT,
            status=ProgressStatus.IN_PROGRESS,
            percentage=25,
            message="Building...",
            elapsed_seconds=1.234,
        )
        d = update.to_dict()
        assert d["stage"] == "building_prompt"
        assert d["status"] == "in_progress"
        assert d["percentage"] == 25
        assert d["message"] == "Building..."
        assert d["elapsed_seconds"] == 1.23
        assert d["estimated_remaining_seconds"] is None
        assert d["error"] is None

    def test_to_dict_with_error(self):
        update = ProgressUpdate(
            stage=ProgressStage.CALLING_MODEL,
            status=ProgressStatus.ERROR,
            percentage=75,
            message="Failed",
            elapsed_seconds=5.0,
            error="API timeout",
        )
        d = update.to_dict()
        assert d["error"] == "API timeout"
        assert d["status"] == "error"

    def test_to_dict_with_details(self):
        update = ProgressUpdate(
            stage=ProgressStage.PARSING_JSON,
            status=ProgressStatus.COMPLETED,
            percentage=90,
            message="Done",
            elapsed_seconds=2.0,
            details={"response_length": 5000},
        )
        d = update.to_dict()
        assert d["details"]["response_length"] == 5000


# =====================================================================
# EvaluationResult
# =====================================================================

class TestEvaluationResult:
    """Test the EvaluationResult dataclass."""

    def test_to_dict_minimal(self):
        result = EvaluationResult(success=True, prompt="test prompt")
        d = result.to_dict()
        assert d["success"] is True
        assert d["prompt"] == "test prompt"
        assert d["model_output"] is None
        assert d["parsed"] is None
        assert d["prompt_length"] == len("test prompt")
        assert d["model_output_length"] == 0
        assert d["progress_history"] == []
        assert d["retry_count"] == 0

    def test_to_dict_with_parsed(self):
        result = EvaluationResult(
            success=True,
            prompt="p",
            model_output='{"key": "value"}',
            parsed={"key": "value"},
            validation_ok=True,
        )
        d = result.to_dict()
        assert d["parsed"] == {"key": "value"}
        assert d["validation_ok"] is True
        assert d["model_output_length"] == len('{"key": "value"}')

    def test_to_dict_with_errors(self):
        result = EvaluationResult(
            success=False,
            prompt="p",
            validation_ok=False,
            validation_errors={"message": "bad field", "path": ["categories"]},
            recovery_suggestions=["Try again"],
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["validation_errors"]["message"] == "bad field"
        assert d["recovery_suggestions"] == ["Try again"]


# =====================================================================
# ProgressTracker
# =====================================================================

class TestProgressTracker:
    """Test the ProgressTracker state machine."""

    def test_start_stage_records_history(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.BUILDING_PROMPT, "Starting...")
        assert len(tracker.get_history()) == 1
        assert tracker.get_history()[0].status == ProgressStatus.IN_PROGRESS

    def test_complete_stage_records_history(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        tracker.complete_stage(ProgressStage.BUILDING_PROMPT, "Done")
        history = tracker.get_history()
        assert len(history) == 2
        assert history[1].status == ProgressStatus.COMPLETED

    def test_error_stage_records_error(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.CALLING_MODEL)
        tracker.error_stage(ProgressStage.CALLING_MODEL, "timeout", "Model timed out")
        history = tracker.get_history()
        assert len(history) == 2
        assert history[1].status == ProgressStatus.ERROR
        assert history[1].error == "timeout"

    def test_update_stage_records_intermediate(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.CALLING_MODEL)
        tracker.update_stage(ProgressStage.CALLING_MODEL, "50% done")
        tracker.update_stage(ProgressStage.CALLING_MODEL, "75% done")
        assert len(tracker.get_history()) == 3

    def test_callback_invoked(self):
        received = []
        tracker = ProgressTracker(callback=lambda u: received.append(u))
        tracker.start_stage(ProgressStage.BUILDING_PROMPT, "go")
        tracker.complete_stage(ProgressStage.BUILDING_PROMPT, "done")
        assert len(received) == 2
        assert received[0].status == ProgressStatus.IN_PROGRESS
        assert received[1].status == ProgressStatus.COMPLETED

    def test_get_elapsed_increases(self):
        tracker = ProgressTracker()
        e1 = tracker.get_elapsed()
        # Tiny sleep to ensure time passes
        time.sleep(0.01)
        e2 = tracker.get_elapsed()
        assert e2 > e1

    def test_get_history_returns_copy(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        h1 = tracker.get_history()
        h1.append("extra")
        # Internal list should not be affected
        assert len(tracker.get_history()) == 1

    def test_stage_percentages(self):
        """Ensure the percentage mapping is consistent and monotonic."""
        tracker = ProgressTracker()
        prev = 0
        for stage in ProgressStage:
            pct = tracker.STAGE_PERCENTAGES[stage]
            assert pct >= prev, f"{stage} percentage {pct} < previous {prev}"
            prev = pct
        assert prev == 100
