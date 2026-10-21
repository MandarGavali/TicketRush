import string

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.booking_rules import SeatStatus
from app.models import Event, Seat, User
from app.repositories.event_repo import EventRepository, normalise_city
from app.repositories.seat_repo import SeatRepository
from app.schemas.event import EventCreate, EventFilters, EventOut, EventPage, EventUpdate
from app.services.cache_service import CacheService, event_cache_key


class EventService:
    def __init__(
        self,
        session: Session,
        events: EventRepository,
        seats: SeatRepository,
        cache: CacheService,
    ) -> None:
        self.session = session
        self.events = events
        self.seats = seats
        self.cache = cache

    def create_event(self, data: EventCreate, admin: User) -> EventOut:
        total_seats = data.rows * data.seats_per_row
        event = Event(
            title=data.title,
            description=data.description,
            venue=data.venue,
            city=normalise_city(data.city),
            starts_at=data.starts_at,
            price_paise=data.price_paise,
            total_seats=total_seats,
            created_by=admin.id,
        )
        self.events.add(event)
        self.session.flush()  # sends the INSERT so event.id exists for the seats

        seats = [
            Seat(
                event_id=event.id,
                row_label=row_label,
                seat_number=number,
                status=SeatStatus.AVAILABLE,
                price_paise=data.price_paise,
            )
            for row_label in string.ascii_uppercase[: data.rows]
            for number in range(1, data.seats_per_row + 1)
        ]
        self.seats.add_all(seats)
        # Event and all its seats are saved in one transaction: never an event without seats.
        self.session.commit()
        return to_event_out(event, available_seats=total_seats)

    def list_events(self, filters: EventFilters) -> EventPage:
        rows, total = self.events.list(filters)
        items = [to_event_out(event, available) for event, available in rows]
        return EventPage(items=items, page=filters.page, size=filters.size, total=total)

    def get_event(self, event_id: int) -> EventOut:
        # Cache-aside: try Redis first, on a miss read Postgres and fill the cache.
        key = event_cache_key(event_id)
        cached = self.cache.get_json(key)
        if cached is not None:
            return EventOut.model_validate(cached)

        row = self.events.get_with_available(event_id)
        if row is None:
            raise NotFoundError("Event not found")
        event_out = to_event_out(*row)
        self.cache.set_json(key, event_out.model_dump(mode="json"))
        return event_out

    def update_event(self, event_id: int, data: EventUpdate) -> EventOut:
        event = self.events.get(event_id)
        if event is None:
            raise NotFoundError("Event not found")
        changes = data.model_dump(exclude_unset=True)
        if "city" in changes and changes["city"] is not None:
            changes["city"] = normalise_city(changes["city"])
        for field, value in changes.items():
            if value is not None:
                setattr(event, field, value)
        self.session.commit()
        # Invalidate after the commit so the next read caches the new data, not the old.
        self.cache.delete(event_cache_key(event_id))
        return self.get_event(event_id)

    def list_seats(self, event_id: int) -> list[Seat]:
        if self.events.get(event_id) is None:
            raise NotFoundError("Event not found")
        return self.seats.list_for_event(event_id)


def to_event_out(event: Event, available_seats: int) -> EventOut:
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        venue=event.venue,
        city=event.city,
        starts_at=event.starts_at,
        price_paise=event.price_paise,
        total_seats=event.total_seats,
        available_seats=available_seats,
    )
