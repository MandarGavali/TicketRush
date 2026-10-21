from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import BookingServiceDep, CurrentUser, booking_rate_limit
from app.schemas.booking import BookingCreate, BookingOut, BookingPage, PayRequest

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(booking_rate_limit)],
)
def create_booking(
    data: BookingCreate,
    user: CurrentUser,
    service: BookingServiceDep,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=100,
            description="Any unique string per booking attempt, e.g. a UUID. Reuse it on retry.",
        ),
    ],
) -> BookingOut:
    booking = service.create_booking(user.id, data.event_id, data.seat_ids, idempotency_key)
    return BookingOut.from_model(booking)


@router.post("/{booking_id}/pay", response_model=BookingOut)
def pay_booking(
    booking_id: int, data: PayRequest, user: CurrentUser, service: BookingServiceDep
) -> BookingOut:
    return BookingOut.from_model(service.pay(user.id, booking_id, data.payment_token))


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, user: CurrentUser, service: BookingServiceDep) -> BookingOut:
    return BookingOut.from_model(service.cancel(user.id, booking_id))


@router.get("", response_model=BookingPage)
def list_my_bookings(
    user: CurrentUser,
    service: BookingServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> BookingPage:
    bookings, total = service.list_bookings(user.id, page, size)
    items = [BookingOut.from_model(booking) for booking in bookings]
    return BookingPage(items=items, page=page, size=size, total=total)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, user: CurrentUser, service: BookingServiceDep) -> BookingOut:
    return BookingOut.from_model(service.get_booking(user.id, booking_id))
