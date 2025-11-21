"""Progress tracking utilities for the evaluate module."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, List
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class ProgressStage(Enum):
    """Stages of the evaluation process."""
    BUILDING_PROMPT = "building_prompt"
    CALLING_MODEL = "calling_model"
    PARSING_JSON = "parsing_json"
    VALIDATING = "validating"
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
            "estimated_remaining_seconds": round(self.estimated_remaining_seconds, 2) if self.estimated_remaining_seconds else None,
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


class ProgressTracker:
    """Tracks progress through evaluation stages."""
    
    STAGE_PERCENTAGES = {
        ProgressStage.BUILDING_PROMPT: 25,
        ProgressStage.CALLING_MODEL: 75,
        ProgressStage.PARSING_JSON: 90,
        ProgressStage.VALIDATING: 95,
        ProgressStage.COMPLETED: 100,
    }
    
    def __init__(self, callback: Optional[Callable[[ProgressUpdate], None]] = None):
        self.callback = callback
        self.history: List[ProgressUpdate] = []
        self.start_time = time.time()
        self.stage_times: Dict[str, float] = {}

    def start_stage(self, stage: ProgressStage, message: str = "", details: Optional[Dict] = None) -> None:
        """Mark the beginning of a stage."""
        elapsed = time.time() - self.start_time
        
        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.IN_PROGRESS,
            percentage=self.STAGE_PERCENTAGES[stage],
            message=message or f"Starting {stage.value}...",
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(stage),
            details=details,
        )
        
        self.history.append(update)
        logger.debug("Progress: %s", update.message)
        
        if self.callback:
            self.callback(update)
        
        self.stage_times[stage.value] = elapsed

    def update_stage(self, stage: ProgressStage, message: str, details: Optional[Dict] = None) -> None:
        """Update progress within a stage."""
        elapsed = time.time() - self.start_time
        
        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.IN_PROGRESS,
            percentage=self.STAGE_PERCENTAGES[stage],
            message=message,
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(stage),
            details=details,
        )
        
        self.history.append(update)
        # logger.debug("Progress update: %s", update.message) # Optional logging
        
        if self.callback:
            self.callback(update)

    def complete_stage(self, stage: ProgressStage, message: str = "", details: Optional[Dict] = None) -> None:
        """Mark the completion of a stage."""
        elapsed = time.time() - self.start_time
        
        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.COMPLETED,
            percentage=self.STAGE_PERCENTAGES[stage],
            message=message or f"Completed {stage.value}",
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=self._estimate_remaining(stage),
            details=details,
        )
        
        self.history.append(update)
        logger.debug("Progress: %s", update.message)
        
        if self.callback:
            self.callback(update)

    def error_stage(self, stage: ProgressStage, error: str, message: str = "") -> None:
        """Mark a stage as errored."""
        elapsed = time.time() - self.start_time
        
        update = ProgressUpdate(
            stage=stage,
            status=ProgressStatus.ERROR,
            percentage=self.STAGE_PERCENTAGES[stage],
            message=message or f"Error in {stage.value}",
            elapsed_seconds=elapsed,
            error=error,
        )
        
        self.history.append(update)
        logger.error("Progress error: %s - %s", update.message, error)
        
        if self.callback:
            self.callback(update)

    def _estimate_remaining(self, current_stage: ProgressStage) -> Optional[float]:
        """Estimate remaining time based on progress so far."""
        if not self.stage_times:
            return None
        
        elapsed = time.time() - self.start_time
        current_percentage = self.STAGE_PERCENTAGES[current_stage]
        
        if current_percentage == 0:
            return None
        
        # Linear estimation: if we're at X% and took Y seconds, total = Y / (X/100)
        estimated_total = elapsed / (current_percentage / 100.0)
        remaining = estimated_total - elapsed
        
        return max(0, remaining)

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time

    def get_history(self) -> List[ProgressUpdate]:
        """Get all progress updates."""
        return self.history.copy()
