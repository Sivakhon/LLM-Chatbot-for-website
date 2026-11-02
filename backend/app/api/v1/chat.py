import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import ChatServiceDep
from app.core.errors import AppError
from app.domain.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatResponse, summary="Ask the shopping assistant")
async def chat(request: ChatRequest, service: ChatServiceDep) -> ChatResponse:
    return await service.answer(request)


@router.post(
    "/stream",
    summary="Ask the shopping assistant (Server-Sent Events)",
    response_description=(
        "`text/event-stream` with events: `filters` (applied filters), "
        "`sources` (retrieved candidates), `token` (text delta), "
        "`recommended` (SKUs the answer cites), "
        "`done`, and `error`."
    ),
)
async def chat_stream(request: ChatRequest, service: ChatServiceDep) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        try:
            async for ev in service.stream(request):
                yield _sse(ev.event, ev.data)
        except AppError as exc:
            # Headers are already sent, so errors are reported in-band.
            yield _sse("error", {"code": exc.code, "message": exc.message})
        except Exception:
            logger.exception("stream failed")
            yield _sse("error", {"code": "internal_error", "message": "Internal server error"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
