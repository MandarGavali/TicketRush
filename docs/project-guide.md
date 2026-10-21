# TicketRush: Project Guide (interview edition)

A ticket-booking REST API built to show solid backend fundamentals.
**Core guarantee: the same seat is never sold twice, even when many users click "book" at the same moment.**

> This is the trimmed version. The earlier 5-service / Kafka / Kubernetes design is in git history
> (commit `0c27b66`) and is now only a "what I would add next" talking point (see the last section).

---

## 1. The 30-second pitch

- TicketRush is a FastAPI + PostgreSQL + Redis backend for booking event seats.
- Users register, log in with JWT, browse events, **hold seats for 5 minutes**, pay (mock), or cancel.
- The hard part is concurrency: two users clicking the same seat at the same time.
  I solved it with a **database transaction + row-level lock (`SELECT ... FOR UPDATE SKIP LOCKED`)**,
  and I **prove it with a test**: 20 threads try to book one seat, exactly 1 succeeds, 19 get `409 Conflict`.
- Retried requests do not create duplicate bookings, thanks to an **Idempotency-Key** backed by a unique constraint.
- Redis is used for **caching** event details and for **rate limiting** login and booking.
- Clean layered architecture (router → service → repository), Alembic migrations, Docker Compose, pytest, GitHub Actions CI.

---

## 2. Scope

**In (build all of it)**

| Area | What | Interview concept it shows |
|---|---|---|
| REST API | Versioned `/api/v1`, correct status codes, Pydantic validation, Swagger | HTTP, REST, DTOs, OpenAPI |
| Auth | Register, login, bcrypt hashing, JWT access token, `GET /users/me` | Authentication, hashing vs encryption, stateless auth |
| Authorization | Roles `USER` and `ADMIN`; only admins create/edit events; users see only their own bookings | RBAC, 401 vs 403 vs 404 |
| Events | Create (auto-generates seats), list with filter + sort + pagination, detail, update | CRUD, pagination, filtering |
| Booking | Hold seats → pay → confirm, or cancel; holds expire after 5 min | Transactions, ACID, row locks, state machine |
| Idempotency | `Idempotency-Key` header on `POST /bookings` | Safe retries, unique constraints |
| Caching | Cache-aside on event detail, TTL, invalidate on update, Redis-down fallback | Caching, cache invalidation |
| Rate limiting | Fixed window in Redis: 5 failed logins/min per IP, 10 bookings/min per user | Rate limiting, 429 |
| Background job | Sweeper that expires unpaid holds every 30 s | Background tasks, scheduled work |
| Errors and logs | One error JSON format, request-id middleware, structured logs | Error handling, observability basics |
| DB | PostgreSQL, SQLAlchemy 2, Alembic, constraints and indexes, joins | SQL, indexing, normalization, migrations |
| Design | Dependency injection, `PaymentGateway` interface with a fake | SOLID, DI, interfaces, testability |
| Testing | Unit tests (pure functions), API tests, the concurrency test | Test pyramid, mocking vs fakes |
| DevOps | Dockerfile, Docker Compose with healthchecks, GitHub Actions CI | Containers, CI |

**Out (cut on purpose, mention only as "next steps")**

Microservices and API gateway, MongoDB, Kafka, outbox, saga, payment webhooks and HMAC, Google OAuth, cookie sessions and CSRF,
refresh-token rotation, WebSockets, RQ/Celery, CQRS, Nginx and TLS, read replicas, Prometheus/Grafana/tracing, Kubernetes,
k6, mutation testing, Testcontainers, circuit breakers, cloud deployment.

---

## 3. Stack

| Layer | Choice | Why (one line you can say out loud) |
|---|---|---|
| Language / framework | Python 3.12, FastAPI, Pydantic v2 | Typed, fast to build, auto Swagger docs |
| Database | PostgreSQL 16 | ACID transactions, row locks, constraints: seats and money must be exact |
| ORM / migrations | SQLAlchemy 2 (sync), Alembic | Parameterized queries (no SQL injection), versioned schema changes |
| Cache / limits | Redis 7 | In-memory, TTLs, atomic `INCR` |
| Auth | PyJWT (HS256), bcrypt | Stateless tokens; slow salted password hashing |
| Tests | pytest, FastAPI `TestClient` | Simple, standard |
| Packaging | Docker, Docker Compose | One command to run API + Postgres + Redis |
| CI | GitHub Actions | Lint + tests on every push |

