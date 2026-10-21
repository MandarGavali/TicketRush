"""Live demo: N different users try to book the SAME seat at the SAME moment.

Expected result: exactly one 201 (Created) and N-1 409 (Conflict).

Usage (with the API running and seeded):
    python scripts/race.py
    python scripts/race.py --base-url http://localhost:8000 --users 50 --event-id 2
"""

import argparse
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx

PASSWORD = "password123"


def create_user(client: httpx.Client, run_id: str, index: int) -> dict[str, str]:
    email = f"race-{run_id}-{index}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": f"Racer {index}"},
    ).raise_for_status()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def pick_seat(client: httpx.Client, event_id: int | None) -> tuple[int, int, str]:
    if event_id is None:
        events = client.get("/api/v1/events").json()["items"]
        if not events:
            raise SystemExit("No events found. Run: python -m app.scripts.seed")
        event_id = events[0]["id"]
    seats = client.get(f"/api/v1/events/{event_id}/seats").json()
    free = [seat for seat in seats if seat["status"] == "AVAILABLE"]
    if not free:
        raise SystemExit(f"Event {event_id} has no available seats left")
    return event_id, free[0]["id"], free[0]["label"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--event-id", type=int, default=None)
    args = parser.parse_args()

    limits = httpx.Limits(max_connections=args.users)
    with httpx.Client(base_url=args.base_url, timeout=30, limits=limits) as client:
        event_id, seat_id, label = pick_seat(client, args.event_id)
        run_id = uuid.uuid4().hex[:6]
        print(f"Creating {args.users} users ...")
        with ThreadPoolExecutor(max_workers=10) as pool:
            users = list(pool.map(lambda i: create_user(client, run_id, i), range(args.users)))

        print(f"{args.users} users booking seat {label} (id {seat_id}) of event {event_id} ...")
        barrier = threading.Barrier(args.users)

        def attempt(headers: dict[str, str]) -> int:
            barrier.wait()  # everyone fires at the same moment
            response = client.post(
                "/api/v1/bookings",
                json={"event_id": event_id, "seat_ids": [seat_id]},
                headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=args.users) as pool:
            codes = Counter(pool.map(attempt, users))

        seat = next(
            s for s in client.get(f"/api/v1/events/{event_id}/seats").json() if s["id"] == seat_id
        )

    print("\nResults by HTTP status:")
    for code, count in sorted(codes.items()):
        print(f"  {code}: {count}")
    print(f"Seat {label} is now {seat['status']}")
    verdict = "OK: exactly one buyer got the seat" if codes.get(201) == 1 else "UNEXPECTED"
    print(verdict)


if __name__ == "__main__":
    main()
