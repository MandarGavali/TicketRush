# One-shot build prompt

Paste everything inside the box below into a new Claude Code session opened on this repository.

---

```text
Build the TicketRush backend end to end in this session.

Read these first and follow them exactly; they are the spec:
- CLAUDE.md
- docs/project-guide.md   (scope, data model, API, flows, tests)
- docs/build-checklist.md (Part A is your task list)

Goal: a small, clean, fully working FastAPI + PostgreSQL + Redis project that I (a fresher) will
explain in a backend interview in 2 days. Simplicity and readability beat cleverness. If something
is not in the guide, do not add it. Complete every item in Part A of the checklist.

Hard requirements
1. Remove the old scaffold first: services/, libs/, deploy/, loadtest/, docs/adr/ (git rm, including
   the committed services/booking/.venv). Keep docs/project-guide.md, docs/build-checklist.md,
   docs/build-prompt.md and CLAUDE.md.
2. Layout exactly as in guide section 10. Layers: router -> service -> repository; services own the
   transaction; repositories never commit; app/domain/ has no FastAPI/SQLAlchemy/Redis imports.
3. Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (sync, typed Mapped[] models), psycopg 3, Alembic,
   redis-py, PyJWT (HS256), bcrypt (use the bcrypt package directly, not passlib; max password
   length 72 bytes), pydantic-settings. Plain `def` endpoints. Dependencies in requirements.txt and
   requirements-dev.txt (pytest, httpx, ruff). No other frameworks.
4. Auth uses fastapi.security.HTTPBearer(auto_error=False) so Swagger's Authorize button takes a
   pasted token and missing/invalid tokens return 401 in our error format.
5. The hold query must be exactly the pattern in guide 8.1:
   SELECT ... FROM seats WHERE id IN (...) AND event_id = :e AND status = 'AVAILABLE'
   ORDER BY id FOR UPDATE SKIP LOCKED  (SQLAlchemy: .with_for_update(skip_locked=True)).
   Fewer rows than requested -> rollback and 409 SEAT_UNAVAILABLE listing the missing ids.
6. Idempotency: unique (user_id, idempotency_key). Check first; on IntegrityError from a concurrent
   duplicate, rollback, re-read and return the existing booking with 201.
7. Every error (AppError subclasses, HTTPException incl. 404/405, RequestValidationError, unexpected
   Exception) returns {"error": {"code", "message", "request_id"}}. 500s log the stack trace and
   return a generic message.
8. Redis failures never break a request: cache and rate limiter catch redis errors, log a warning and
   fall back (DB read / allow request).
9. Expiry sweeper: asyncio task started in lifespan, controlled by ENABLE_SWEEPER (false in tests),
   calling expire_pending_bookings(session, now) in a thread every EXPIRY_SWEEP_SECONDS.
10. Money is integer paise everywhere. Timestamps timezone-aware UTC. Secrets only from env;
    .env is git-ignored; .env.example has placeholders.
11. Add a one-line comment only where it explains an interview-relevant "why" (the lock query,
    SKIP LOCKED, ORDER BY id, the IntegrityError catch, cache invalidation, fail-open). No noise.

Tests (guide section 12, all of them)
- tests/unit: domain functions (parametrized) and security helpers. No DB.
- tests/integration: FastAPI TestClient against real Postgres (TEST_DATABASE_URL, database
  ticketrush_test) and Redis (db 1). conftest: create tables once per session with
  Base.metadata.create_all, TRUNCATE ... RESTART IDENTITY CASCADE and flush Redis before each test,
  override the session dependency, provide helpers to register/login a user and an admin.
- tests/integration/test_concurrency.py: 20 threads, each with its own SessionLocal session and its
  own user, call BookingService.create_booking for the same seat at the same moment (use a
  threading.Barrier). Assert exactly 1 success, 19 SeatUnavailable errors, the seat is HELD and
  exactly one booking_seats row exists for it. Run it 5 times in a loop inside the test.
- scripts/race.py: registers N users against a running API (default N=50, base URL arg), fires
  concurrent POST /bookings for the same seat with httpx + threads, prints counts per status code.

Run it, do not just write it
- Start Postgres 16 and Redis 7 (docker compose up -d db redis; if Docker is not available here,
  install and start them locally) and run: alembic upgrade head, ruff check ., ruff format --check .,
  pytest -v. Fix until everything passes. Also start the app and hit /health and /docs once.
- Never claim something passed that you did not run. Never invent performance numbers.

Also deliver
- docker-compose.yml, Dockerfile, .github/workflows/ci.yml (Postgres + Redis service containers,
  ruff, pytest), app/scripts/seed.py (admin@ticketrush.dev / password from env with a dev default,
  2 events, idempotent).
- README.md: one-paragraph intro, mermaid architecture diagram, "run in 3 commands" (docker), local
  dev steps for Windows PowerShell and Linux/macOS, how to run tests and race.py, API table, key design
  decisions (5 bullets), and a "Code map" table: interview concept -> file path (e.g. row locking ->
  app/repositories/seat_repo.py, idempotency -> app/services/booking_service.py, JWT ->
  app/core/security.py, caching, rate limiting, DI, state machine, migrations, concurrency test, CI).

Git
- Work on the current branch. Small logical commits (cleanup, core, models+migration, auth, events,
  bookings, tests, docker+ci, docs). Push when done.

Finish with a short report: what was built, the exact test command and its real output summary,
anything you could not complete, and the 5 files I should read first to explain the project.
```
