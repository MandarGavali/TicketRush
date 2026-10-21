from datetime import UTC, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.booking_rules import SeatStatus
from app.models import Event, Seat
from app.schemas.event import EventFilters

SORT_COLUMNS = {
    "starts_at": Event.starts_at.asc(),
    "-starts_at": Event.starts_at.desc(),
    "price": Event.price_paise.asc(),
    "-price": Event.price_paise.desc(),
}


def available_seats_subquery():
    """Correlated subquery: counts AVAILABLE seats per event inside the same SQL (no N+1)."""
    return (
        select(func.count(Seat.id))
        .where(Seat.event_id == Event.id, Seat.status == SeatStatus.AVAILABLE)
        .correlate(Event)
        .scalar_subquery()
    )


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: Event) -> None:
        self.session.add(event)

    def get(self, event_id: int) -> Event | None:
        return self.session.get(Event, event_id)

    def get_with_available(self, event_id: int) -> tuple[Event, int] | None:
        stmt = select(Event, available_seats_subquery()).where(Event.id == event_id)
        row = self.session.execute(stmt).first()
        return (row[0], row[1]) if row else None

    def list(self, filters: EventFilters) -> tuple[list[tuple[Event, int]], int]:
        """Returns (event, available_seats) pairs for one page, plus the total match count."""
        base = self._apply_filters(select(Event), filters)
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0

        stmt = (
            self._apply_filters(select(Event, available_seats_subquery()), filters)
            # id as a tie-breaker keeps the order stable, so pages never overlap.
            .order_by(SORT_COLUMNS[filters.sort], Event.id)
            .offset((filters.page - 1) * filters.size)
            .limit(filters.size)
        )
        rows = self.session.execute(stmt).all()
        return [(row[0], row[1]) for row in rows], total

    @staticmethod
    def _apply_filters(stmt: Select, filters: EventFilters) -> Select:
        if filters.city:
            # Exact match on a normalised value so the (city, starts_at) index can be used.
            stmt = stmt.where(Event.city == normalise_city(filters.city))
        if filters.q:
            # ORM builds a parameterized query: user input is never pasted into the SQL string.
            stmt = stmt.where(Event.title.ilike(f"%{filters.q}%"))
        if filters.from_date:
            stmt = stmt.where(Event.starts_at >= datetime.combine(filters.from_date, time(), UTC))
        if filters.to_date:
            day_after = datetime.combine(filters.to_date + timedelta(days=1), time(), UTC)
            stmt = stmt.where(Event.starts_at < day_after)
        return stmt


def normalise_city(city: str) -> str:
    return city.strip().title()