**Why sync SQLAlchemy and `def` endpoints?** FastAPI runs plain `def` endpoints in a thread pool, so blocking DB calls do not block the
event loop. It is simpler to read, test and explain than async SQLAlchemy, and enough for this scale.

---

## 4. Architecture

One service, cleanly layered. Every request goes through the same path:

```mermaid
flowchart LR
    C[Client / Swagger] --> M[Middleware<br/>request id, logging, CORS]
    M --> R[Router<br/>api/v1/*.py<br/>validation, auth deps]
    R --> S[Service<br/>business rules,<br/>owns the transaction]
    S --> D[Domain<br/>pure functions]
    S --> Repo[Repository<br/>SQL only]
    Repo --> PG[(PostgreSQL)]
    S --> Cache[(Redis<br/>cache + rate limit)]
    S --> P[PaymentGateway<br/>FakePaymentGateway]
    W[Expiry sweeper<br/>every 30 s] --> S
```

**Rules of the layers**

- **Router**: HTTP only. Parses input (Pydantic), calls one service method, returns a response model. No SQL, no business rules.
- **Service**: business logic. Opens/commits the transaction (`with session.begin()`), calls repositories and domain functions.
- **Repository**: the only place that touches SQLAlchemy queries. Never commits.
- **Domain**: pure functions, no I/O (no FastAPI, SQLAlchemy or Redis imports). Easiest code to unit test.
- **Dependency injection**: FastAPI `Depends` builds `Session → Repository → Service`; services get dependencies through their constructor,
  so tests can pass fakes (for example `FakePaymentGateway`).

---

## 5. Data model (PostgreSQL)

```mermaid
erDiagram
    users ||--o{ bookings : makes
    events ||--o{ seats : has
    events ||--o{ bookings : for
    bookings ||--o{ booking_seats : contains
    seats ||--o{ booking_seats : "appears in"
```

| Table | Columns | Constraints and indexes |
|---|---|---|
| `users` | id, email, password_hash, full_name, role (`USER`/`ADMIN`), created_at | unique `email` (stored lower-case) |
| `events` | id, title, description, venue, city, starts_at, price_paise, total_seats, created_by, created_at | index `(city, starts_at)`; check `price_paise > 0` |
| `seats` | id, event_id, row_label, seat_number, status (`AVAILABLE`/`HELD`/`BOOKED`), price_paise | unique `(event_id, row_label, seat_number)`; index `(event_id, status)` |
| `bookings` | id, user_id, event_id, status, total_paise, idempotency_key, expires_at, payment_ref, created_at, updated_at | unique `(user_id, idempotency_key)`; index `(user_id, created_at)`; index `(status, expires_at)` |
| `booking_seats` | booking_id, seat_id | primary key `(booking_id, seat_id)` |

- All ids are integers (`BIGSERIAL`/identity). Timestamps are `timestamptz` in UTC.
- **Money is integer paise** (`₹499.00` = `49900`), never floats, because floats cannot represent money exactly.
- `price_paise` is copied onto each seat at creation (so prices can differ per seat later), and `bookings.total_paise` stores the
  amount charged at that moment: a later price change must not change an old booking.
- `booking_seats` is a join table (many-to-many): one booking has many seats; one seat can appear in many bookings over time
  (cancelled, then re-booked).

---

## 6. State machines

```mermaid
stateDiagram-v2
    direction LR
    [*] --> PENDING: hold seats
    PENDING --> CONFIRMED: payment ok
    PENDING --> CANCELLED: user cancels
    PENDING --> EXPIRED: 5 min passed
    CONFIRMED --> CANCELLED: user cancels (refund)
```

| Seat | Allowed moves |
|---|---|
| `AVAILABLE` → `HELD` | a booking is created |
| `HELD` → `BOOKED` | payment succeeded |
| `HELD` → `AVAILABLE` | booking cancelled or expired |
| `BOOKED` → `AVAILABLE` | confirmed booking cancelled |

A pure function `can_transition(current, target)` guards every booking status change. Anything else raises `InvalidStateTransition` → `409`.
Payment failure keeps the booking `PENDING` (user can retry until it expires) and returns `402 Payment Required`.

