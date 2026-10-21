from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, EventServiceDep
from app.schemas.event import (
    EventCreate,
    EventFilters,
    EventOut,
    EventPage,
    EventSort,
    EventUpdate,
    SeatOut,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(data: EventCreate, admin: AdminUser, service: EventServiceDep) -> EventOut:
    return service.create_event(data, admin)


@router.get("", response_model=EventPage)
def list_events(
    service: EventServiceDep,
    city: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(max_length=100, description="Title contains")] = None,
    from_date: date | None = None,
    to_date: date | None = None,
    sort: EventSort = "starts_at",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> EventPage:
    filters = EventFilters(
        city=city, q=q, from_date=from_date, to_date=to_date, sort=sort, page=page, size=size
    )
    return service.list_events(filters)


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int, service: EventServiceDep) -> EventOut:
    return service.get_event(event_id)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int, data: EventUpdate, _admin: AdminUser, service: EventServiceDep
) -> EventOut:
    return service.update_event(event_id, data)


@router.get("/{event_id}/seats", response_model=list[SeatOut])
def list_seats(event_id: int, service: EventServiceDep) -> list[SeatOut]:
    return [SeatOut.model_validate(seat) for seat in service.list_seats(event_id)]
