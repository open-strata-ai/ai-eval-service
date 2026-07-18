from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_eval_service.domain.model.dataset import EvalCase
from ai_eval_service.domain.model.run import Score
from ai_eval_service.domain.port.agent_runtime import CaseResult


class UnknownScorerError(Exception):
    pass


@runtime_checkable
class ScorerPort(Protocol):
    """Pluggable scorer (§5). Concrete adapters wrap Promptfoo/DeepEval/Ragas."""

    scorer_key: str
    supported_metrics: list[str]

    def score(self, case: EvalCase, result: CaseResult) -> list[Score]: ...


class ScorerRegistry:
    """ProviderSelector (§5.1): resolve a registered scorer by key."""

    def __init__(self, scorers: dict[str, ScorerPort] | None = None):
        self._scorers: dict[str, ScorerPort] = dict(scorers or {})

    def register(self, scorer: ScorerPort) -> None:
        self._scorers[scorer.scorer_key] = scorer

    def get(self, scorer_key: str) -> ScorerPort:
        if scorer_key not in self._scorers:
            raise UnknownScorerError(f"Unknown scorer: {scorer_key}")
        return self._scorers[scorer_key]

    def list_enabled(self) -> list[str]:
        return list(self._scorers.keys())
