import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.core.logging import request_id_var

logger = logging.getLogger("app.access")


async def request_id_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Give every request an id (reuse the client's if sent), log it, and echo it back."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_id_var.set(request_id)
    request.state.request_id = request_id

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s -> %s in %sms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response
