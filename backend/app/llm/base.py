"""Provider-agnostic LLM interface."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.domain.chat import ChatMessage


@runtime_checkable
class LLMClient(Protocol):
    model: str

    async def generate(self, system: str, messages: list[ChatMessage]) -> str:
        """Return the full completion."""
        ...

    def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Yield text deltas as they arrive."""
        ...
