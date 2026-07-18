from __future__ import annotations

from typing import Optional

from ai_eval_service.application.usecase.eval_usecase import EvalUseCase
from ai_eval_service.domain.port.agent_runtime import AgentRuntimePort
from ai_eval_service.domain.port.integration import (
    AuthPort,
    CachePort,
    TracingPort,
    VectorStorePort,
)
from ai_eval_service.domain.port.llm_provider import LLMProviderPort
from ai_eval_service.domain.port.repository import EvalRepositoryPort
from ai_eval_service.domain.port.scorer import ScorerRegistry
from ai_eval_service.infrastructure.adapter.fakes import (
    FakeAgentRuntime,
    FakeLLMProvider,
    InMemoryCache,
    InMemoryVectorStore,
    NoOpAuth,
    NoOpTracing,
)
from ai_eval_service.infrastructure.adapter.integration import (
    AgentRuntimeAdapter,
    AuthAdapter,
    CacheAdapter,
    LLMProviderAdapter,
    TracingAdapter,
    VectorStoreAdapter,
)
from ai_eval_service.infrastructure.adapter.scorer import build_default_scorers
from ai_eval_service.infrastructure.config.eval_config import EvalConfig, load_eval_config
from ai_eval_service.infrastructure.repository.memory import InMemoryEvalRepository
from ai_eval_service.infrastructure.repository.sqlalchemy_repo import (
    SqlAlchemyEvalRepository,
)


class Container:
    """Lightweight DI container assembling adapters onto ports (ARCH §5.2)."""

    def __init__(self) -> None:
        self._registry: dict[type, dict[str, object]] = {}
        self._usecase: Optional[EvalUseCase] = None

    def register(self, port: type, impl: object, key: str = "default") -> None:
        self._registry.setdefault(port, {})[key] = impl

    def resolve(self, port: type, key: str = "default") -> object:
        return self._registry[port][key]

    def resolve_eval_usecase(self) -> EvalUseCase:
        if self._usecase is None:
            repo = self.resolve(EvalRepositoryPort)
            agent = self.resolve(AgentRuntimePort)
            scorers = self.resolve(ScorerRegistry)
            self._usecase = EvalUseCase(repo, agent, scorers)
        return self._usecase


def build_container(
    mode: str = "memory", config: Optional[EvalConfig] = None
) -> Container:
    """Assemble the container.

    - ``memory`` (default, offline): in-memory repo + fake adapters + heuristic
      scorers — fully runnable without Postgres/Redis/LLM.
    - ``production``: SQLAlchemy repo + real SPI adapters (lazy external libs).
    """
    config = config or load_eval_config("infrastructure/config/eval.yaml")
    c = Container()

    if mode == "production":
        pg_dsn = os_environ("PGDSN")
        if not pg_dsn:
            raise RuntimeError("PGDSN must be set for production mode")
        c.register(EvalRepositoryPort, SqlAlchemyEvalRepository(pg_dsn))
        c.register(
            AgentRuntimePort,
            AgentRuntimeAdapter(os_environ("GATEWAY_URL", "http://ai-gateway-core:8000")),
        )
        c.register(
            LLMProviderPort,
            LLMProviderAdapter(os_environ("GATEWAY_URL", "http://ai-gateway-core:8000")),
        )
        c.register(CachePort, CacheAdapter())
        c.register(AuthPort, AuthAdapter())
        c.register(TracingPort, TracingAdapter())
        c.register(VectorStorePort, VectorStoreAdapter())
    else:
        c.register(EvalRepositoryPort, InMemoryEvalRepository())
        c.register(AgentRuntimePort, FakeAgentRuntime())
        c.register(LLMProviderPort, FakeLLMProvider())
        c.register(CachePort, InMemoryCache())
        c.register(AuthPort, NoOpAuth())
        c.register(TracingPort, NoOpTracing())
        c.register(VectorStorePort, InMemoryVectorStore())

    registry = ScorerRegistry()
    for s in build_default_scorers():
        registry.register(s)
    c.register(ScorerRegistry, registry)
    return c


def os_environ(key: str, default: str = "") -> str:
    import os

    return os.environ.get(key, default)
