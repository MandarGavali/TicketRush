import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1 import auth, bookings, events, users
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_id_middleware
from app.workers.expiry import run_expiry_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once at startup (before yield) and once at shutdown (after yield)."""
    sweeper = None
    if settings.enable_sweeper:
        sweeper = asyncio.create_task(run_expiry_loop(settings.expiry_sweep_seconds))
    yield
    if sweeper is not None:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="TicketRush",
        version="1.0.0",
        description="Ticket booking API: the same seat is never sold twice.",
        lifespan=lifespan,
    )

    app.middleware("http")(request_id_middleware)
    # Only the listed browser origins may call the API with credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

    api_v1 = APIRouter(prefix="/api/v1")
    for module in (auth, users, events, bookings):
        api_v1.include_router(module.router)
    app.include_router(api_v1)
    app.include_router(health.router)
    return app


app = create_app()
