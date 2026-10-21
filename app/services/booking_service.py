import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    BadRequestError,
    BookingExpiredError,
    InvalidStateTransitionError,
    NotFoundError,
    PaymentFailedError,
    SeatUnavailableError,
)
from app.domain.booking_rules import (
    BookingStatus,
    SeatStatus,
    calculate_total,
    can_transition,
    find_unavailable,
    hold_expires_at,
    is_expired,
    validate_seat_request,
)
from app.models import Booking
from app.payments.gateway import PaymentGateway
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.seat_repo import SeatRepository
from app.services.cache_service import CacheService, event_cache_key

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


def change_status(booking: Booking, target: BookingStatus) -> None:
    """The only way a booking changes status: the state machine must allow the move."""
    current = BookingStatus(booking.status)
    if not can_transition(current, target):
        raise InvalidStateTransitionError(f"Cannot move booking from {current} to {target}")
    booking.status = target


def release_seats(booking: Booking) -> None:
    for seat in booking.seats:
        seat.status = SeatStatus.AVAILABLE


def mark_expired(booking: Booking) -> None:
    change_status(booking, BookingStatus.EXPIRED)
    release_seats(booking)


class BookingService:
    def __init__(
        self,
        session: Session,
        bookings: BookingRepository,
        seats: SeatRepository,
        events: EventRepository,
        payment_gateway: PaymentGateway,
        cache: CacheService,
        hold_minutes: int = 5,
        max_seats: int = 6,
    ) -> None:
        self.session = session
        self.bookings = bookings
        self.seats = seats
        self.events = events
        self.payment_gateway = payment_gateway
        self.cache = cache
        self.hold_minutes = hold_minutes
        self.max_seats = max_seats

    def create_booking(
        self, user_id: int, event_id: int, seat_ids: list[int], idempotency_key: str
    ) -> Booking:
        """Hold seats for a few minutes. Safe under concurrency and safe to retry."""
        try:
            validate_seat_request(seat_ids, self.max_seats)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from None

        # Fast path for a retry: same user + same key returns the booking we already made.
        existing = self.bookings.get_by_idempotency_key(user_id, idempotency_key)
        if existing is not None:
            return existing

        if self.events.get(event_id) is None:
            raise NotFoundError("Event not found")

        booking = Booking(
            user_id=user_id,
            event_id=event_id,
            status=BookingStatus.PENDING,
            total_paise=0,
            idempotency_key=idempotency_key,
            expires_at=hold_expires_at(utc_now(), self.hold_minutes),
        )
        self.bookings.add(booking)
        try:
            # Claims the idempotency key: a concurrent request with the same key waits here,
            # then fails on the unique constraint once we commit.
            self.session.flush()
        except IntegrityError:
            # Lost the race to a request with the same key: return that request's booking.
            self.session.rollback()
            winner = self.bookings.get_by_idempotency_key(user_id, idempotency_key)
            if winner is None:
                raise
            return winner

        locked = self.seats.lock_available(event_id, seat_ids)
        missing = find_unavailable(seat_ids, [seat.id for seat in locked])
        if missing:
            # Undo everything (including the booking row) and release our locks.
            self.session.rollback()
            raise SeatUnavailableError(missing)

        for seat in locked:
            seat.status = SeatStatus.HELD
        booking.seats = locked  # inserts the booking_seats rows
        booking.total_paise = calculate_total([seat.price_paise for seat in locked])
        # One commit: seat status, booking and booking_seats are saved together or not at all.
        self.session.commit()

        # Available-seat count changed, so the cached event detail is now stale.
        self.cache.delete(event_cache_key(event_id))
        logger.info("Booking %s holds seats %s", booking.id, seat_ids)
        return booking

    def pay(self, user_id: int, booking_id: int, payment_token: str) -> Booking:
        booking = self._get_owned_for_update(user_id, booking_id)
        if not can_transition(BookingStatus(booking.status), BookingStatus.CONFIRMED):
            raise InvalidStateTransitionError(f"Cannot pay a {booking.status} booking")

        if is_expired(utc_now(), booking.expires_at):
            # The sweeper may not have run yet: expire it now and refuse the payment.
            mark_expired(booking)
            self.session.commit()
            self.cache.delete(event_cache_key(booking.event_id))
            raise BookingExpiredError("The hold has expired, please book again")

        result = self.payment_gateway.charge(
            booking.total_paise, payment_token, reference=f"booking-{booking.id}"
        )
        if not result.success:
            self.session.rollback()  # booking stays PENDING; the user can retry until it expires
            raise PaymentFailedError(f"Payment failed: {result.message}")

        change_status(booking, BookingStatus.CONFIRMED)
        booking.payment_ref = result.payment_ref
        for seat in booking.seats:
            seat.status = SeatStatus.BOOKED
        self.session.commit()
        logger.info("Booking %s confirmed, sending confirmation email (simulated)", booking.id)
        return booking

    def cancel(self, user_id: int, booking_id: int) -> Booking:
        booking = self._get_owned_for_update(user_id, booking_id)
        was_confirmed = booking.status == BookingStatus.CONFIRMED
        change_status(booking, BookingStatus.CANCELLED)
        release_seats(booking)
        if was_confirmed and booking.payment_ref:
            self.payment_gateway.refund(booking.payment_ref, booking.total_paise)
        self.session.commit()
        self.cache.delete(event_cache_key(booking.event_id))
        return booking

    def get_booking(self, user_id: int, booking_id: int) -> Booking:
        booking = self.bookings.get(booking_id)
        # Someone else's booking looks exactly like a missing one: do not leak that it exists.
        if booking is None or booking.user_id != user_id:
            raise NotFoundError("Booking not found")
        return booking

    def list_bookings(self, user_id: int, page: int, size: int) -> tuple[list[Booking], int]:
        return self.bookings.list_for_user(user_id, page, size)

    def _get_owned_for_update(self, user_id: int, booking_id: int) -> Booking:
        booking = self.bookings.get_for_update(booking_id)
        if booking is None or booking.user_id != user_id:
            raise NotFoundError("Booking not found")
        return booking
