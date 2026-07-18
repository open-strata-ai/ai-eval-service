from __future__ import annotations

from ai_eval_service.domain.port.agent_runtime import AgentRuntimePort
from ai_eval_service.domain.port.llm_provider import LLMProviderPort
from ai_eval_service.domain.port.scorer import ScorerRegistry, UnknownScorerError
from ai_eval_service.infrastructure.adapter.fakes import (
    FakeAgentRuntime,
    FakeLLMProvider,
)
from ai_eval_service.infrastructure.adapter.scorer import build_default_scorers


def test_fakes_satisfy_ports():
    assert isinstance(FakeAgentRuntime(), AgentRuntimePort)
    assert isinstance(FakeLLMProvider(), LLMProviderPort)


def test_default_scorers_registered():
    registry = ScorerRegistry()
    for s in build_default_scorers():
        registry.register(s)
    keys = set(registry.list_enabled())
    assert {
        "promptfoo_accuracy",
        "promptfoo_security",
        "deepeval_hallucination",
        "ragas_faithfulness",
    }.issubset(keys)


def test_unknown_scorer_raises():
    registry = ScorerRegistry()
    try:
        registry.get("nope")
        assert False, "expected UnknownScorerError"
    except UnknownScorerError:
        pass
