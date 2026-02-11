"""Progress tracking utilities for the evaluate module.

Design rationale
----------------
Progress is driven by **substeps** — the discrete events the backend streams
to the frontend via SSE.  Each call to ``start_stage``, ``update_stage``,
``complete_stage`` or ``error_stage`` counts as **one substep** and advances
an internal counter.  The percentage is simply::

    percentage = completed_substeps / total_substeps × 100

Every stage declares upfront how many substeps it will emit (e.g.
DOWNLOADING emits *start → update → complete* = 3 substeps).
``complete_stage`` additionally **snaps** the counter to the stage's
cumulative boundary so that code-paths that skip intermediate events (e.g.
text-input only emits *start + complete* for DOWNLOADING) still leave the
counter at the correct position for the next stage.

For long-running steps like model streaming, ``update_stream_progress``
interpolates within the current stage's percentage window **without**
advancing the counter, keeping the bar moving smoothly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, List
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class ProgressStage(Enum):
    """Stages of the evaluation process."""
    DOWNLOADING = "downloading"
    BUILDING_PROMPT = "building_prompt"
    CALLING_MODEL = "calling_model"
    PARSING_JSON = "parsing_json"
    VALIDATING = "validating"
    RENDERING = "rendering"
    COMPLETED = "completed"


class ProgressStatus(Enum):
    """Status of a stage."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ProgressUpdate:
    """Single progress update."""
    stage: ProgressStage
    status: ProgressStatus
    percentage: int  # 0-100
    message: str
    elapsed_seconds: float
    estimated_remaining_seconds: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "percentage": self.percentage,
            "message": self.message,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "estimated_remaining_seconds": (
                round(self.estimated_remaining_seconds, 2)
                if self.estimated_remaining_seconds
                else None
            ),
            "details": self.details,
            "error": self.error,
        }


@dataclass
class EvaluationResult:
    """Complete result of an evaluation."""
    success: bool

    # Core results
    prompt: str
    model_output: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None
    validation_ok: Optional[bool] = None
    validation_errors: Optional[Dict] = None

    # Progress tracking
    progress_history: List[ProgressUpdate] = field(default_factory=list)

    # Timing (in seconds)
    timing: Dict[str, float] = field(default_factory=dict)

    # Token usage
    tokens: Dict[str, int] = field(default_factory=dict)

    # Retry info
    retry_count: int = 0
    recovery_suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "prompt": self.prompt,
            "model_output": self.model_output,
            "prompt_length": len(self.prompt),
            "model_output_length": len(self.model_output) if self.model_output else 0,
            "parsed": self.parsed,
            "validation_ok": self.validation_ok,
            "validation_errors": self.validation_errors,
            "progress_history": [p.to_dict() for p in self.progress_history],
            "timing": self.timing,
            "tokens": self.tokens,
            "retry_count": self.retry_count,
            "recovery_suggestions": self.recovery_suggestions,
        }


# =====================================================================
# Default substep declarations
# =====================================================================

DEFAULT_SUBSTEPS: Dict[ProgressStage, int] = {
    ProgressStage.DOWNLOADING: 3,       # start -> update -> complete
    ProgressStage.BUILDING_PROMPT: 2,   # start -> complete
    ProgressStage.CALLING_MODEL: 2,     # start -> complete  (streaming interpolates)
    ProgressStage.PARSING_JSON: 2,      # start -> complete
    ProgressStage.VALIDATING: 2,        # start -> complete
    ProgressStage.RENDERING: 2,         # start -> complete
    ProgressStage.COMPLETED: 1,         # complete only
}
"""Maps each stage to the number of discrete events (substeps) it emits.

Total = 14.  Each SSE event the frontend receives is one substep, so the
progress bar advances by ~7 % with every event.
"""


