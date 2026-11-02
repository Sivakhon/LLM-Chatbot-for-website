"""FastAPI dependencies. Services live on `app.state` (built once in the lifespan)."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings
from app.repositories.product_repository import ProductRepository
from app.services.chat_service import ChatService

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_repository(request: Request) -> ProductRepository:
    repo: ProductRepository = request.app.state.repository
    return repo


def get_chat_service(request: Request) -> ChatService:
    service: ChatService | None = request.app.state.chat_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=request.app.state.llm_error or "LLM is not configured",
        )
    return service


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    provided: Annotated[str | None, Security(_api_key_header)],
) -> None:
    expected = settings.api_key
    if expected is None:
        return  # auth disabled (local dev)
    if not provided or not secrets.compare_digest(provided, expected.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


RepositoryDep = Annotated[ProductRepository, Depends(get_repository)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
