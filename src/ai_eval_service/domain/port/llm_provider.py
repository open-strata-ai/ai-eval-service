from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProviderPort(Protocol):
    """Model supply for synthetic data generation (§4.6.3)."""

    def complete(
        self, prompt: str, *, model: Optional[str] = None, temperature: float = 0.0
    ) -> str: ...
