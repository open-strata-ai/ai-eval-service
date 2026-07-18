from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class CachePort(Protocol):
    def get(self, key: str) -> Optional[bytes]: ...
    def set(self, key: str, val: bytes, ttl: float = 0.0) -> None: ...


@runtime_checkable
class AuthPort(Protocol):
    def resolve_tenant(self, token: str) -> str: ...
    def authorize(self, token: str, resource: str) -> bool: ...


@runtime_checkable
class TracingPort(Protocol):
    def record(self, name: str, attrs: Optional[dict] = None) -> None: ...


@runtime_checkable
class VectorStorePort(Protocol):
    def search(self, query: str, k: int = 3) -> list: ...
