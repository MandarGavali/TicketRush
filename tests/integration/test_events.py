from datetime import UTC, datetime, timedelta

from app.core.redis_client import get_redis
from tests.integration.helpers import DEAD_REDIS, event_payload


def test_admin_creates_event_with_seats(client, create_event):
    event = create_event(rows=3, seats_per_row=4, city="  mumbai ")
    assert event["total_seats"] == 12
    assert event["available_seats"] == 12
    assert event["city"] == "Mumbai"  # normalised

    seats = client.get(f"/api/v1/events/{event['id']}/seats").json()
    assert len(seats) == 12
    assert [seat["label"] for seat in seats[:5]] == ["A1", "A2", "A3", "A4", "B1"]
    assert {seat["status"] for seat in seats} == {"AVAILABLE"}


def test_user_cannot_create_event(client, user_headers):
    response = client.post("/api/v1/events", json=event_payload(), headers=user_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_create_event_without_token_is_401(client):
    assert client.post("/api/v1/events", json=event_payload()).status_code == 401


def test_event_in_the_past_is_422(client, admin_headers):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/v1/events", json=event_payload(starts_at=past), headers=admin_headers
    )
    assert response.status_code == 422


def test_list_filters_sorts_and_paginates(client, create_event):
    now = datetime.now(UTC)
    create_event(title="Pune Jazz", city="Pune", price_paise=30000)
    create_event(title="Pune Rock", city="Pune", price_paise=90000)
    create_event(title="Mumbai Rock", city="Mumbai", price_paise=60000)
    create_event(
        title="Pune Late Show",
        city="Pune",
        price_paise=10000,
        starts_at=(now + timedelta(days=60)).isoformat(),
    )

    by_city = client.get("/api/v1/events", params={"city": "pune", "sort": "-price"}).json()
    assert by_city["total"] == 3
    assert [e["title"] for e in by_city["items"]] == ["Pune Rock", "Pune Jazz", "Pune Late Show"]

    search = client.get("/api/v1/events", params={"q": "rock"}).json()
    assert {e["title"] for e in search["items"]} == {"Pune Rock", "Mumbai Rock"}

    to_date = (now + timedelta(days=30)).date().isoformat()
    soon = client.get("/api/v1/events", params={"city": "Pune", "to_date": to_date}).json()
    assert soon["total"] == 2

    page_1 = client.get("/api/v1/events", params={"size": 3, "page": 1, "sort": "price"}).json()
    page_2 = client.get("/api/v1/events", params={"size": 3, "page": 2, "sort": "price"}).json()
    assert page_1["total"] == page_2["total"] == 4
    assert len(page_1["items"]) == 3
    assert [e["title"] for e in page_2["items"]] == ["Pune Rock"]


def test_page_size_over_50_is_422(client):
    assert client.get("/api/v1/events", params={"size": 51}).status_code == 422


def test_missing_event_is_404(client):
    response = client.get("/api/v1/events/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_event_detail_is_cached_and_invalidated_on_update(
    client, create_event, admin_headers, redis_client
):
    event = create_event()
    client.get(f"/api/v1/events/{event['id']}")
    assert redis_client.exists(f"event:{event['id']}")
    assert 0 < redis_client.ttl(f"event:{event['id']}") <= 60

    response = client.patch(
        f"/api/v1/events/{event['id']}", json={"title": "New Title"}, headers=admin_headers
    )
    assert response.status_code == 200
    # The update deleted the old cache entry, so readers see the new title right away.
    assert client.get(f"/api/v1/events/{event['id']}").json()["title"] == "New Title"


def test_user_cannot_update_event(client, create_event, user_headers):
    event = create_event()
    response = client.patch(
        f"/api/v1/events/{event['id']}", json={"title": "x"}, headers=user_headers
    )
    assert response.status_code == 403


def test_event_detail_still_works_when_redis_is_down(app, client, create_event):
    event = create_event()
    app.dependency_overrides[get_redis] = lambda: DEAD_REDIS
    response = client.get(f"/api/v1/events/{event['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == event["id"]


def test_seats_of_missing_event_is_404(client):
    assert client.get("/api/v1/events/999/seats").status_code == 404
