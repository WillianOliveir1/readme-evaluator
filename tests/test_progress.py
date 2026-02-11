"""Tests for backend.evaluate.progress — substep-based design."""
from __future__ import annotations

import time

from backend.evaluate.progress import (
    DEFAULT_SUBSTEPS,
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
# ProgressTracker — Substep-based design
# =====================================================================

class TestProgressTracker:
    """Test the substep-based ProgressTracker."""

    # ---- construction --------------------------------------------------

    def test_default_substeps(self):
        tracker = ProgressTracker()
        assert tracker.total_substeps == sum(DEFAULT_SUBSTEPS.values())
        assert tracker.completed_substeps == 0

    def test_custom_substeps(self):
        custom = {ProgressStage.BUILDING_PROMPT: 2, ProgressStage.COMPLETED: 1}
        tracker = ProgressTracker(substeps=custom)
        assert tracker.total_substeps == 3

    def test_default_total_is_14(self):
        """DEFAULT_SUBSTEPS should sum to 14."""
        assert sum(DEFAULT_SUBSTEPS.values()) == 14

    # ---- percentage computation ----------------------------------------

    def test_percentage_starts_at_zero(self):
        tracker = ProgressTracker()
        assert tracker._base_percentage() == 0

    def test_start_stage_increments(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.DOWNLOADING)
        assert tracker.completed_substeps == 1
        # 1/14 = 7%
        assert tracker._base_percentage() == 7

    def test_update_stage_increments(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.DOWNLOADING)
        tracker.update_stage(ProgressStage.DOWNLOADING, "Downloading...")
        assert tracker.completed_substeps == 2
        # 2/14 = 14%
        assert tracker._base_percentage() == 14

    def test_complete_stage_snaps_to_boundary(self):
        """complete_stage snaps the counter to the stage boundary.

        DOWNLOADING has 3 substeps, so after complete_stage the counter
        should be at 3 even if only start+complete were emitted (2 events).
        """
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.DOWNLOADING)  # 1
        tracker.complete_stage(ProgressStage.DOWNLOADING)  # snap to 3
        assert tracker.completed_substeps == 3
        # 3/14 = 21%
        assert tracker._base_percentage() == 21

    def test_complete_full_3_event_stage(self):
        """When all 3 events are emitted, complete_stage still snaps to 3."""
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.DOWNLOADING)      # 1
        tracker.update_stage(ProgressStage.DOWNLOADING, "x") # 2
        tracker.complete_stage(ProgressStage.DOWNLOADING)     # max(3, 3) = 3
        assert tracker.completed_substeps == 3

    def test_percentage_after_full_pipeline(self):
        """After completing all stages, percentage == 100."""
        tracker = ProgressTracker()
        for stage in DEFAULT_SUBSTEPS:
            tracker.start_stage(stage)
            tracker.complete_stage(stage)
        assert tracker._base_percentage() == 100

    def test_percentage_never_exceeds_100(self):
        tracker = ProgressTracker()
        # Complete everything twice
        for stage in DEFAULT_SUBSTEPS:
            tracker.start_stage(stage)
            tracker.complete_stage(stage)
        for stage in DEFAULT_SUBSTEPS:
            tracker.start_stage(stage)
            tracker.complete_stage(stage)
        assert tracker._base_percentage() == 100

    # ---- history recording ---------------------------------------------

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
        time.sleep(0.01)
        e2 = tracker.get_elapsed()
        assert e2 > e1

    def test_get_history_returns_copy(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        h1 = tracker.get_history()
        h1.append("extra")
        assert len(tracker.get_history()) == 1

    # ---- error advances counter ----------------------------------------

    def test_error_advances_counter(self):
        """error_stage advances the substep counter so the bar moves."""
        tracker = ProgressTracker()
        before = tracker.completed_substeps
        tracker.error_stage(ProgressStage.CALLING_MODEL, "fail")
        assert tracker.completed_substeps == before + 1

    # ---- monotonic percentage through full pipeline --------------------

    def test_full_pipeline_percentages_monotonic(self):
        """Percentages never decrease through a full start/complete cycle."""
        tracker = ProgressTracker()
        prev_pct = 0
        for stage in DEFAULT_SUBSTEPS:
            tracker.start_stage(stage)
            pct_start = tracker.get_history()[-1].percentage
            assert pct_start >= prev_pct, f"start({stage}) {pct_start} < {prev_pct}"
            tracker.complete_stage(stage)
            pct_end = tracker.get_history()[-1].percentage
            assert pct_end >= pct_start, f"complete({stage}) {pct_end} < {pct_start}"
            prev_pct = pct_end
        assert prev_pct == 100

    def test_skip_intermediate_still_monotonic(self):
        """Even when skipping update_stage, percentages stay monotonic.

        Simulates the text-input path: DOWNLOADING gets start+complete
        (2 events instead of 3), but complete_stage snaps to boundary.
        """
        tracker = ProgressTracker()
        # Only start + complete (skip update)
        tracker.start_stage(ProgressStage.DOWNLOADING)
        tracker.complete_stage(ProgressStage.DOWNLOADING)
        pct_after_download = tracker.get_history()[-1].percentage

        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        pct_build_start = tracker.get_history()[-1].percentage
        assert pct_build_start >= pct_after_download

    # ---- stream sub-progress -------------------------------------------

    def test_update_stream_progress_with_estimate(self):
        """Sub-progress interpolates within the current stage window."""
        received = []
        tracker = ProgressTracker(callback=lambda u: received.append(u))
        # Complete DOWNLOADING so model-call stage is next
        tracker.start_stage(ProgressStage.DOWNLOADING)
        tracker.complete_stage(ProgressStage.DOWNLOADING)
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        tracker.complete_stage(ProgressStage.BUILDING_PROMPT)
        tracker.start_stage(ProgressStage.CALLING_MODEL)
        start_pct, end_pct = tracker._step_bounds()
        tracker.update_stream_progress(chars_received=500, estimated_total=1000)
        pct = received[-1].percentage
        assert start_pct <= pct <= end_pct

    def test_update_stream_progress_without_estimate(self):
        """Without estimated_total, uses logarithmic curve within bounds."""
        received = []
        tracker = ProgressTracker(callback=lambda u: received.append(u))
        tracker.start_stage(ProgressStage.DOWNLOADING)
        tracker.complete_stage(ProgressStage.DOWNLOADING)
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        tracker.complete_stage(ProgressStage.BUILDING_PROMPT)
        tracker.start_stage(ProgressStage.CALLING_MODEL)
        start_pct, end_pct = tracker._step_bounds()
        tracker.update_stream_progress(chars_received=2000)
        pct = received[-1].percentage
        assert start_pct <= pct <= end_pct

    def test_update_stream_progress_zero_chars(self):
        """With 0 chars received should sit at the start of the window."""
        received = []
        tracker = ProgressTracker(callback=lambda u: received.append(u))
        tracker.start_stage(ProgressStage.DOWNLOADING)
        tracker.complete_stage(ProgressStage.DOWNLOADING)
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        tracker.complete_stage(ProgressStage.BUILDING_PROMPT)
        tracker.start_stage(ProgressStage.CALLING_MODEL)
        start_pct, _ = tracker._step_bounds()
        tracker.update_stream_progress(chars_received=0)
        assert received[-1].percentage == start_pct

    def test_stream_progress_does_not_advance_counter(self):
        """update_stream_progress must NOT advance the substep counter."""
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.CALLING_MODEL)
        before = tracker.completed_substeps
        tracker.update_stream_progress(chars_received=1000)
        tracker.update_stream_progress(chars_received=5000)
        assert tracker.completed_substeps == before

    # ---- stages exist --------------------------------------------------

    def test_all_stages_in_default_substeps(self):
        """Every ProgressStage should be declared in DEFAULT_SUBSTEPS."""
        for stage in ProgressStage:
            assert stage in DEFAULT_SUBSTEPS, f"{stage} missing from DEFAULT_SUBSTEPS"

    def test_new_stages_in_enum(self):
        """Verify DOWNLOADING and RENDERING stages exist."""
        assert hasattr(ProgressStage, "DOWNLOADING")
        assert hasattr(ProgressStage, "RENDERING")

    # ---- estimate remaining --------------------------------------------

    def test_estimate_remaining_none_at_start(self):
        tracker = ProgressTracker()
        assert tracker._estimate_remaining() is None

    def test_estimate_remaining_positive(self):
        tracker = ProgressTracker()
        tracker.start_stage(ProgressStage.BUILDING_PROMPT)
        time.sleep(0.01)
        est = tracker._estimate_remaining()
        assert est is not None
        assert est >= 0

    # ---- stage_end_boundary --------------------------------------------

    def test_stage_end_boundary_downloading(self):
        """DOWNLOADING boundary should be 3 (sum of its substeps)."""
        tracker = ProgressTracker()
        assert tracker._stage_end_boundary(ProgressStage.DOWNLOADING) == 3

    def test_stage_end_boundary_building_prompt(self):
        """BUILDING_PROMPT comes after DOWNLOADING(3), so boundary = 3+2 = 5."""
        tracker = ProgressTracker()
        assert tracker._stage_end_boundary(ProgressStage.BUILDING_PROMPT) == 5

    def test_stage_end_boundary_completed(self):
        """COMPLETED is the last stage, boundary should equal total."""
        tracker = ProgressTracker()
        assert tracker._stage_end_boundary(ProgressStage.COMPLETED) == tracker.total_substeps