---

## 7. API

All routes under `/api/v1` except `/health`. Auth = `Authorization: Bearer <jwt>`.

| Method and path | Auth | Success | Errors | Notes |
|---|---|---|---|---|
| `GET /health` | - | 200 | 503 | Reports Postgres and Redis; 503 only if Postgres is down (Redis down = `degraded`, still 200) |
| `POST /auth/register` | - | 201 user | 409 email taken, 422 | Password min 8 chars; hash never returned |
| `POST /auth/login` | - | 200 `{access_token, token_type, expires_in}` | 401, 429 | Same 401 message for unknown email and wrong password; 429 after 5 failed attempts in a minute |
| `GET /users/me` | user | 200 user | 401 | |
| `POST /events` | admin | 201 event | 401, 403, 422 | Body includes `rows` (1-26) and `seats_per_row` (1-50); seats created in the same transaction |
| `GET /events` | - | 200 page | 422 | Query: `city`, `q` (title contains, case-insensitive), `from_date`, `to_date`, `sort` (`starts_at` / `-starts_at` / `price` / `-price`), `page` (≥1), `size` (1-50, default 10). Response: `{items, page, size, total}` |
| `GET /events/{id}` | - | 200 event + `available_seats` | 404 | Cached in Redis (cache-aside) |
| `PATCH /events/{id}` | admin | 200 event | 403, 404 | Partial update; invalidates the cache key |
| `GET /events/{id}/seats` | - | 200 list of seats | 404 | Ordered by row, then number |
| `POST /bookings` | user | 201 booking | 400 too many seats, 404, 409 seat taken, 422 missing header, 429 | Header `Idempotency-Key` required; body `{event_id, seat_ids}`, 1-6 unique seats |
| `POST /bookings/{id}/pay` | owner | 200 booking CONFIRMED | 402 payment failed, 404, 409 expired / wrong state | Body `{payment_token}`; token `"fail"` makes the fake gateway decline |
| `POST /bookings/{id}/cancel` | owner | 200 booking CANCELLED | 404, 409 | Releases seats; refunds if it was CONFIRMED |
| `GET /bookings` | user | 200 page | 401 | Only my bookings, newest first, with event title and seat labels (`A1`, `A2`) |
| `GET /bookings/{id}` | owner | 200 booking | 404 | Another user's booking returns **404**, not 403 (do not leak that it exists) |

**Error format (every error, including 422 and 500)**

```json
{ "error": { "code": "SEAT_UNAVAILABLE", "message": "Seats already taken: [12, 13]", "request_id": "3f2a..." } }
```

- Custom exception classes (`NotFoundError`, `ConflictError`, ...) carry `status_code` and `code`; one exception handler turns them into
  this JSON. Unknown exceptions are logged with the stack trace and return a generic `500 INTERNAL_ERROR` (no stack trace to the client).
- Rate-limited responses include a `Retry-After` header.

---

## 8. Key flows

### 8.1 Hold seats (`POST /bookings`) — the core of the project

```mermaid
sequenceDiagram
    participant U as User
    participant API as Router
    participant S as BookingService
    participant DB as PostgreSQL
    U->>API: POST /bookings (Idempotency-Key: k1, seat_ids [12,13])
    API->>S: create_booking(user, event, seats, key)
    S->>DB: SELECT booking WHERE user_id=? AND idempotency_key=k1
    alt key already used
        DB-->>S: existing booking
        S-->>U: 201 same booking (no new work)
    else new key
        Note over S,DB: transaction starts
        S->>DB: INSERT booking (PENDING, expires_at = now + 5 min) -- claims the key
        S->>DB: SELECT ... FROM seats WHERE id IN (12,13) AND event_id=? AND status='AVAILABLE' ORDER BY id FOR UPDATE SKIP LOCKED
        alt got fewer rows than requested
            S->>DB: ROLLBACK (booking row disappears too)
            S-->>U: 409 SEAT_UNAVAILABLE
        else got all seats
            S->>DB: UPDATE seats SET status='HELD', INSERT booking_seats, set total
            S->>DB: COMMIT
            S-->>U: 201 booking
        end
    end
```

Why each piece exists (say these in the interview):

