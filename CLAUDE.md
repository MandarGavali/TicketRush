# TicketRush

Ticket-booking REST API (FastAPI + PostgreSQL + Redis) built to show backend fundamentals in interviews.
**Core guarantee: the same seat is never sold twice, even under concurrent requests.**

## Mode (changed for the Capgemini interview, 23-24 Oct)

- **Build mode:** Claude may build the whole project from `docs/build-prompt.md` in one go.
- **Explain mode (after the build):** explain concepts first-principles, short bullets, exam-ready; quiz Mandar;
  point to the exact file and line. Keep answers simple enough to say out loud in an interview.
- Keep everything simple: if a feature is not in `docs/project-guide.md`, do not add it.

## Source of truth

- `docs/project-guide.md`: scope, stack, architecture, data model, API, flows, tests, interview Q&A.
- `docs/build-checklist.md`: Part A (build), B (verify), C (understand), D (interview prep).
- If code diverges from the guide, update the guide first.

## Rules

- One service, layered: router → service → repository; services own transactions; repositories never commit.
- `app/domain/` = pure functions, no FastAPI / SQLAlchemy / Redis imports; time is passed in as an argument.
- Dependency injection through FastAPI `Depends` and constructors; `PaymentGateway` protocol with `FakePaymentGateway`.
- Money in integer paise. UTC timestamps. Secrets only from environment; `.env` never in git.
- Seat holds use `SELECT ... FOR UPDATE SKIP LOCKED` with `ORDER BY id` inside one transaction.
- `POST /bookings` requires `Idempotency-Key`; unique `(user_id, idempotency_key)`.
- Redis (cache, rate limit) fails open; Postgres is the source of truth.
- Never invent metrics; only quote numbers from tests or `scripts/race.py` that were actually run.

## Defaults

Hold 5 min, max 6 seats per booking, expiry sweep every 30 s, event cache TTL 60 s,
login 5/min per IP, booking 10/min per user, JWT 30 min.

## Commands (after the build)

- Run: `docker compose up --build` → http://localhost:8000/docs
- Test: `docker compose up -d db redis` then `pytest -v`
- Lint: `ruff check . && ruff format --check .`
