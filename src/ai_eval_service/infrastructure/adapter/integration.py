from __future__ import annotations

from typing import Optional

from ai_eval_service.domain.model.dataset import EvalCase
from ai_eval_service.domain.model.run import AgentRef
from ai_eval_service.domain.port.agent_runtime import AgentRuntimePort, CaseResult
from ai_eval_service.domain.port.integration import (
    AuthPort,
    CachePort,
    TracingPort,
    VectorStorePort,
)
from ai_eval_service.domain.port.llm_provider import LLMProviderPort


class AgentRuntimeAdapter(AgentRuntimePort):
    """Calls ai-gateway-core's AgentRuntime over HTTP (lazy httpx import)."""

    def __init__(self, base_url: str, token: str = "") -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    def run_case(self, ref: AgentRef, case: EvalCase) -> CaseResult:
        import httpx

        resp = httpx.post(
            f"{self._base}/v1/agents/{ref.agent_id}/run",
            json={"inputs": case.inputs, "version": ref.version},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return CaseResult(
            output=data.get("output", ""),
            trace_ref=data.get("trace_ref"),
            latency=float(data.get("latency", 0.0)),
            cost=float(data.get("cost", 0.0)),
        )


class LLMProviderAdapter(LLMProviderPort):
    def __init__(self, base_url: str, token: str = "") -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    def complete(self, prompt, *, model=None, temperature=0.0):
        import httpx

        resp = httpx.post(
            f"{self._base}/v1/llm/complete",
            json={"prompt": prompt, "model": model, "temperature": temperature},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("text", "")


class CacheAdapter(CachePort):
    def __init__(self, dsn: str = "redis://localhost:6379/0") -> None:
        self._dsn = dsn

    def _client(self):
        import redis  # lazy

        return redis.Redis.from_url(self._dsn)

    def get(self, key: str) -> Optional[bytes]:
        return self._client().get(key)

    def set(self, key: str, val: bytes, ttl: float = 0.0) -> None:
        self._client().set(key, val, ex=int(ttl) if ttl and ttl > 0 else None)


class AuthAdapter(AuthPort):
    """Keycloak-style tenant resolution (token claim). Stub for reference."""

    def __init__(self, issuer: str = "", client_id: str = "") -> None:
        self._issuer = issuer
        self._client_id = client_id

    def resolve_tenant(self, token: str) -> str:
        import base64
        import json

        try:
            part = token.split(".")[1]
            part += "=" * (-len(part) % 4)
            claims = json.loads(base64.urlsafe_b64decode(part))
            return claims.get("tenant_id", "local")
        except Exception:
            return "local"

    def authorize(self, token: str, resource: str) -> bool:
        return bool(token)


class TracingAdapter(TracingPort):
    def __init__(self, dsn: str = "") -> None:
        self._dsn = dsn

    def record(self, name: str, attrs: Optional[dict] = None) -> None:
        try:
            from opentelemetry import trace  # lazy

            tracer = trace.get_tracer("ai-eval-service")
            with tracer.start_as_current_span(name) as span:
                for k, v in (attrs or {}).items():
                    span.set_attribute(str(k), str(v))
        except Exception:
            pass


class VectorStoreAdapter(VectorStorePort):
    def __init__(self, url: str = "http://localhost:6333") -> None:
        self._url = url.rstrip("/")

    def search(self, query: str, k: int = 3) -> list:
        import httpx

        resp = httpx.post(
            f"{self._url}/search", json={"query": query, "limit": k}, timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
