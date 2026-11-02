"""Retrieval-augmented chat over the product catalog."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from app.domain.chat import ChatMessage, ChatRequest, ChatResponse, ProductFilters, ScoredProduct
from app.llm.base import LLMClient
from app.repositories.product_repository import ProductRepository
from app.services.prompts import build_system_prompt
from app.services.query_parser import resolve_filters

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamEvent:
    event: str  # "sources" | "token" | "done" | "error"
    data: object


class ChatService:
    def __init__(
        self,
        repository: ProductRepository,
        llm: LLMClient,
        top_k: int = 6,
        max_history: int = 10,
    ) -> None:
        self._repo = repository
        self._llm = llm
        self._top_k = top_k
        self._max_history = max_history

    @property
    def llm(self) -> LLMClient:
        return self._llm

    @staticmethod
    def build_retrieval_query(messages: list[ChatMessage]) -> str:
        """Use the last two user turns so follow-ups like "a cheaper one?" keep their context."""
        user_turns = [m.content for m in messages if m.role == "user"]
        return " ".join(user_turns[-2:])

    def _trim_history(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        trimmed = messages[-self._max_history :]
        # Providers require the conversation to start with a user turn.
        while trimmed and trimmed[0].role != "user":
            trimmed = trimmed[1:]
        return trimmed

    def resolve_filters(self, request: ChatRequest) -> ProductFilters:
        """Constraints stated anywhere in the recent conversation (later turns win),
        plus any explicit API filters. So "under 1000" keeps applying to follow-ups."""
        window = self._trim_history(request.messages)
        user_turns = [m.content for m in window if m.role == "user"]
        return resolve_filters(request.filters, user_turns)

    async def _retrieve(self, request: ChatRequest) -> tuple[list[ScoredProduct], ProductFilters]:
        query = self.build_retrieval_query(request.messages)
        filters = self.resolve_filters(request)
        start = time.perf_counter()
        results: list[ScoredProduct] = await run_in_threadpool(
            self._repo.search, query, self._top_k, filters
        )
        logger.info(
            "retrieved %d products in %.0fms (filters=%s)",
            len(results),
            (time.perf_counter() - start) * 1000,
            filters.model_dump(exclude_none=True),
        )
        return results, filters

    @staticmethod
    def find_recommended(answer: str, sources: list[ScoredProduct]) -> list[str]:
        """SKUs of the sources the answer actually cites, in the order they appear.

        Retrieval returns candidates; the LLM picks among them. The UI should show
        the picks, not every candidate. A variant SKU counts as citing its product.
        """
        positions: list[tuple[int, str]] = []
        for sp in sources:
            skus = [sp.product.sku, *(s.sku for s in sp.product.sizes)]
            hits = [i for sku in skus if (i := answer.find(sku)) >= 0]
            if hits:
                positions.append((min(hits), sp.product.sku))
        return [sku for _, sku in sorted(positions)]

    async def answer(self, request: ChatRequest) -> ChatResponse:
        sources, filters = await self._retrieve(request)
        system = build_system_prompt(sources, filters)
        answer = await self._llm.generate(system, self._trim_history(request.messages))
        return ChatResponse(
            answer=answer,
            sources=sources,
            recommended_skus=self.find_recommended(answer, sources),
            applied_filters=filters,
            model=self._llm.model,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        sources, filters = await self._retrieve(request)
        yield StreamEvent("filters", filters.model_dump(mode="json", exclude_none=True))
        yield StreamEvent("sources", [s.model_dump(mode="json") for s in sources])
        system = build_system_prompt(sources, filters)
        parts: list[str] = []
        async for delta in self._llm.stream(system, self._trim_history(request.messages)):
            parts.append(delta)
            yield StreamEvent("token", delta)
        yield StreamEvent("recommended", self.find_recommended("".join(parts), sources))
        yield StreamEvent("done", {"model": self._llm.model})
