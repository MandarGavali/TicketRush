from datetime import UTC, datetime, timedelta

import pytest

from app.domain.booking_rules import (
    BookingStatus,
    calculate_total,
    can_transition,
    find_unavailable,
    hold_expires_at,
    is_expired,
    validate_seat_request,
)

P, C, X, E = (
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CANCELLED,
    BookingStatus.EXPIRED,
)


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (P, C, True),
        (P, X, True),
        (P, E, True),
        (C, X, True),
        (P, P, False),
        (C, P, False),
        (C, E, False),
        (C, C, False),
        (X, P, False),
        (X, C, False),
        (E, P, False),
        (E, C, False),
    ],
)
def test_can_transition(current, target, allowed):
    assert can_transition(current, target) is allowed


@pytest.mark.parametrize("seat_ids", [[1], [1, 2, 3], [1, 2, 3, 4, 5, 6]])
def test_validate_seat_request_accepts_valid_lists(seat_ids):
    validate_seat_request(seat_ids, max_seats=6)


@pytest.mark.parametrize(
    ("seat_ids", "message"),
    [
        ([], "at least one"),
        ([1, 1], "unique"),
        ([1, 2, 3, 4, 5, 6, 7], "at most 6"),
    ],
)
def test_validate_seat_request_rejects_bad_lists(seat_ids, message):
    with pytest.raises(ValueError, match=message):
        validate_seat_request(seat_ids, max_seats=6)


@pytest.mark.parametrize(
    ("requested", "locked", "missing"),
    [
        ([1, 2, 3], [1, 2, 3], []),
        ([1, 2, 3], [1, 3], [2]),
        ([3, 1, 2], [], [1, 2, 3]),
    ],
)
def test_find_unavailable(requested, locked, missing):
    assert find_unavailable(requested, locked) == missing


@pytest.mark.parametrize(
    ("prices", "total"),
    [([], 0), ([49900], 49900), ([49900, 49900, 10], 99810)],
)
def test_calculate_total_in_paise(prices, total):
    assert calculate_total(prices) == total


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def test_hold_expires_at_adds_minutes():
    assert hold_expires_at(NOW, 5) == NOW + timedelta(minutes=5)


@pytest.mark.parametrize(
    ("now", "expired"),
    [
        (NOW - timedelta(seconds=1), False),
        (NOW, True),
        (NOW + timedelta(seconds=1), True),
    ],
)
def test_is_expired_at_the_boundary(now, expired):
    assert is_expired(now, expires_at=NOW) is expired
