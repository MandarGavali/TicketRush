"""Pure business rules: no database, no web framework, no Redis. Time is always passed in."""

from datetime import datetime, timedelta
from enum import StrEnum


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SeatStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"


class Role(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


# The booking state machine: every allowed move, nothing else.
ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.PENDING: {
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.CANCELLED: set(),
    BookingStatus.EXPIRED: set(),
}


def can_transition(current: BookingStatus, target: BookingStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def validate_seat_request(seat_ids: list[int], max_seats: int = 6) -> None:
    """Raises ValueError if the list is empty, has duplicates or is too long."""
    if not seat_ids:
        raise ValueError("Choose at least one seat")
    if len(set(seat_ids)) != len(seat_ids):
        raise ValueError("Seat ids must be unique")
    if len(seat_ids) > max_seats:
        raise ValueError(f"You can book at most {max_seats} seats at a time")


def find_unavailable(requested: list[int], locked: list[int]) -> list[int]:
    """Seats we asked for but could not lock: someone else has them (or they do not exist)."""
    locked_set = set(locked)
    return sorted(seat_id for seat_id in requested if seat_id not in locked_set)


def calculate_total(prices_paise: list[int]) -> int:
    # Integer paise: floats cannot represent money exactly (0.1 + 0.2 != 0.3).
    return sum(prices_paise)


def hold_expires_at(now: datetime, hold_minutes: int) -> datetime:
    return now + timedelta(minutes=hold_minutes)


def is_expired(now: datetime, expires_at: datetime) -> bool:
    return now >= expires_at
