import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected errors. Each subclass maps to one HTTP status and error code."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class AuthenticationError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class PaymentFailedError(AppError):
    status_code = 402
    code = "PAYMENT_FAILED"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class EmailTakenError(ConflictError):
    code = "EMAIL_TAKEN"


class SeatUnavailableError(ConflictError):
    code = "SEAT_UNAVAILABLE"

    def __init__(self, seat_ids: list[int]) -> None:
        super().__init__(f"Seats already taken: {seat_ids}")
        self.seat_ids = seat_ids


class BookingExpiredError(ConflictError):
    code = "BOOKING_EXPIRED"


class InvalidStateTransitionError(ConflictError):
    code = "INVALID_STATE"


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request_id_var.get()


def error_response(
    request: Request, status_code: int, code: str, message: str, headers: dict | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": _request_id(request)}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimitError) else None
    return error_response(request, exc.status_code, exc.code, exc.message, headers)


HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    return error_response(request, exc.status_code, code, str(exc.detail), exc.headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    problems = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"])
        problems.append(f"{location}: {err['msg']}")
    return error_response(request, 422, "VALIDATION_ERROR", "; ".join(problems))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full stack trace goes to the server log; the client only gets a generic message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(request, 500, "INTERNAL_ERROR", "Something went wrong")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
