from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.booking_rules import SeatStatus
from app.models import Seat


class SeatRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_all(self, seats: list[Seat]) -> None:
        self.session.add_all(seats)

    def list_for_event(self, event_id: int) -> list[Seat]:
        stmt = (
            select(Seat).where(Seat.event_id == event_id).order_by(Seat.row_label, Seat.seat_number)
        )
        return list(self.session.scalars(stmt))

    def lock_available(self, event_id: int, seat_ids: list[int]) -> list[Seat]:
        """Lock the requested seats that are still AVAILABLE. This is the double-booking guard.

        SELECT ... WHERE id IN (...) AND event_id = ? AND status = 'AVAILABLE'
        ORDER BY id FOR UPDATE SKIP LOCKED
        """
        stmt = (
            select(Seat)
            .where(
                Seat.id.in_(seat_ids),
                Seat.event_id == event_id,
                # Seats already HELD or BOOKED are simply not returned.
                Seat.status == SeatStatus.AVAILABLE,
            )
            # Everyone locks rows in the same order (by id), so two buyers can never deadlock.
            .order_by(Seat.id)
            # FOR UPDATE: rows stay locked until our transaction commits or rolls back.
            # SKIP LOCKED: if another buyer is locking a seat right now, skip it (answer 409 fast)
            # instead of waiting for them.
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(stmt))
