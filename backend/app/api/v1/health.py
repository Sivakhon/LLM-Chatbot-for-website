from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.errors import VectorStoreError

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    products_indexed: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    detail: str | None = None


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/ready", response_model=HealthStatus, summary="Readiness probe")
async def ready(request: Request, response: Response) -> HealthStatus:
    state = request.app.state
    try:
        count = await run_in_threadpool(state.repository.count)
    except VectorStoreError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatus(status="unavailable", detail=exc.message)

    llm = state.chat_service.llm if state.chat_service else None
    ok = llm is not None and count > 0
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthStatus(
        status="ok" if ok else "degraded",
        products_indexed=count,
        llm_provider=state.settings.llm_provider,
        llm_model=llm.model if llm else None,
        detail=None if ok else (state.llm_error or "catalog is empty — run ingestion"),
    )
