from datetime import UTC, date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    venue: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    starts_at: AwareDatetime  # must include a timezone, e.g. 2026-12-01T19:30:00+05:30
    price_paise: int = Field(gt=0, description="Ticket price in paise (49900 = Rs 499.00)")
    rows: int = Field(ge=1, le=26, description="Rows are labelled A to Z")
    seats_per_row: int = Field(ge=1, le=50)

    @field_validator("starts_at")
    @classmethod
    def must_be_in_future(cls, value: datetime) -> datetime:
        if value <= datetime.now(UTC):
            raise ValueError("starts_at must be in the future")
        return value


class EventUpdate(BaseModel):
    """Partial update: only fields that are sent are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    venue: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    starts_at: AwareDatetime | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    venue: str
    city: str
    starts_at: datetime
    price_paise: int
    total_seats: int
    available_seats: int


class EventPage(BaseModel):
    items: list[EventOut]
    page: int
    size: int
    total: int


EventSort = Literal["starts_at", "-starts_at", "price", "-price"]


class EventFilters(BaseModel):
    city: str | None = None
    q: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    sort: EventSort = "starts_at"
    page: int = 1
    size: int = 10


class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_label: str
    seat_number: int
    label: str
    status: str
    price_paise: int
