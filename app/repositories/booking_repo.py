from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain.booking_rules import BookingStatus
from app.models import Booking


class BookingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, booking: Booking) -> None:
        self.session.add(booking)

    def get(self, booking_id: int) -> Booking | None:
        return self.session.get(Booking, booking_id)

    def get_for_update(self, booking_id: int) -> Booking | None:
        """Lock the booking row so pay and cancel on the same booking run one after the other."""
        stmt = select(Booking).where(Booking.id == booking_id).with_for_update()
        return self.session.scalar(stmt)

    def get_by_idempotency_key(self, user_id: int, key: str) -> Booking | None:
        stmt = select(Booking).where(Booking.user_id == user_id, Booking.idempotency_key == key)
        return self.session.scalar(stmt)

    def list_for_user(self, user_id: int, page: int, size: int) -> tuple[list[Booking], int]:
        total = (
            self.session.scalar(select(func.count(Booking.id)).where(Booking.user_id == user_id))
            or 0
        )
        stmt = (
            select(Booking)
            .where(Booking.user_id == user_id)
            # Load event (JOIN) and seats (one extra IN query) up front: avoids N+1 queries.
            .options(joinedload(Booking.event), selectinload(Booking.seats))
            .order_by(Booking.created_at.desc(), Booking.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.session.scalars(stmt)), total

    def lock_expired_pending(self, now: datetime, limit: int = 100) -> list[Booking]:
        """PENDING bookings past their expiry, locked. SKIP LOCKED lets two sweepers share work."""
        stmt = (
            select(Booking)
            .where(Booking.status == BookingStatus.PENDING, Booking.expires_at < now)
            .order_by(Booking.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(stmt))