- **Transaction**: lock, status change and booking insert succeed together or not at all (atomicity).
- **`FOR UPDATE`**: locks the seat rows until commit, so a second transaction cannot also read them as available.
- **`SKIP LOCKED`**: if another user is locking the seat right now, do not wait for them; treat it as taken and answer `409` fast.
- **`AND status = 'AVAILABLE'`**: a seat that is already held/booked is simply not returned.
- **`ORDER BY id`**: all transactions lock rows in the same order, which prevents deadlocks.
- **Idempotency key race**: the booking row is inserted *before* the seats are locked. If two requests with the same key arrive
  together, the second `INSERT` waits on the unique index `(user_id, idempotency_key)` until the first commits, then fails with
  `IntegrityError`; the service rolls back, re-reads and returns the first booking (proved by a 10-thread test).

### 8.2 Pay (`POST /bookings/{id}/pay`)

1. In one transaction: load the booking `FOR UPDATE`; 404 if not mine.
2. If status is not `PENDING` → 409. If `is_expired(now, expires_at)` → mark `EXPIRED`, release seats, commit, then 409 `BOOKING_EXPIRED`.
3. Call `payment_gateway.charge(amount_paise, token, reference=booking_id)`.
   - Declined → raise `PaymentFailedError` (402); booking stays `PENDING`.
   - Approved → booking `CONFIRMED`, store `payment_ref`, seats `BOOKED`, commit.
4. Log "booking confirmed" (stands in for sending an email).

Note for interviews: in a real system the payment provider is external and slow, so you would not call it while holding a DB lock;
you would use a webhook. Kept simple here on purpose.

### 8.3 Cancel and expiry

- Cancel: lock booking, `can_transition(status, CANCELLED)`, seats back to `AVAILABLE`, refund via the gateway if it was `CONFIRMED`.
- Expiry sweeper (started in the FastAPI `lifespan`, runs every 30 s):
  `SELECT id FROM bookings WHERE status='PENDING' AND expires_at < now() ORDER BY expires_at LIMIT 100 FOR UPDATE SKIP LOCKED`,
  then mark each `EXPIRED` and release its seats. `SKIP LOCKED` means two app instances can run the sweeper without processing the
  same booking twice.
- The sweeper logic lives in a plain function `expire_pending_bookings(session, now)` so tests can call it directly with a fake `now`.

### 8.4 Event detail cache (cache-aside)

1. `GET event:{id}` from Redis → hit: return it.
2. Miss: read Postgres, `SET event:{id} <json> EX 60`, return it.
3. `PATCH /events/{id}` and any booking change for that event → `DEL event:{id}` (so `available_seats` stays fresh).
4. Redis down → log a warning and read from Postgres (the cache is an optimisation, never the source of truth).

### 8.5 Rate limiting (fixed window)

- Key `rl:{scope}:{identity}:{window}` where `window = now // 60`.
- `INCR` the key; if the result is 1, `EXPIRE` it for 60 s; if the result is above the limit → 429 with `Retry-After`.
- Login: 5 **failed** attempts per minute per client IP (successful logins are not counted, so many users behind one IP can still log in).
  Create booking: 10 per minute per user.
- Redis down → allow the request (fail open) and log a warning.
- Trade-off to mention: a fixed window allows a burst at the window edge; sliding window or token bucket smooth that.

---

## 9. Domain functions (pure, unit-tested first)

| Function | Returns |
|---|---|
| `can_transition(current: BookingStatus, target: BookingStatus) -> bool` | whether the move is allowed |
| `validate_seat_request(seat_ids: list[int], max_seats: int = 6) -> None` | raises on empty, duplicates or too many |
| `find_unavailable(requested: list[int], locked: list[int]) -> list[int]` | requested ids that were not locked |
| `calculate_total(prices_paise: list[int]) -> int` | sum in paise |
| `hold_expires_at(now: datetime, hold_minutes: int) -> datetime` | expiry time |
| `is_expired(now: datetime, expires_at: datetime) -> bool` | `now >= expires_at` |

Time is always passed in as an argument, never read inside, so tests control it.

---

## 10. Code layout

