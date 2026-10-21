"""The core guarantee: the same seat is never sold twice, even when everyone clicks at once."""

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select, text

from app.core.errors import SeatUnavailableError
from app.models import Booking, Event, Seat, User, booking_seats
from app.payments.gateway import FakePaymentGateway
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.seat_repo import SeatRepository
from app.services.booking_service import BookingService
from app.services.cache_service import CacheService

BUYERS = 20
ROUNDS = 5


def make_service(session, redis_client) -> BookingService:
    return BookingService(
        session,
        BookingRepository(session),
        SeatRepository(session),
        EventRepository(session),
        payment_gateway=FakePaymentGateway(),
        cache=CacheService(redis_client),
    )


def setup_round(session, n_users: int) -> tuple[int, int, list[int]]:
    """One event with one seat, plus n users. Returns (event_id, seat_id, user_ids)."""
    session.execute(
        text("TRUNCATE booking_seats, bookings, seats, events, users RESTART IDENTITY CASCADE")
    )
    users = [
        User(email=f"buyer{i}@test.com", password_hash="x", full_name=f"Buyer {i}", role="USER")
        for i in range(n_users)
    ]
    session.add_all(users)
    session.flush()
    event = Event(
        title="Hot Show",
        venue="Arena",
        city="Pune",
        starts_at=func.now() + text("interval '1 day'"),
        price_paise=50000,
        total_seats=1,
        created_by=users[0].id,
    )
    session.add(event)
    session.flush()
    seat = Seat(event_id=event.id, row_label="A", seat_number=1, status="AVAILABLE", price_paise=1)
    session.add(seat)
    session.commit()
    return event.id, seat.id, [user.id for user in users]


def run_one_round(session_factory, redis_client) -> list[str]:
    """20 buyers try to book the same single seat at the same moment."""
    with session_factory() as session:
        event_id, seat_id, user_ids = setup_round(session, BUYERS)

    # Every thread waits at the barrier, then all of them hit the database at the same moment.
    barrier = threading.Barrier(BUYERS)

    def attempt(user_id: int) -> str:
        with session_factory() as session:  # each buyer has its own session and connection
            service = make_service(session, redis_client)
            barrier.wait()
            try:
                service.create_booking(user_id, event_id, [seat_id], f"key-{user_id}")
                return "success"
            except SeatUnavailableError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=BUYERS) as pool:
        results = list(pool.map(attempt, user_ids))

    with session_factory() as session:
        assert session.get(Seat, seat_id).status == "HELD"
        rows = session.scalar(
            select(func.count())
            .select_from(booking_seats)
            .where(booking_seats.c.seat_id == seat_id)
        )
        assert rows == 1  # exactly one booking owns the seat
    return results


def test_only_one_of_20_concurrent_buyers_gets_the_seat(session_factory, redis_client):
    for _ in range(ROUNDS):
        results = run_one_round(session_factory, redis_client)
        assert results.count("success") == 1
        assert results.count("conflict") == BUYERS - 1


def test_same_idempotency_key_sent_10_times_at_once_creates_one_booking(
    session_factory, redis_client
):
    with session_factory() as session:
        event_id, seat_id, (user_id,) = setup_round(session, 1)

    barrier = threading.Barrier(10)

    def attempt(_: int) -> int:
        with session_factory() as session:
            service = make_service(session, redis_client)
            barrier.wait()
            return service.create_booking(user_id, event_id, [seat_id], "double-click").id

    with ThreadPoolExecutor(max_workers=10) as pool:
        booking_ids = list(pool.map(attempt, range(10)))

    assert len(set(booking_ids)) == 1  # every request got the same booking back
    with session_factory() as session:
        assert session.scalar(select(func.count(Booking.id))) == 1
