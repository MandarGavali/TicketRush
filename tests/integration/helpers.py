"""Plain helper functions shared by the integration tests."""

from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from fastapi.testclient import TestClient

PASSWORD = "password123"

Headers = dict[str, str]

# Nothing listens on port 1: used to simulate "Redis is down".
DEAD_REDIS = redis.Redis(port=1, socket_timeout=0.2, socket_connect_timeout=0.2)


def register(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD) -> Headers:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def event_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "title": "Rock Night",
        "description": "Live music",
        "venue": "Main Hall",
        "city": "Pune",
        "starts_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        "price_paise": 50000,
        "rows": 2,
        "seats_per_row": 5,
    }
    payload.update(overrides)
    return payload


def seat_ids(client: TestClient, event_id: int) -> list[int]:
    return [seat["id"] for seat in client.get(f"/api/v1/events/{event_id}/seats").json()]


def book(client: TestClient, headers: Headers, event_id: int, seats: list[int], key: str = "key-1"):
    return client.post(
        "/api/v1/bookings",
        json={"event_id": event_id, "seat_ids": seats},
        headers={**headers, "Idempotency-Key": key},
    )
