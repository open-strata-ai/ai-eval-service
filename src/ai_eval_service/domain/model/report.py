from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    max = "max"
    min = "min"


class Metric(BaseModel):
    metric_key: str
    direction: Direction = Direction.max
    threshold: Optional[float] = None


class EvalReport(BaseModel):
    report_id: str
    run_id: str
    baseline_run_id: Optional[str] = None
    metrics_summary: dict[str, float] = Field(default_factory=dict)
    regression_delta: Optional[dict[str, float]] = None