```
TicketRush/
  app/
    main.py                 # create_app(): middleware, routers, exception handlers, lifespan (sweeper)
    core/
      config.py             # Settings (pydantic-settings, reads env / .env)
      database.py           # engine, SessionLocal, Base, get_session dependency
      redis_client.py       # Redis client + get_redis dependency
      security.py           # hash_password, verify_password, create_access_token, decode_access_token
      errors.py             # AppError hierarchy + exception handlers
      logging.py            # logging config, request_id context variable
      middleware.py         # request id + access log middleware
    domain/
      booking_rules.py      # pure functions from section 9
    models/                 # SQLAlchemy models: user, event, seat, booking
    schemas/                # Pydantic request/response models (DTOs)
    repositories/           # user_repo, event_repo, seat_repo, booking_repo
    services/               # auth_service, event_service, booking_service, cache_service, rate_limiter
    payments/
      gateway.py            # PaymentGateway Protocol + FakePaymentGateway
    api/
      deps.py               # get_current_user, require_admin, service factories
      v1/                   # auth.py, users.py, events.py, bookings.py
      health.py
    workers/
      expiry.py             # expire_pending_bookings() + async loop
    scripts/
      seed.py               # admin user + 2 sample events
  alembic/                  # migrations (one initial migration with every constraint and index)
  tests/
    conftest.py
    unit/                   # domain + security, no DB
    integration/            # API tests with TestClient + real Postgres/Redis, incl. test_concurrency.py
                            # (helpers.py: shared helpers; conftest.py: fixtures)
  scripts/race.py           # live demo: N concurrent requests for one seat against the running API
  docker/postgres-init.sql  # creates ticketrush_test on first start
  Dockerfile
  docker-compose.yml
  .github/workflows/ci.yml
  requirements.txt, requirements-dev.txt
  pyproject.toml            # ruff + pytest config
  .env.example
  README.md
```

---

## 11. Configuration defaults

| Setting (env var) | Default |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://ticketrush:ticketrush@localhost:5432/ticketrush` |
| `TEST_DATABASE_URL` | same server, database `ticketrush_test` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `JWT_SECRET` | none in code; `.env.example` has a placeholder |
| `JWT_EXPIRE_MINUTES` | 30 |
| `HOLD_MINUTES` | 5 |
| `MAX_SEATS_PER_BOOKING` | 6 |
| `EVENT_CACHE_TTL_SECONDS` | 60 |
| `LOGIN_RATE_LIMIT_PER_MIN` | 5 (failed attempts) |
| `BOOKING_RATE_LIMIT_PER_MIN` | 10 |
| `EXPIRY_SWEEP_SECONDS` | 30 |
| `CORS_ORIGINS` | `http://localhost:3000` |

---

## 12. Tests (what each one proves)

| Level | Test | Proves |
|---|---|---|
| Unit | every domain function, table-driven (`pytest.mark.parametrize`) | business rules without a DB |
| Unit | hash/verify password, create/decode JWT, expired and tampered JWT rejected | auth basics |
| Integration | register, duplicate email 409, login, wrong password 401, `/users/me` | auth flow |
| Integration | user cannot create an event (403), no token (401) | authorization |
| Integration | list events with filter, sort, pagination | query logic |
| Integration | hold → pay → CONFIRMED; seats become BOOKED | happy path |
| Integration | pay with token `fail` → 402, booking still PENDING | payment failure |
| Integration | same `Idempotency-Key` twice → one booking, same id | idempotency |
| Integration | another user's booking → 404 | ownership |
| Integration | `expire_pending_bookings` with `now` 6 min later frees seats | expiry |
| Integration | 6th login after 5 failures in a minute → 429; 11th booking in a minute → 429 | rate limit |
| Integration | Redis down: `/health` says degraded, event detail still 200 | fail open |
| **Concurrency** | 20 threads, each its own session and user, try to book the same seat → exactly 1 success, 19 conflicts, seat HELD once (5 rounds) | **no double booking** |
| **Concurrency** | same `Idempotency-Key` sent by 10 threads at once → 1 booking, all get the same id | **no duplicate booking** |

`FakePaymentGateway` is a **fake** (a working simple implementation). One test uses `unittest.mock` to assert `refund` was called on
cancel of a confirmed booking: that is an **interaction** test, the rest are **state** tests.

---

## 13. Interview prep

### Questions this project lets you answer with code

