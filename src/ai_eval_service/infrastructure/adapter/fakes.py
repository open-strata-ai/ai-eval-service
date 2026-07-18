from __future__ import annotations

from typing import Optional

from ai_eval_service.domain.model.dataset import EvalCase
from ai_eval_service.domain.model.run import AgentRef
from ai_eval_service.domain.port.agent_runtime import AgentRuntimePort, CaseResult
from ai_eval_service.domain.port.llm_provider import LLMProviderPort


class FakeAgentRuntime(AgentRuntimePort):
    """Deterministic in-process Agent (no real LLM), used for offline e2e."""

    def run_case(self, ref: AgentRef, case: EvalCase) -> CaseResult:
        q = case.inputs.get("query") if isinstance(case.inputs, dict) else str(case.inputs)
        out = f"[fake-agent:{ref.agent_id}] {q}"
        return CaseResult(output=out, trace_ref=f"trace-{ref.agent_id}", latency=0.01, cost=0.0)


class FakeLLMProvider(LLMProviderPort):
    def complete(self, prompt, *, model=None, temperature=0.0):
        return f"[fake-llm] {prompt[:200]}"


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str) -> Optional[bytes]:
        return self._store.get(key)

    def set(self, key: str, val: bytes, ttl: float = 0.0) -> None:
        self._store[key] = val


class NoOpAuth:
    def resolve_tenant(self, token: str) -> str:
        return "local"

    def authorize(self, token: str, resource: str) -> bool:
        return True


class NoOpTracing:
    def record(self, name: str, attrs: Optional[dict] = None) -> None:
        pass

    def span(self, name: str, attrs: Optional[dict] = None):
        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Ctx()


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._docs: list[tuple[str, dict]] = []

    def upsert(self, doc_id: str, payload: dict) -> None:
        self._docs.append((doc_id, payload))

    def search(self, query: str, k: int = 3) -> list:
        return self._docs[:k]
