"""Deterministic, offline LLM used for tests, CI and demos without an API key.

It doesn't "understand" anything: it lists the products found in the context
block of the system prompt. That is enough to exercise the full RAG pipeline.
"""

import re
from collections.abc import AsyncIterator

from app.domain.chat import ChatMessage

_PRODUCT_LINE = re.compile(r"^- \[(?P<sku>[^\]]+)\] (?P<name>[^|]+)\| (?P<price>฿[\d,]+)", re.M)


class FakeLLMClient:
    model = "fake-extractive"

    async def generate(self, system: str, messages: list[ChatMessage]) -> str:
        matches = _PRODUCT_LINE.findall(system)[:3]
        if not matches:
            return "Sorry, I couldn't find any matching products in our catalog."
        lines = [f"- {name.strip()} ({price}) — SKU {sku}" for sku, name, price in matches]
        return "Here are some products that match your request:\n" + "\n".join(lines)

    async def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        text = await self.generate(system, messages)
        for token in re.split(r"(\s+)", text):
            if token:
                yield token
