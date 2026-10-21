from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from sqlalchemy import select, update

from app.api.deps import get_payment_gateway
from app.core.config import settings
from app.models import Booking, Seat
from app.payments.gateway import FakePaymentGateway
from app.workers.expiry import expire_pending_bookings
from tests.integration.helpers import book, seat_ids


def seat_statuses(client, event_id: int, ids: list[int]) -> set[str]:
    seats = client.get(f"/api/v1/events/{event_id}/seats").json()
    return {seat["status"] for seat in seats if seat["id"] in ids}


def test_hold_then_pay_confirms_booking(client, create_event, user_headers):
    event = create_event(price_paise=50000)
    seats = seat_ids(client, event["id"])[:2]

    held = book(client, user_headers, event["id"], seats)
    assert held.status_code == 201
    booking = held.json()
    assert booking["status"] == "PENDING"
    assert booking["total_paise"] == 100000
    assert booking["seats"] == ["A1", "A2"]
    assert seat_statuses(client, event["id"], seats) == {"HELD"}
    assert client.get(f"/api/v1/events/{event['id']}").json()["available_seats"] == 8

    paid = client.post(
        f"/api/v1/bookings/{booking['id']}/pay",
        json={"payment_token": "tok_visa"},
        headers=user_headers,
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "CONFIRMED"
    assert paid.json()["payment_ref"].startswith("pay_")
    assert seat_statuses(client, event["id"], seats) == {"BOOKED"}


def test_declined_payment_is_402_and_booking_stays_pending(client, create_event, user_headers):
    event = create_event()
    booking = book(client, user_headers, event["id"], seat_ids(client, event["id"])[:1]).json()

    response = client.post(
        f"/api/v1/bookings/{booking['id']}/pay",
        json={"payment_token": "fail"},
        headers=user_headers,
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "PAYMENT_FAILED"
    current = client.get(f"/api/v1/bookings/{booking['id']}", headers=user_headers).json()
    assert current["status"] == "PENDING"


def test_paying_twice_is_409(client, create_event, user_headers):
    event = create_event()
    booking = book(client, user_headers, event["id"], seat_ids(client, event["id"])[:1]).json()
    url = f"/api/v1/bookings/{booking['id']}/pay"
    assert client.post(url, json={"payment_token": "tok"}, headers=user_headers).status_code == 200
    second = client.post(url, json={"payment_token": "tok"}, headers=user_headers)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INVALID_STATE"


def test_same_idempotency_key_returns_the_same_booking(client, create_event, user_headers):
    event = create_event()
    seats = seat_ids(client, event["id"])[:2]
    first = book(client, user_headers, event["id"], seats, key="retry-me")
    second = book(client, user_headers, event["id"], seats, key="retry-me")
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get("/api/v1/bookings", headers=user_headers).json()["total"] == 1


def test_seat_held_by_someone_else_is_409(client, create_event, make_user):
    event = create_event()
    seats = seat_ids(client, event["id"])
    alice, bob = make_user("alice@test.com"), make_user("bob@test.com")

    assert book(client, alice, event["id"], seats[:2]).status_code == 201
    response = book(client, bob, event["id"], [seats[1], seats[2]])
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SEAT_UNAVAILABLE"
    assert str(seats[1]) in error["message"]
    # All or nothing: Bob did not get the free seat either.
    assert seat_statuses(client, event["id"], [seats[2]]) == {"AVAILABLE"}


def test_booking_validation(client, create_event, user_headers):
    event = create_event()
    seats = seat_ids(client, event["id"])

    too_many = book(client, user_headers, event["id"], seats[:7])
    assert too_many.status_code == 400

    no_key = client.post(
        "/api/v1/bookings",
        json={"event_id": event["id"], "seat_ids": seats[:1]},
        headers=user_headers,
    )
    assert no_key.status_code == 422

    missing_event = book(client, user_headers, 999, seats[:1], key="k-404")
    assert missing_event.status_code == 404


def test_other_users_booking_is_404(client, create_event, make_user):
    event = create_event()
    alice, bob = make_user("alice@test.com"), make_user("bob@test.com")
    booking = book(client, alice, event["id"], seat_ids(client, event["id"])[:1]).json()

    assert client.get(f"/api/v1/bookings/{booking['id']}", headers=bob).status_code == 404
    pay = client.post(
        f"/api/v1/bookings/{booking['id']}/pay", json={"payment_token": "tok"}, headers=bob
    )
    assert pay.status_code == 404
    assert client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=bob).status_code == 404


def test_cancel_pending_booking_releases_seats(client, create_event, user_headers):
    event = create_event()
    seats = seat_ids(client, event["id"])[:2]
    booking = book(client, user_headers, event["id"], seats).json()

    response = client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=user_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert seat_statuses(client, event["id"], seats) == {"AVAILABLE"}

    again = client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=user_headers)
    assert again.status_code == 409


