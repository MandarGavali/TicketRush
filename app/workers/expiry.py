import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.redis_client import redis_client
from app.repositories.booking_repo import BookingRepository
from app.services.booking_service import mark_expired
from app.services.cache_service import CacheService, event_cache_key

logger = logging.getLogger(__name__)


def expire_pending_bookings(
    session: Session, now: datetime, cache: CacheService | None = None, batch_size: int = 100
) -> int:
    """Expire unpaid holds whose time is up and free their seats. Returns how many expired.

    A plain function (time passed in) so tests can call it directly with a fake "now".
    """
    bookings = BookingRepository(session).lock_expired_pending(now, batch_size)
    for booking in bookings:
        mark_expired(booking)
    session.commit()

    if cache is not None:
        for event_id in {booking.event_id for booking in bookings}:
            cache.delete(event_cache_key(event_id))
    if bookings:
        logger.info("Expired %s bookings", len(bookings))
    return len(bookings)


def _sweep_once() -> int:
    with SessionLocal() as session:
        return expire_pending_bookings(session, datetime.now(UTC), CacheService(redis_client))


async def run_expiry_loop(interval_seconds: int) -> None:
    """Background task started with the app: runs the sweep every few seconds."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            # The sweep uses blocking DB calls, so run it in a thread to keep the event loop free.
            await asyncio.to_thread(_sweep_once)
        except Exception:
            logger.exception("Expiry sweep failed, will retry on the next tick")
