"""Anthropic Claude adapter."""

from collections.abc import AsyncIterator

import anthropic

from app.core.errors import LLMError
from app.domain.chat import ChatMessage


class AnthropicClient:
    def __init__(self, api_key: str, model: str, max_tokens: int, timeout_s: float) -> None:
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
        self._max_tokens = max_tokens

    @staticmethod
    def _messages(messages: list[ChatMessage]) -> list[anthropic.types.MessageParam]:
        out: list[anthropic.types.MessageParam] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            else:
                out.append({"role": "assistant", "content": m.content})
        return out

    async def generate(self, system: str, messages: list[ChatMessage]) -> str:
        try:
            resp = await self._client.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                messages=self._messages(messages),
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic request failed: {exc.message}") from exc
        return "".join(block.text for block in resp.content if block.type == "text")

    async def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                messages=self._messages(messages),
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic request failed: {exc.message}") from exc
