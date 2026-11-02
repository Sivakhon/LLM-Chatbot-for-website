from collections.abc import AsyncIterator

import pytest

from app.domain.chat import ChatMessage, ChatRequest
from app.repositories.product_repository import ProductRepository
from app.services.chat_service import ChatService


class RecordingLLM:
    model = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    async def generate(self, system: str, messages: list[ChatMessage]) -> str:
        self.calls.append((system, messages))
        return "ok"

    async def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append((system, messages))
        for t in ("o", "k"):
            yield t


def _msgs(*pairs: tuple[str, str]) -> list[ChatMessage]:
    return [ChatMessage(role=r, content=c) for r, c in pairs]  # type: ignore[arg-type]


async def test_answer_grounds_prompt_in_retrieved_products(repository: ProductRepository) -> None:
    llm = RecordingLLM()
    service = ChatService(repository, llm, top_k=2)
    resp = await service.answer(ChatRequest(messages=_msgs(("user", "bomber jacket"))))

    system, _ = llm.calls[0]
    assert resp.sources[0].product.sku == "SKU-4"
    assert "[SKU-4] Jacket Bomber Black" in system
    assert "฿1,595 (was ฿2,695, -41%)" in system


def test_retrieval_query_uses_last_two_user_turns() -> None:
    msgs = _msgs(
        ("user", "jeans"),
        ("assistant", "..."),
        ("user", "black"),
        ("assistant", "..."),
        ("user", "cheaper?"),
    )
    assert ChatService.build_retrieval_query(msgs) == "black cheaper?"


async def test_history_is_trimmed_and_starts_with_user(repository: ProductRepository) -> None:
    llm = RecordingLLM()
    service = ChatService(repository, llm, max_history=2)
    msgs = _msgs(("user", "a"), ("assistant", "b"), ("user", "c"))
    await service.answer(ChatRequest(messages=msgs))
    assert [m.content for m in llm.calls[0][1]] == ["c"]


async def test_stream_emits_sources_tokens_done(repository: ProductRepository) -> None:
    service = ChatService(repository, RecordingLLM())
    events = [e async for e in service.stream(ChatRequest(messages=_msgs(("user", "jeans"))))]
    assert [e.event for e in events] == [
        "filters",
        "sources",
        "token",
        "token",
        "recommended",
        "done",
    ]


async def test_price_in_message_is_enforced(repository: ProductRepository) -> None:
    service = ChatService(repository, RecordingLLM(), top_k=5)
    resp = await service.answer(ChatRequest(messages=_msgs(("user", "ขอดูของราคาไม่เกิน 1000 หน่อย"))))
    assert resp.applied_filters.max_price == 1000
    assert resp.sources and all(s.product.price <= 1000 for s in resp.sources)


def test_request_must_end_with_user_message() -> None:
    with pytest.raises(ValueError):
        ChatRequest(messages=_msgs(("user", "hi"), ("assistant", "hello")))


def test_filters_persist_across_follow_ups(repository: ProductRepository) -> None:
    service = ChatService(repository, RecordingLLM(), max_history=10)
    msgs = _msgs(
        ("user", "ขอดูของราคาไม่เกิน 1000 หน่อย"),
        ("assistant", "..."),
        ("user", "มีสีดำไหม"),
        ("assistant", "..."),
        ("user", "ผู้หญิงล่ะ"),
    )
    f = service.resolve_filters(ChatRequest(messages=msgs))
    assert f.model_dump(exclude_none=True) == {"gender": "women", "max_price": 1000}


def test_later_turn_overrides_earlier_constraint(repository: ProductRepository) -> None:
    service = ChatService(repository, RecordingLLM())
    msgs = _msgs(("user", "under 1000"), ("assistant", "..."), ("user", "actually under 2000"))
    assert service.resolve_filters(ChatRequest(messages=msgs)).max_price == 2000


def test_find_recommended_orders_by_mention_and_accepts_variant_skus(
    repository: ProductRepository,
) -> None:
    sources = repository.search("jeans", k=5)
    answer = "Try SKU-2 first. Or the bomber (size M: SKU-4). Ignore everything else."
    picked = ChatService.find_recommended(answer, [s for s in sources if s.product.sku != "SKU-4"])
    assert picked == ["SKU-2"]
    assert ChatService.find_recommended(answer, sources)[:2] == ["SKU-2", "SKU-4"]
    assert ChatService.find_recommended("No matches, sorry.", sources) == []
