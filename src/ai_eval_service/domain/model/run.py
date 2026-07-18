from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    scoring = "scoring"
    aggregated = "aggregated"
    done = "done"
    failed = "failed"


class AgentRef(BaseModel):
    agent_id: str
    tenant_id: str
    version: Optional[str] = None


class Score(BaseModel):
    case_id: str
    metric_key: str
    value: float
    reason: str = ""
    trace_ref: Optional[str] = None


class EvalRun(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex[:12]}")
    agent_ref: AgentRef
    dataset_id: str
    dataset_version: str
    scorer_set: list[str] = Field(default_factory=list)
    status: RunStatus = RunStatus.pending
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    tenant_id: str = "local"
    baseline_run_id: Optional[str] = None
    split: str = "eval"