class ProgressTracker:
    """Substep-based progress tracker.

    Percentage = ``completed_substeps / total_substeps * 100``.

    Parameters
    ----------
    substeps : dict[ProgressStage, int] | None
        Maps each stage to the number of discrete events it will emit.
        Defaults to :data:`DEFAULT_SUBSTEPS`.
    callback : callable | None
        Invoked with every :class:`ProgressUpdate`.
    """

    def __init__(
        self,
        substeps: Optional[Dict[ProgressStage, int]] = None,
        callback: Optional[Callable[[ProgressUpdate], None]] = None,
    ):
        self.callback = callback
        self.history: List[ProgressUpdate] = []
        self.start_time = time.time()

        self._substeps = substeps or dict(DEFAULT_SUBSTEPS)
        self._ordered_stages: List[ProgressStage] = list(self._substeps.keys())
        self._total: int = sum(self._substeps.values())
        self._completed: int = 0
        self._current_stage: Optional[ProgressStage] = None

        # Stage-level timing book-keeping
        self.stage_times: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Percentage helpers
    # ------------------------------------------------------------------

    @property
    def total_substeps(self) -> int:
        return self._total

    @property
    def completed_substeps(self) -> int:
        return self._completed

    def _base_percentage(self) -> int:
        """Percentage based on completed substeps."""
        if self._total <= 0:
            return 100
        return int(self._completed / self._total * 100)

    def _stage_end_boundary(self, stage: ProgressStage) -> int:
        """Cumulative substep count after *stage* is fully complete.

        For a stage not in the registered list, returns the current counter
        + 1 as a safe fallback (behaves as a single-substep stage).
        """
        if stage not in self._substeps:
            return self._completed + 1
        idx = self._ordered_stages.index(stage)
        return sum(
            self._substeps[self._ordered_stages[i]] for i in range(idx + 1)
        )

    def _step_bounds(self) -> tuple[int, int]:
        """Return (start_pct, end_pct) for streaming interpolation.

        The window spans from the current counter position to the end
        boundary of the active stage.
        """
        if self._current_stage is None or self._total <= 0:
            return (0, 0)
        end_boundary = self._stage_end_boundary(self._current_stage)
        start_pct = int(self._completed / self._total * 100)
        end_pct = int(end_boundary / self._total * 100)
        return start_pct, end_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_stage(
        self,
        stage: ProgressStage,
        message: str = "",
        details: Optional[Dict] = None,
    ) -> None:
        """Mark the beginning of a stage (+1 substep)."""
        self._current_stage = stage
        self._completed = min(self._completed + 1, self._total)
        pct = self._base_percentage()
        elapsed = time.time() - self.start_time

        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.IN_PROGRESS,
            percentage=pct,
            message=message or f"Starting {stage.value}...",
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(),
            details=details,
        )

        self.history.append(update)
        logger.debug("Progress: %s (%d%%)", update.message, pct)

        if self.callback:
            self.callback(update)

        self.stage_times[stage.value] = elapsed

    def update_stage(
        self,
        stage: ProgressStage,
        message: str,
        details: Optional[Dict] = None,
    ) -> None:
        """Emit an intermediate update inside the current stage (+1 substep)."""
        self._completed = min(self._completed + 1, self._total)
        pct = self._base_percentage()
        elapsed = time.time() - self.start_time

        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.IN_PROGRESS,
            percentage=pct,
            message=message,
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(),
            details=details,
        )

        self.history.append(update)
        if self.callback:
            self.callback(update)

    def update_stream_progress(
        self,
        chars_received: int,
        estimated_total: int = 0,
        message: str = "",
    ) -> None:
        """Emit smooth sub-progress during model streaming.

        Interpolates within the current stage's percentage window so the
        bar advances gradually while the model generates.  Does **not**
        advance the substep counter -- the final ``complete_stage`` does.

        When *estimated_total* is known the interpolation is linear.  When
        unknown (0) a logarithmic curve is used so the bar keeps moving
        without jumping to the end.
        """
        start_pct, end_pct = self._step_bounds()
        span = end_pct - start_pct
        elapsed = time.time() - self.start_time

        if estimated_total > 0 and chars_received > 0:
            ratio = min(chars_received / estimated_total, 1.0)
            pct = int(start_pct + span * ratio)
        elif chars_received > 0:
            # Log curve: approaches 95 % of span asymptotically
            ratio = min(
                math.log1p(chars_received / 500) / math.log1p(20), 0.95
            )
            pct = int(start_pct + span * ratio)
        else:
            pct = start_pct

        pct = max(start_pct, min(pct, end_pct))

        update = ProgressUpdate(
            stage=ProgressStage.CALLING_MODEL,
            status=ProgressStatus.IN_PROGRESS,
            percentage=pct,
            message=message or f"Generating response... ({chars_received} chars)",
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(),
            details={"chars_received": chars_received},
        )

        self.history.append(update)
        if self.callback:
            self.callback(update)

    def complete_stage(
        self,
        stage: ProgressStage,
        message: str = "",
        details: Optional[Dict] = None,
    ) -> None:
        """Mark a stage as completed (+1 substep, snap to boundary).

        After incrementing, the counter is snapped to at least the
        cumulative boundary for *stage* so that stages with fewer events
        than declared still leave the counter in the right position.
        """
        boundary = self._stage_end_boundary(stage)
        self._completed = min(max(self._completed + 1, boundary), self._total)
        pct = self._base_percentage()
        elapsed = time.time() - self.start_time

        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.COMPLETED,
            percentage=pct,
            message=message or f"Completed {stage.value}",
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(),
            details=details,
        )

        self.history.append(update)
        logger.debug("Progress: %s (%d%%)", update.message, pct)

        if self.callback:
            self.callback(update)

    def error_stage(
        self,
        stage: ProgressStage,
        error: str,
        message: str = "",
    ) -> None:
        """Mark a stage as errored (+1 substep).

        Advances the counter so that subsequent stages start from the
        correct position.
        """
        self._completed = min(self._completed + 1, self._total)
        pct = self._base_percentage()
        elapsed = time.time() - self.start_time

        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.ERROR,
            percentage=pct,
            message=message or f"Error in {stage.value}",
            elapsed_seconds=elapsed,
            error=error,
        )

        self.history.append(update)
        logger.error("Progress error: %s - %s", update.message, error)

        if self.callback:
            self.callback(update)

    # ------------------------------------------------------------------
    # Estimation
    # ------------------------------------------------------------------

    def _estimate_remaining(self) -> Optional[float]:
        """Estimate remaining seconds based on substeps completed so far."""
        if self._completed == 0:
            return None

        elapsed = time.time() - self.start_time
        avg_per_substep = elapsed / self._completed
        remaining = self._total - self._completed
        return max(0.0, avg_per_substep * remaining)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time

    def get_history(self) -> List[ProgressUpdate]:
        """Get all progress updates."""
        return self.history.copy()