def test_cancel_confirmed_booking_refunds(app, client, create_event, user_headers):
    # Interaction test: a mock that wraps the fake lets us assert that refund() was called.
    gateway = Mock(wraps=FakePaymentGateway())
    app.dependency_overrides[get_payment_gateway] = lambda: gateway

    event = create_event()
    seats = seat_ids(client, event["id"])[:2]
    booking = book(client, user_headers, event["id"], seats).json()
    paid = client.post(
        f"/api/v1/bookings/{booking['id']}/pay", json={"payment_token": "tok"}, headers=user_headers
    ).json()

    client.post(f"/api/v1/bookings/{booking['id']}/cancel", headers=user_headers)

    gateway.refund.assert_called_once_with(paid["payment_ref"], paid["total_paise"])
    assert seat_statuses(client, event["id"], seats) == {"AVAILABLE"}


def test_list_my_bookings_newest_first(client, create_event, make_user):
    event = create_event()
    seats = seat_ids(client, event["id"])
    alice, bob = make_user("alice@test.com"), make_user("bob@test.com")
    book(client, alice, event["id"], seats[:1], key="a1")
    book(client, alice, event["id"], seats[1:3], key="a2")
    book(client, bob, event["id"], seats[3:4], key="b1")

    page = client.get("/api/v1/bookings", headers=alice).json()
    assert page["total"] == 2
    assert [b["seats"] for b in page["items"]] == [["A2", "A3"], ["A1"]]
    assert page["items"][0]["event_title"] == event["title"]


def test_sweeper_expires_old_holds_and_frees_seats(client, db, create_event, user_headers):
    event = create_event()
    seats = seat_ids(client, event["id"])[:2]
    booking = book(client, user_headers, event["id"], seats).json()

    # Nothing to expire yet.
    assert expire_pending_bookings(db, now=datetime.now(UTC)) == 0

    later = datetime.now(UTC) + timedelta(minutes=settings.hold_minutes + 1)
    assert expire_pending_bookings(db, now=later) == 1

    assert db.get(Booking, booking["id"]).status == "EXPIRED"
    statuses = db.scalars(select(Seat.status).where(Seat.id.in_(seats))).all()
    assert set(statuses) == {"AVAILABLE"}


def test_paying_an_expired_hold_is_409(client, db, create_event, user_headers):
    event = create_event()
    seats = seat_ids(client, event["id"])[:1]
    booking = book(client, user_headers, event["id"], seats).json()
    past = datetime.now(UTC) - timedelta(seconds=1)
    db.execute(update(Booking).where(Booking.id == booking["id"]).values(expires_at=past))
    db.commit()

    response = client.post(
        f"/api/v1/bookings/{booking['id']}/pay", json={"payment_token": "tok"}, headers=user_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOOKING_EXPIRED"
    assert seat_statuses(client, event["id"], seats) == {"AVAILABLE"}


def test_eleventh_booking_in_a_minute_is_429(client, create_event, user_headers):
    event = create_event(rows=1, seats_per_row=11)
    seats = seat_ids(client, event["id"])
    for i in range(10):
        assert book(client, user_headers, event["id"], [seats[i]], key=f"k{i}").status_code == 201
    response = book(client, user_headers, event["id"], [seats[10]], key="k10")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
