"""Shared data contracts for cloud CPU training orchestration.

Military/tactical context:
Typed contracts keep trainer, evaluator, and demo services synchronized during
air-gapped mission rehearsals where schema drift can break operator workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, Field


class CheckpointMeta(BaseModel):
    """Metadata describing a produced checkpoint."""

    checkpoint_id: str = Field(min_length=1)
    track: str = Field(min_length=1)
    step: int = Field(ge=0, default=0)
    epoch: int = Field(ge=0, default=0)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    path: str = ""


class CycleMetrics(BaseModel):
    """One training cycle snapshot for KPI and trend tracking."""

    track: str = Field(min_length=1)
    step: int = Field(ge=0, default=0)
    epoch: int = Field(ge=0, default=0)
    samples_processed: int = Field(ge=0, default=0)
    loss: float = 0.0
    checkpoint_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    eval_results: Dict[str, float] = Field(default_factory=dict)


class PromotionDecision(BaseModel):
    """Promotion outcome used to gate what reaches live demo serving."""

    checkpoint_id: str = Field(min_length=1)
    track: str = Field(min_length=1)
    passed: bool
    eval_scores: Dict[str, float] = Field(default_factory=dict)
    thresholds: Dict[str, float] = Field(default_factory=dict)
    promoted_at: Optional[str] = None
    reason: str = ""
    regression_vs_previous: Dict[str, float] = Field(default_factory=dict)
