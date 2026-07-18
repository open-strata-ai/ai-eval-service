from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from ai_eval_service.domain.model.dataset import EvalCase
from ai_eval_service.domain.model.run import AgentRef


class CaseResult(BaseModel):
    output: str = ""
    trace_ref: Optional[str] = None
    latency: float = 0.0
    cost: float = 0.0


@runtime_checkable
class AgentRuntimePort(Protocol):
    """Run the target Agent for a single evaluation case (docking §4.2)."""

    def run_case(self, ref: AgentRef, case: EvalCase) -> CaseResult: ...
