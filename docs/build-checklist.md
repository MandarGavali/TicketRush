# TicketRush Build Checklist (interview edition)

Four parts. Part A is built by Claude in one go (prompt in `docs/build-prompt.md`). Parts B to D are yours.
Spec for everything: `docs/project-guide.md`. Tick an item only when it works **and** you can explain it.

Suggested timing: Part A + B on day 1, Part C + D on day 2.

## Part A: Build (Claude, one shot)

**A1. Clean-up and setup**

- [x] Remove the old multi-service scaffold: `services/`, `libs/`, `deploy/`, `loadtest/`, `docs/adr/` (incl. the committed `.venv`)
- [x] `.gitignore` (venvs, `__pycache__`, `.env`, `.pytest_cache`, `.ruff_cache`), `.env.example`, `pyproject.toml` (deps + ruff + pytest config)
- [x] `docker-compose.yml`: `api`, `db` (postgres:16 + init script creating `ticketrush_test`), `redis` (redis:7); healthchecks; `depends_on: service_healthy`; named volume
- [x] `Dockerfile`: python:3.12-slim, non-root user, runs `alembic upgrade head` then uvicorn

**A2. Core**

- [x] `core/config.py`, `database.py`, `redis_client.py`, `security.py`, `errors.py`, `logging.py`, `middleware.py`
- [x] Request-id middleware (accept `X-Request-ID` or generate), access log line with method, path, status, duration
- [x] One error JSON format for app errors, 404/405, 422 and unexpected 500s
- [x] CORS allow-list from settings
- [x] `GET /health` checks Postgres and Redis

**A3. Data**

- [x] SQLAlchemy models for `users`, `events`, `seats`, `bookings`, `booking_seats` with every constraint and index in guide section 5
- [x] One Alembic migration that creates all of it (`alembic upgrade head` works on an empty DB)
- [x] `app/scripts/seed.py`: admin user + 2 sample events with seats (idempotent)

**A4. Features**

- [x] Auth: register, login, `/users/me`; bcrypt; JWT; `get_current_user`, `require_admin`
- [x] Events: create (with seats), list (filter, sort, pagination), detail (cached), patch (admin, invalidates cache), seats
- [x] Bookings: create with `FOR UPDATE SKIP LOCKED` + `Idempotency-Key`, pay, cancel, list mine, get one (404 if not mine)
- [x] Domain pure functions from guide section 9
- [x] `PaymentGateway` protocol + `FakePaymentGateway` injected into `BookingService`
- [x] Rate limiting: login 5/min/IP, create booking 10/min/user, 429 + `Retry-After`, fail open
- [x] Expiry sweeper started in `lifespan`, plus `expire_pending_bookings(session, now)`

**A4b. UI**

- [x] Airbnb-style single-page UI in `frontend/` served at `/` (home, event + seat map, checkout, trips, host); see guide 9a

**A5. Tests and CI**

- [x] Every test in guide section 12, including the 20-thread concurrency test
- [x] `scripts/race.py`: fires N concurrent `POST /bookings` (different users) at one seat on the running API and prints successes vs 409s
- [x] `.github/workflows/ci.yml`: Postgres + Redis service containers, `ruff check`, `ruff format --check`, `pytest`
- [x] `README.md`: what it is, architecture diagram, run in 3 commands, how to test, API table, design decisions, "code map" (concept → file)
- [x] `ruff check .` and `pytest` pass locally; `docker compose up --build` serves Swagger at `http://localhost:8000/docs`

## Part B: Verify it yourself (do not skip)

- [ ] `docker compose up --build`; open `/docs`; `/health` is green
- [ ] Open `http://localhost:8000` in two browsers (one normal, one private), log in as two users, pick the same seat in both and
      click Reserve: one goes to checkout, the other gets "Seats already taken" and the map refreshes
- [ ] Stop Redis (`docker compose stop redis`): `/health` reports Redis down, `GET /events/{id}` still works; start it again
- [ ] In Swagger: register, log in, click **Authorize**, paste the token, call `/users/me`
- [ ] Log in as the seeded admin, create an event, list it with a filter and `sort=-price`
- [ ] Hold 2 seats → `GET /events/{id}/seats` shows them `HELD` → pay → `CONFIRMED`, seats `BOOKED`
- [ ] Repeat `POST /bookings` with the same `Idempotency-Key`: same booking id comes back
- [ ] Try to book a held seat from a second user: `409`
- [ ] Pay with token `fail`: `402`, booking still `PENDING`
- [ ] Wrong password 5 times, then a 6th login (even correct): `429`
- [ ] Open another user's booking: `404`
- [ ] Run `pytest -v` and `python scripts/race.py`; write the real numbers in your notes
- [ ] Push; CI is green on GitHub

## Part C: Understand every file (read, then explain out loud)

- [ ] Trace one request end to end: `main.py` → middleware → `api/v1/bookings.py` → `deps.py` → `booking_service.py` → `booking_repo.py`
- [ ] Explain the hold transaction line by line (guide 8.1): transaction, `FOR UPDATE`, `SKIP LOCKED`, `ORDER BY id`, status filter
- [ ] Explain the idempotency race (unique constraint + `IntegrityError` → re-read)
- [ ] Explain `security.py`: bcrypt salt, JWT parts (header, payload, signature), `exp`, why the secret is in env
- [ ] Explain cache-aside and rate limiting from the code, and why both fail open
- [ ] Explain the migration file: every constraint and index and why it exists
- [ ] Read the concurrency test; break it on purpose (remove `FOR UPDATE`) and watch it fail; restore it
- [ ] Explain `Depends` chain and why `FakePaymentGateway` makes tests easy
- [ ] Explain `Dockerfile`, `docker-compose.yml` (healthchecks, service DNS name `db` vs `localhost`) and `ci.yml`

## Part D: Interview prep

- [ ] Say the 30-second pitch (guide section 1) without notes
- [ ] Draw the architecture and the hold sequence diagram on paper
- [ ] Answer the 18 questions in guide section 13 out loud
- [ ] Prepare 3 honest weaknesses and the "what I would add next" list
- [ ] Update the resume entry with only measured facts; repo public with a green CI badge
- [ ] Tag `v1.0.0`

**Done when:** you can demo the double-booking test live and answer "why" for every line in the hold transaction.
