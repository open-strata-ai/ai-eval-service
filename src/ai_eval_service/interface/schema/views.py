from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ai_eval_service.domain.model.dataset import DatasetSource, Split
from ai_eval_service.domain.model.run import AgentRef, RunStatus


class AgentRefView(AgentRef):
    pass


class DatasetCreate(BaseModel):
    name: str
    dataset_id: Optional[str] = None
    split: Split = Split.eval
    source: DatasetSource = DatasetSource.human
    tenant_id: str = "local"


class CaseCreate(BaseModel):
    inputs: dict = Field(default_factory=dict)
    expected: Optional[dict] = None
    contexts: Optional[list] = None
    tags: list[str] = Field(default_factory=list)


class RunCreate(BaseModel):
    dataset_id: str
    dataset_version: str
    agent: AgentRef
    scorer_set: list[str] = Field(..., min_length=1)
    split: Split = Split.eval
    baseline_run_id: Optional[str] = None


class RunView(BaseModel):
    run_id: str
    status: RunStatus
    progress: float = Field(ge=0, le=1)
    dataset_id: str
    dataset_version: str
    scorer_set: list[str]
    baseline_run_id: Optional[str] = None


class ReportView(BaseModel):
    report_id: str
    run_id: str
    baseline_run_id: Optional[str] = None
    metrics_summary: dict[str, float]
    regression_delta: Optional[dict[str, float]] = None
