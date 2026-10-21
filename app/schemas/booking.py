from datetime import datetime

from pydantic import BaseModel, Field

from app.models import Booking


class BookingCreate(BaseModel):
    event_id: int
    seat_ids: list[int] = Field(description="1 to 6 unique seat ids from GET /events/{id}/seats")


class PayRequest(BaseModel):
    payment_token: str = Field(min_length=1, description='Use "fail" to simulate a declined card')


class BookingOut(BaseModel):
    id: int
    event_id: int
    event_title: str
    status: str
    total_paise: int
    seat_ids: list[int]
    seats: list[str]  # labels like "A1"
    expires_at: datetime
    payment_ref: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, booking: Booking) -> "BookingOut":
        return cls(
            id=booking.id,
            event_id=booking.event_id,
            event_title=booking.event.title,
            status=booking.status,
            total_paise=booking.total_paise,
            seat_ids=[seat.id for seat in booking.seats],
            seats=[seat.label for seat in booking.seats],
            expires_at=booking.expires_at,
            payment_ref=booking.payment_ref,
            created_at=booking.created_at,
        )


class BookingPage(BaseModel):
    items: list[BookingOut]
    page: int
    size: int
    total: int
