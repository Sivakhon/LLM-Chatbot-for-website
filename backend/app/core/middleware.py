import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates X-Request-ID and logs one access line per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "%s %s -> %d (%.0fms)",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - start) * 1000,
            )
            return response
        finally:
            request_id_ctx.reset(token)
