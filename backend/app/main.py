"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.api.v1 import health
from app.core.config import Settings, get_settings
from app.core.errors import LLMError, register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.llm import LLMClient, create_llm_client
from app.repositories.product_repository import ProductRepository
from app.repositories.vector_store import create_chroma_client
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    repository: ProductRepository | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    """Build the app. `repository` / `llm` can be injected (tests, scripts)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        repo = repository or ProductRepository(
            create_chroma_client(settings), settings.collection_name
        )
        llm_client, llm_error = llm, None
        if llm_client is None:
            try:
                llm_client = create_llm_client(settings)
            except LLMError as exc:
                # Keep serving search endpoints; chat returns 503 until fixed.
                llm_error = exc.message
                logger.warning("LLM disabled: %s", exc.message)

        app.state.settings = settings
        app.state.repository = repo
        app.state.llm_error = llm_error
        app.state.chat_service = (
            ChatService(repo, llm_client, settings.retrieval_top_k, settings.max_history_messages)
            if llm_client
            else None
        )
        logger.info(
            "%s started (env=%s, llm=%s/%s, products=%d)",
            settings.app_name,
            settings.environment,
            settings.llm_provider,
            llm_client.model if llm_client else "-",
            repo.count(),
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="RAG shopping assistant API over a scraped MC Jeans product catalog.",
        lifespan=lifespan,
        docs_url="/docs",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app