1. **How do you prevent double booking?** Transaction + `SELECT ... FOR UPDATE SKIP LOCKED` on the seat rows, `status='AVAILABLE'`
   filter, ordered locking. Proven by the 20-thread test and `scripts/race.py` (50 buyers → 1 × 201, 49 × 409).
   Removing `FOR UPDATE` makes the test fail: 18 of 20 buyers got the same seat.
2. **Optimistic vs pessimistic locking?** Pessimistic = lock first (`FOR UPDATE`), good for hot rows with high contention, like one popular
   seat. Optimistic = a `version` column and `UPDATE ... WHERE version = ?`, retry on 0 rows; good when conflicts are rare.
3. **What is ACID?** Atomicity (all or nothing: the hold), Consistency (constraints hold), Isolation (locks stop two holds seeing the same
   free seat), Durability (committed = on disk).
4. **Isolation levels?** Postgres default is READ COMMITTED. A naive "read then write" can lose updates there; `FOR UPDATE` fixes that.
   SERIALIZABLE would also work but makes you retry serialization failures.
5. **What if the client retries the booking request?** Idempotency key + unique constraint; a retry gets the first result.
6. **Why an index on `(city, starts_at)`?** The list query filters by city and sorts by date; a composite index serves both. Column
   order matters: equality column first, range/sort column second. Indexes speed reads but slow writes and use space.
7. **JWT vs sessions?** JWT is self-contained and stateless (any instance can verify it, no lookup); hard to revoke before expiry, so keep
   it short-lived and add refresh tokens. Sessions are server-side and easy to revoke but need shared storage.
8. **Why bcrypt and not SHA-256?** bcrypt is slow on purpose and salted, so brute force and rainbow tables are expensive. Hashing is
   one-way; encryption is reversible.
9. **401 vs 403 vs 404?** 401 = who are you? 403 = I know you, not allowed. 404 for other people's bookings so we do not reveal they exist.
10. **How does your cache stay correct?** Cache-aside with a 60 s TTL and delete-on-write. Postgres stays the source of truth; Redis down
    means slower, not wrong.
11. **How does rate limiting work?** Fixed window counter with `INCR` + `EXPIRE` in Redis, shared by all app instances, 429 + `Retry-After`.
    Login counts only failed attempts (brute-force protection); booking counts every request.
12. **Offset vs cursor pagination?** Offset is simple and allows "jump to page N", but gets slow for deep pages and can skip/repeat rows
    when data changes. Cursor (keyset) pagination fixes both; I would switch to it for the bookings history at scale.
13. **What happens to unpaid holds?** Sweeper expires them every 30 s; pay also checks expiry itself, so a late payment is refused even
    if the sweeper has not run yet.
14. **How is the code structured and why?** Router → service → repository, DI with `Depends`, pure domain functions. Each layer is
    testable alone; the payment provider can be swapped because the service depends on the `PaymentGateway` interface.
15. **How do you avoid N+1 queries?** `GET /bookings` loads bookings with their event and seats using joins/`selectinload` in a fixed number
    of queries instead of one query per booking.
16. **How do you prevent SQL injection?** The ORM always sends parameterized queries; user input is never concatenated into SQL.
17. **What is `async def` vs `def` in FastAPI?** `async def` runs on the event loop, so blocking calls inside it freeze every request;
    `def` endpoints run in a thread pool. I use `def` with a sync DB driver.
18. **How do you deploy it?** Docker image, Docker Compose with Postgres and Redis healthchecks, migrations run on start; CI runs lint and
    tests on every push.

### What I would add next (talking points, not built)

- Split into services (auth, catalog, booking, payment) only when teams or scaling needs differ; add an API gateway.
- Real payment provider with signed **webhooks** (HMAC) and an **outbox** table to publish events reliably to Kafka.
- **Refresh tokens** with rotation; OAuth (Google login).
- **WebSockets** (or SSE) for a live seat map.
- Celery/RQ for emails; Prometheus + Grafana metrics; OpenTelemetry tracing.
- Read replica for history queries; cursor pagination; a load test with k6 to find the real bottleneck.

### Be honest

- It is one service tested on a laptop. Say "proved with a 20-thread concurrency test", never "handles millions of users".
- Only quote numbers you actually ran (the concurrency test, `scripts/race.py` output).
