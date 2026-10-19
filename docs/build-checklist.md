# TicketRush Build Checklist


Eleven phases, one working system at the end of each. Tick a task only when it works and has a test.

## Phase 1: Foundations

Syllabus sections 1 to 6, 17 to 19, 27, 28. Goal: one FastAPI skeleton with the layered structure you will copy into every service.

**Repo and tooling**

- [ ] Create the monorepo `ticketrush/` with the layout from the low-level design; `git init`, `.gitignore`, `.env.example`
- [ ] One Python 3.12 virtual env per service with `pyproject.toml`: FastAPI, uvicorn, SQLAlchemy 2, Alembic, psycopg, pydantic-settings, httpx, pytest, ruff, mypy
- [ ] Pre-commit running ruff and mypy

**Compose and networking**

- [ ] `deploy/compose.yml` with a `core` profile: Postgres 16 (three databases from an init script) and Redis 7 (`maxmemory 64mb`, `allkeys-lru`)
- [ ] Healthchecks on Postgres and Redis; services wait for healthy dependencies; named volumes for data and explicit port mappings (explain each)
- [ ] Run one service in a container and reach Postgres by service name, not `localhost`; write 3 lines on port vs IP vs DNS name vs localhost
- [ ] Experiment: 1 vs 2 uvicorn workers; a `time.sleep` inside an `async def` handler blocks every request, the same code in a plain `def` handler does not; note the numbers

**Service skeleton (build it in booking first, then copy)**

- [ ] `create_app()` factory, pydantic-settings config from environment variables, and a composition root that builds dependencies
- [ ] Routers under `/v1` with route groups; `/healthz` for liveness and `/readyz` that checks Postgres and Redis
- [ ] Middleware: request id (accept or generate), access log, timing header
- [ ] Central exception handlers that return the error JSON format; a custom 422 shape; unknown errors become a generic 500
- [ ] Pydantic request and response models kept separate from database models (DTOs)
- [ ] Layers: router to service to repository; only repositories import SQLAlchemy
- [ ] Protocols for `Clock`, `Cache`, `EventPublisher` with a real and a fake version each, injected through constructors; FastAPI `Depends` only assembles the graph

**Logging**

- [ ] JSON structured logs with `request_id`, `service`, `level`; use DEBUG, INFO, WARN, ERROR on purpose; never log passwords, tokens or secrets
- [ ] Move logging, errors and config helpers into `libs/common`

**HTTP practice**

- [ ] Make 10 `curl` calls and note method, status, headers and Content-Type; trigger a 2xx, 3xx, 4xx and 5xx on purpose
- [ ] Compare the same call in browser dev tools and `curl -v`: connection, headers, cookies

**Review**

- [ ] Swagger at `/docs` shows the models and error responses
- [ ] 5 small tests: health, error format, request id echo, validation error shape, unknown route
- [ ] Tag `phase-1`

**Done when:** `docker compose --profile core up` starts Postgres, Redis and one service; `/readyz` goes red when you stop Redis.

## Phase 2: Identity service

Syllabus sections 7 to 12 and the browser side of 37. Goal: one service that supports cookie sessions, JWT and Google login, with roles and safe browser behaviour.

**Registration and passwords**

- [ ] Alembic migration for `users`, `oauth_accounts`, `refresh_tokens` with the constraints from the low-level design
- [ ] `POST /auth/register`: validate email and password rules, hash with Argon2, duplicate email returns 409, the hash never appears in any response or log
- [ ] Login gives the same error for an unknown email and a wrong password

**Cookie sessions**

- [ ] `POST /auth/session`: random session id, stored in Redis with a sliding 24 hour TTL, cookie with `Secure`, `HttpOnly`, `SameSite=Lax`
- [ ] Auth middleware loads the session from the cookie; logout deletes the Redis key and the cookie
- [ ] Test: an expired session returns 401; a copied cookie stops working after logout

**JWT**

- [ ] `POST /auth/login`: 15 minute access token (claims `sub`, `role`, `iat`, `exp`, `jti`) and a random 7 day refresh token stored only as a hash
- [ ] A shared `verify_token` in `libs/common` that pins the algorithm, checks signature and expiry, and rejects `alg: none`
- [ ] `POST /auth/refresh` rotates the pair and links old to new; presenting an already-used refresh token revokes the whole family
- [ ] Write 6 lines on sessions vs JWT and where TicketRush uses each (cookie for the web page, JWT for API clients and k6)

**Google OAuth**

- [ ] Create a Google OAuth client in test mode
- [ ] `GET /auth/google/start` with a `state` value (and PKCE); callback checks `state`, exchanges the code, reads the profile, links or creates the user, then issues your own session or JWT
- [ ] Explain in your own words: client, authorization server, resource server, user consent, and why OAuth is authorization while login with Google adds identity on top

**Authorization**

- [ ] Roles `attendee`, `organizer`, `admin`; a `require_role` dependency; an ownership helper that returns 404 for resources that are not yours
- [ ] A test table of endpoint by role (allowed, 403, 404) that runs on every change

**Browser security (needs the tiny front end)**

- [ ] A plain HTML and JS page served on `localhost:3000` that logs in and calls the API on another port
- [ ] CORS: allow-list one origin with credentials; watch a failing preflight in dev tools, read the `OPTIONS` request, fix it; try `*` with credentials and see the browser refuse
- [ ] CSRF: cookie-session writes require an `X-CSRF-Token` that matches; a forged cross-site form fails
- [ ] XSS: send CSP and `X-Content-Type-Options` headers, escape user text in the page, show a script injection attempt being neutralised
- [ ] SQL injection: write one vulnerable string-built query on a scratch route, exploit it once, replace it with a parameterized query, delete the scratch route
- [ ] Secrets only from environment variables; `.env` is ignored by git
- [ ] Login brute-force limit in Redis: 5 failures per 15 minutes per account and per IP (sliding window)

**Tests**

- [ ] Small tests: password policy, token verification, refresh rules (no I/O)
- [ ] Medium tests on real Postgres and Redis: register, login, `/me`, refresh rotation, reuse detection, logout
- [ ] Tag `phase-2`

**Done when:** you can log in from the browser page by cookie, by JWT with `curl`, and with Google, and a stolen refresh token is detected.

## Phase 3: Catalog service

Syllabus sections 3, 6, 16, 20, 21, 30. Goal: a read-heavy MongoDB service with search, cursor pagination and every caching pattern on your list.

**MongoDB and the model**

- [ ] Add MongoDB 7 to Compose; connect with the async driver; collections `events` and `seat_layouts`
- [ ] Indexes: `(city, starts_at)`, a text index on `title`, `(organizer_id)`; confirm each is used with `explain()`
- [ ] Experiment: model an event whose attributes differ by type (concert, match, play) in both Mongo and Postgres; write 8 lines on when each fits

**CRUD and API**

- [ ] `POST /events` (organizer), `GET /events/{id}`, `PATCH /events/{id}` (own events only), `DELETE /events/{id}` as a soft cancel
- [ ] Request and response models; validation: `starts_at` in the future, price tiers are positive integers in paise
- [ ] Use `verify_token` from Phase 2; other people's events return 404
- [ ] OpenAPI examples on every route

**Search, filter, sort, pagination**

- [ ] `GET /events` with `q`, `city`, `from`, `to`, `category`, `sort`, and `limit` capped at 50
- [ ] Cursor pagination on `(starts_at, _id)` with an opaque base64 cursor; a malformed cursor returns 400
- [ ] Prove the point: insert events while paging; offset paging skips or repeats rows, cursor paging does not

**Caching patterns (each one on purpose)**

- [ ] A `Cache` protocol with a Redis implementation (JSON values) and an in-memory fake
- [ ] Cache-aside on `GET /events/{id}`: miss reads Mongo, sets the key with a 60 second TTL plus 0 to 10 seconds of random jitter
- [ ] Invalidation: `PATCH` and `DELETE` remove the key; list results use a version number in the key that you bump on any change
- [ ] Penetration defense: a missing id is cached as a 10 second negative entry
- [ ] Stampede defense: `SET lock NX EX` so one request reloads while the others wait; test with 200 concurrent requests on a cold key and assert exactly 1 Mongo read
- [ ] Breakdown defense: a hot key expiring under load uses the same lock; test it with a fake clock
- [ ] Read-through: a `CacheLoader.get_or_load(key, loader, ttl)` wrapper that handlers call so they never see the miss path
- [ ] Write-back: `INCR views:{id}` on every read and a flush function that writes the counts to Mongo (it runs as a real job in Phase 6)
- [ ] Eviction: set `maxmemory 64mb` with `allkeys-lru`, flood Redis with junk keys, watch `evicted_keys` and the hit rate; write 5 lines on LRU
- [ ] Write 5 lines on when not to cache (per-user data, rarely read data, data that must be exact)
- [ ] Count hits and misses and expose the hit ratio on a debug endpoint (becomes a Prometheus metric in Phase 8)

**Publishing an event**

- [ ] `POST /events/{id}/publish` calls booking's `/internal/events/{id}/inventory` with a service token, 2 second timeout and retries; the event becomes ON\_SALE only if the call succeeds (booking is a stub until Phase 4)

**Performance notes**

- [ ] Load test `GET /events/{id}` with and without the cache (k6 or `hey`) and write both p95 numbers in your notes

**Tests**

- [ ] Small tests: cursor encode and decode, jitter range, publish rules
- [ ] Medium tests against the Compose Mongo and Redis (you switch to Testcontainers in Phase 9)
- [ ] Tag `phase-3`

**Done when:** a cold key under 200 parallel requests causes one database read, and a cursor walk over 1,000 events returns each event exactly once.

## Phase 4: Booking core

Syllabus sections 13 to 15, 39 to 48, 53, 54. Goal: seats, holds and bookings in Postgres that stay correct under concurrency, with the core logic written test-first. This is the heart of the project; give it the most time.

**Functional core first (test-driven)**

- [ ] Write failing tests, then code, for `can_transition` on the seat, booking and payment machines: every legal pair passes, every illegal pair is refused
- [ ] Same for `choose_seats_outcome`, `hold_expiry` and `is_expired` (time is an argument, never `now()` inside), `price_total` in integer paise, and `decide_webhook_action` with table-driven cases
- [ ] One red, green, refactor commit per function; write 3 lines on where TDD did not help (SQL, I/O)
- [ ] Keep `domain/` free of FastAPI, SQLAlchemy and Redis imports and enforce it with a lint rule

**Schema**

- [ ] Alembic migrations for `seats`, `holds`, `bookings`, `booking_seats`, `seat_events`, `outbox`, `inbound_webhooks`, `processed_messages` with every constraint and partial index from the low-level design
- [ ] SQLAlchemy models and repositories; the service layer owns the transaction boundary, repositories never commit
- [ ] SQL practice: hand-write 10 queries on this schema (INNER and LEFT JOIN, GROUP BY with HAVING, a subquery, aggregates, keyset vs OFFSET paging) in `docs/sql-practice.sql`
- [ ] Write 5 lines on normalization: why `price_paise` is copied onto the seat and why the booking stores its own total

**Inventory**

- [ ] `POST /internal/events/{id}/inventory` creates seats from a layout in batches inside one transaction; calling it twice creates no duplicates; service token required
- [ ] Replace the Phase 3 stub so publishing an event works end to end

**Holds**

- [ ] `POST /holds` using the `SKIP LOCKED` transaction from the design: at most 6 seats, 201 on success, 409 with the taken ids, hold, seat events and outbox rows in one commit
- [ ] `DELETE /holds/{id}` releases your own hold only
- [ ] `expire_due_holds(now, batch)` as a callable function, tested with a fake clock (the worker that runs it arrives in Phase 6)
- [ ] Concurrency test: 200 parallel attempts on one seat give exactly 1 success and 199 conflicts, 0 server errors; repeat 20 times
- [ ] Deadlock experiment: two buyers request overlapping seats in opposite order; show the deadlock without `ORDER BY id`, then show it gone with it
- [ ] Isolation experiment: reproduce a lost update with a naive read then write at READ COMMITTED, fix it with `FOR UPDATE`, and note when SERIALIZABLE would be needed
- [ ] Rollback test: force a failure after the seat update and assert nothing changed

**Bookings and idempotency**

- [ ] `POST /bookings` from an active hold with an `Idempotency-Key`; a retry returns the stored response; the same key with a different body returns 422
- [ ] Race test: send the same key 50 times in parallel and get exactly 1 booking
- [ ] Response is 202 with PENDING\_PAYMENT; the payment call goes to a fake gateway for now
- [ ] `GET /bookings/{id}` (owner only, else 404) and `GET /me/bookings` with cursor paging on `(created_at, id)`
- [ ] `POST /bookings/{id}/cancel`, allowed only from CONFIRMED

**Indexes and the first EXPLAIN**

- [ ] Seed 100,000 seats; run `EXPLAIN ANALYZE` on the hold query with and without the partial index and save both plans (the 1M run is in Phase 11)
- [ ] Write notes on index costs (write overhead, storage) and why composite column order matters

**Tests**

- [ ] Test doubles: `FakePaymentGateway`, `FakeClock`, `FakeEventPublisher`; use one mock on purpose and write 4 lines on state vs interaction testing
- [ ] Label tests small, medium and large with pytest markers; use FastAPI \`TestClient\` and one \`AsyncMock\` with \`patch\` once each, and note when each is the right tool
- [ ] Tag `phase-4`

**Done when:** the 200-way race test passes 20 times in a row and a retried booking request never creates a second booking.

## Phase 5: Payment service and saga

Syllabus sections 35, 36, 38 (receiving side), 65 and webhook security from 37. Goal: a second real service, a booking and payment saga, and webhooks that survive duplicates, delays and disorder.

**The mock payment service**

- [ ] Scaffold `payment` from the Phase 1 skeleton; migration for `payments`, `refunds`, `webhook_outbox`
- [ ] `POST /internal/payment-intents`: idempotent on the key (same key returns the same intent), status CREATED
- [ ] A processing loop that picks CREATED rows with `FOR UPDATE SKIP LOCKED`, waits 0.5 to 3 seconds, sets SUCCEEDED or FAILED by a configurable rate, and writes the `webhook_outbox` row in the same transaction
- [ ] A delivery loop that signs each payload (HMAC-SHA256 over `timestamp.body`) and sends `X-Signature`, `X-Timestamp`, `X-Delivery-Id`; retries up to 5 times with backoff and jitter; stops on a 2xx
- [ ] Idempotent `POST /internal/payments/{id}/refund` that emits a refunded webhook
- [ ] `POST /internal/chaos` with switches: delay, failure rate, duplicate rate, reorder, drop the first N deliveries (all off by default)

**Calling payment from booking**

- [ ] A `PaymentClient` protocol with an HTTP version (httpx, 2 second timeouts, 2 retries with jitter, same idempotency key each time) and a fake
- [ ] A circuit breaker as a pure state function plus a wrapper: 5 failures open it for 30 seconds, then one half-open trial; test with a fake clock
- [ ] A reconciler: bookings stuck in PENDING\_PAYMENT with no payment id get their intent re-requested; old pending ones ask payment for the status

**Receiving webhooks in booking**

- [ ] `POST /webhooks/payments` reads the raw bytes before parsing JSON
- [ ] `verify_signature` in constant time with a 5 minute timestamp tolerance; a bad signature returns 401 and nothing is processed
- [ ] Dedupe inside the transaction with `INSERT ... ON CONFLICT DO NOTHING` on the delivery id; a duplicate returns 200
- [ ] Apply `decide_webhook_action`: succeeded, failed and refunded; a failed event after a succeeded one is ignored and logged
- [ ] Compensation: success after the hold expired makes the booking EXPIRED and requests a refund
- [ ] The handler answers quickly and makes no network calls inside the transaction
- [ ] Tests: the same webhook 10 times changes state once; reordered events; tampered body; wrong secret; missing header; an old valid payload replayed after the tolerance window is rejected

**Saga tests**

- [ ] Happy path: hold, book, pay, webhook, CONFIRMED, seats BOOKED (medium test with the real payment container)
- [ ] Payment fails: seats go back to AVAILABLE and the booking is PAYMENT\_FAILED
- [ ] Kill payment mid-flight: the booking stays PENDING\_PAYMENT, and the reconciler finishes it after restart
- [ ] Chaos run: 100 bookings with 20% failures, 30% duplicates and reordering; assert that no seat has two active bookings and every succeeded payment ends as a confirmed booking or a refund

**Service boundaries and contracts**

- [ ] No cross-database queries anywhere; `/internal/*` needs a service token
- [ ] A shared JSON schema for the webhook payload in `libs/common/contracts`; both sides test against it
- [ ] Write notes on: network and partial failure, timeout vs retry vs idempotency, at-most-once vs at-least-once vs exactly-once, ordering, eventual consistency
- [ ] Tag `phase-5`

**Done when:** the chaos run passes its invariants three times in a row, and you can explain the saga from the diagram without notes.

## Phase 6: Events and real-time

Syllabus sections 22 to 26, 38 (sending side), 64, 66. Goal: the outbox and Kafka pipeline, background jobs, the projector, live seat updates over WebSocket, and signed outbound webhooks.

**Outbox and Kafka**

- [ ] Add Redpanda to Compose (`events` profile); create `seat-events` and `booking-events` with 3 partitions; inspect with `rpk`
- [ ] A real `EventPublisher` with idempotent producer settings and `event_id` as the key
- [ ] Outbox relay in the worker: `LIMIT 100 FOR UPDATE SKIP LOCKED`, publish, then mark `published_at`; test a crash between publish and mark and confirm consumers cope with the duplicate
- [ ] Run two consumers in one group and watch partitions get split; write 8 lines on topic, partition, offset, consumer group, per-key ordering and retention

**Background jobs with RQ**

- [ ] Worker container (2 replicas) with queues `expiry`, `email`, `webhooks`, `default`
- [ ] A loop that calls `expire_due_holds` every 5 seconds; with 2 workers no hold is processed twice (test)
- [ ] Job retries with increasing intervals; inspect the failed registry and job status from the CLI or dashboard
- [ ] Confirmation email job to Mailpit, idempotent per booking id
- [ ] The view-counter flush job from Phase 3 (every 30 seconds)

**Consumers and the dead-letter topic**

- [ ] `notifier` consumer group in the worker: manual offset commit after processing, enqueues the email and organizer webhook jobs, deduplicates with `processed_messages`
- [ ] After 3 failed attempts a message goes to `booking-events.dlq` with the error in a header; write a command that replays one DLQ message
- [ ] Poison message test: a malformed event does not block the partition

**Projector (CQRS read side)**

- [ ] `projector` service: consumer group on both topics; writes the Redis seat view and publishes on `seats:{event_id}` in the same handler
- [ ] Hourly sales table updated with `INSERT ... ON CONFLICT DO UPDATE`; every handler is safe to run twice
- [ ] Replay drill: wipe the Redis view, reset offsets to earliest, rebuild, and compare with Postgres using a `verify_view.py` script
- [ ] Add `schema_version` to every payload; consumers ignore unknown fields
- [ ] Measure the staleness window between a commit and the view update and write it down
- [ ] Write notes on CQRS, the append-only `seat_events` log as event sourcing in miniature, event ordering across keys, and event replay

**Real-time seat map**

- [ ] `WS /ws/events/{id}`: snapshot on connect, then deltas; authenticated; ping and pong heartbeat; rooms per event
- [ ] Each replica subscribes to `seats:{event_id}` in Redis and forwards to its own sockets
- [ ] Run 2 replicas on different ports: hold a seat through replica A and see it on a browser connected to B
- [ ] Fire-and-forget loss: stop the subscriber, miss an update, and show the client repairing itself by refetching the snapshot on reconnect
- [ ] Seat map page in the tiny front end: grid coloured by status, live updates, hold countdown
- [ ] Connection limit per user; slow clients are dropped instead of blocking others

**Outbound organizer webhooks**

- [ ] `POST` and `GET /organizer/webhooks`; the secret is generated and shown once
- [ ] Delivery job: HMAC signature, 5 second timeout, response size cap, no redirects, HTTPS only (plain HTTP to localhost only behind a dev flag)
- [ ] `is_blocked_ip` written test-first with a list: `127.0.0.1`, `10.0.0.5`, `169.254.169.254`, `::1`, an IPv4-mapped IPv6 address, a decimal-integer IP; resolve DNS yourself and connect to the checked address
- [ ] 5 retries with backoff and jitter; `webhook_deliveries` rows with attempts and status; a dead delivery can be replayed by hand
- [ ] A local receiver script that verifies the signature, fails half of the calls, and dedupes by delivery id
- [ ] Tag `phase-6`

**Done when:** you can stop the projector, make 50 bookings, restart it, and the seat view and sales table catch up without a gap or a double count.

## Phase 7: Gateway, rate limiting and scaling

Syllabus sections 1 (stateless), 13 (replicas), 30 to 34. Goal: one entry point, abuse protection, and a system that runs as several replicas behind a load balancer.

**The gateway service**

- [ ] Scaffold `gateway`; a central route table mapping `/v1/auth`, `/v1/events`, `/v1/holds` and the rest to services, with a pooled `httpx` client and 3 second timeouts
- [ ] Authenticate once here: verify the JWT or look up the cookie session in Redis, then send `X-User-Id` and `X-User-Role` upstream; strip any client-supplied copies of those headers
- [ ] Move the CORS allow-list to the gateway and re-run the Phase 2 browser checks
- [ ] Request id created or forwarded; upstream failures become 502 and 504 in the standard error format
- [ ] Aggregate `/readyz` across services; block `/internal/*` (test that it returns 404 from outside)
- [ ] Write notes on service discovery: Compose DNS names now, Kubernetes Services in Phase 10, a registry such as Consul in theory

**Rate limiting**

- [ ] `token_bucket_step` written test-first as a pure function
- [ ] The same logic as one Redis Lua script so the check and update are atomic; keys per user and per IP
- [ ] 429 with `Retry-After` and `X-RateLimit-*` headers; per-route policies from the design defaults
- [ ] A scratch module with fixed-window and sliding-window limiters; send a burst across a window boundary and write down how they differ
- [ ] Two gateway replicas share limits through Redis (test)
- [ ] Redis down: reads fail open and holds fail closed (test both)

**Load balancing and TLS**

- [ ] Nginx with an upstream of 2 gateway replicas: round robin, then `least_conn`; `max_fails` health behaviour; `X-Forwarded-For` and `X-Forwarded-Proto`; WebSocket upgrade headers; keepalive
- [ ] TLS with `mkcert` certificates, an HTTP to HTTPS redirect and an HSTS header; write 6 lines on the TLS handshake and what a certificate proves
- [ ] `ETag` on event detail so a repeat request gets a 304

**Horizontal scaling**

- [ ] Run booking with 2 replicas; confirm both receive traffic from per-instance logs
- [ ] Statelessness check: kill one replica under traffic and see no errors beyond in-flight requests
- [ ] Connection pools: set pool size and overflow per replica so the total stays under Postgres `max_connections`; reproduce pool exhaustion (pool of 2, 50 concurrent requests) and read the symptom; optional PgBouncer in transaction mode with notes on its limits
- [ ] Postgres read replica in Compose (primary with replication settings, replica from `pg_basebackup`)
- [ ] Route `GET /me/bookings` and organizer sales to the replica through a second engine; show replication lag, and handle read-your-writes by sending a user's reads to the primary for 5 seconds after they write
- [ ] Profile one slow endpoint (`py-spy` or `cProfile`), find an N+1 query and fix it; keep the before and after
- [ ] Smoke-run the hold load test with 1, 2 and 3 booking replicas and note throughput, p95 and database CPU (the full measured runs are Phase 11)
- [ ] Write notes on vertical vs horizontal scaling and how you identified the bottleneck

**Tests and tag**

- [ ] Medium tests: rate limit across two gateway instances, header stripping, `/internal` blocked
- [ ] Tag `phase-7`

**Done when:** all traffic enters through Nginx and the gateway, a hold flood gets 429s instead of errors, and killing one replica of any service does not stop the system.

## Phase 8: Observability

Syllabus sections 27 to 29 and the measuring half of 30. Goal: when something breaks you can see what, where and why in under a minute.

**Logs**

- [ ] The request id travels gateway, services, payment, Kafka headers and worker jobs, and appears in every log line (use context variables)
- [ ] Loki and a log shipper in the `obs` profile; in Grafana, search one `request_id` and see a booking's log lines from every service
- [ ] Log the key events (hold created, conflict, webhook verified, duplicate, rejected) at the right level; check that no secret, token or password is ever logged
- [ ] Server logs keep the stack trace of errors; the HTTP response never does

**Metrics**

- [ ] `/metrics` in every service; request counter by route template, method and status (never the raw path, to avoid label explosion)
- [ ] Request duration histogram with buckets from 25 ms to 5 s
- [ ] Business metrics: holds by result, hold conflicts, bookings by status, webhook events by result, cache requests by result, unpublished outbox rows, Kafka consumer lag, RQ queue depth, hold expiry lag, DB pool in use, circuit breaker state
- [ ] Prometheus scrape config; every target shows UP
- [ ] Grafana dashboards provisioned from JSON files in the repo: Overview (rate, errors, p50, p95, p99), Booking, Cache hit ratio, Queues and Kafka, Database

**Traces**

- [ ] OpenTelemetry in FastAPI, httpx, SQLAlchemy and Redis, exported to Jaeger
- [ ] Propagate W3C `traceparent` over HTTP, Kafka headers and RQ job metadata
- [ ] Open one booking trace that spans gateway, booking and payment, and a second that follows the async tail (webhook, confirm, event, notifier); save screenshots
- [ ] A custom span around the `SKIP LOCKED` transaction with the seat count as an attribute

**Health checks and alerts**

- [ ] Confirm liveness only says "the process is alive" and readiness checks dependencies; verify with Compose and, later, Kubernetes probes
- [ ] Alert rules: p95 above your threshold for 5 minutes, 5xx rate above 2%, outbox lag above 60 seconds, consumer lag above 1,000, dead-letter topic not empty, webhook failure rate
- [ ] Fault-inject (stop payment, stop the projector, fill the DLQ) and watch each alert fire in Prometheus
- [ ] One short runbook per alert: what it means and the first 3 things to check

**Use it**

- [ ] Find the slowest route from the dashboard, explain why, and note the fix you would make
- [ ] Tag `phase-8`

**Done when:** you can follow one booking across 5 services by request id in Grafana and by trace in Jaeger, and stopping the payment service raises an alert.

## Phase 9: Quality gates and CI

Syllabus sections 37 (scanning), 39 to 52, 55 to 61, 62. Goal: every claim in this project is backed by an automated check that runs on each push.

**Test infrastructure**

- [ ] Testcontainers fixtures for Postgres, MongoDB, Redis and Redpanda, started once per session with clean state per test; replace the Compose-dependent tests from Phase 3
- [ ] Hermetic rule: block real network access in tests (except the containers) and read time only through `Clock`
- [ ] Network tests: a fake HTTP server (`respx` or an httpx mock transport) that returns 500s, slow responses, timeouts and connection resets; assert the client's retries and the breaker
- [ ] Time tests: expiry exactly at `expires_at`, one second before, one second after
- [ ] Database tests: migrations upgrade from empty and downgrade one step cleanly; a test for every unique and partial index that tries to break it

**Test pyramid**

- [ ] Label every test small (no I/O), medium (containers, one service) or large (whole stack); target roughly 70, 20 and 10 percent
- [ ] Two large end-to-end tests on the full Compose stack: (1) register, hold, book, webhook, confirmed, email in Mailpit, organizer webhook received; (2) 50 concurrent buyers on 10 seats, exactly 10 confirmed
- [ ] Contract tests: both sides of the payment webhook and each service call validate against shared JSON schemas
- [ ] A one-page table in `docs/` mapping each kind of test to what it protects (your practical scope model)

**Quality measures**

- [ ] Coverage with branches: gate at 85% overall and 95% on `domain/`; read the uncovered branches instead of chasing 100%
- [ ] Mutation testing with `mutmut` on `domain/`; add tests for surviving mutants and record the score before and after
- [ ] Flaky tests: run the medium suite 20 times in a loop; fix one real flake (for example a sleep replaced by polling with a timeout) and write what caused it
- [ ] Complexity: ruff `C901` with a limit of 10; refactor anything above it
- [ ] `ruff check`, `ruff format`, `mypy --strict` on `domain/` and services, and an import rule that keeps `domain/` free of I/O libraries

**Security scanning**

- [ ] `bandit`, `pip-audit`, `gitleaks` and Trivy on the images; fix or document every finding

**CI/CD with GitHub Actions**

- [ ] `ci.yml`: lint, types, small tests, medium tests, coverage gate, image build with cache, Trivy scan, Compose end-to-end tests, upload test and coverage reports
- [ ] A matrix per service with path filters so only changed services rebuild
- [ ] Dockerfiles: multi-stage, slim base, non-root user, pinned versions, `.dockerignore`, `HEALTHCHECK`
- [ ] Push images to GHCR on `main` with the commit SHA as the tag; a deploy workflow behind a manual approval; rollback means redeploying the previous tag
- [ ] Branch protection: the CI check is required to merge
- [ ] Write notes on environments, config through environment variables, secrets in GitHub secrets, versioned images and rolling updates
- [ ] Tag `phase-9`

**Done when:** a pull request that breaks the double-booking test, a coverage gate, a lint rule or adds a leaked secret is blocked by CI.

## Phase 10: Kubernetes and resilience

Syllabus sections 63, 65, 66. Goal: run the system on an orchestrator, break it on purpose, and prove you can recover.

**Kubernetes on kind**

- [ ] Install `kind` and `kubectl`; create a cluster with 1 control plane and 2 workers; load your images into it
- [ ] Namespace `ticketrush`; Deployments for gateway, booking, identity, catalog and payment; Postgres and Redis as simple dev-only workloads (say in the README that production would use managed services)
- [ ] ClusterIP Services so `booking` resolves by DNS; an ingress controller in place of the Compose Nginx
- [ ] ConfigMaps for settings and Secrets for passwords and the JWT key; write 3 lines on why base64 is not encryption
- [ ] Readiness and liveness probes on `/readyz` and `/healthz`, a startup probe, and resource requests and limits
- [ ] `kubectl scale` booking to 3; delete a pod and watch it come back; roll out a new image; use `rollout undo`
- [ ] Optional: a CPU-based HorizontalPodAutoscaler with metrics-server
- [ ] Write notes on pods, containers, Services, Deployments, scaling, service discovery and orchestration; run a k6 smoke test against the cluster

**Failure drills (for each: predict, break, observe, write down the result)**

- [ ] Stop Redis: caching, limits and the live seat map degrade, bookings stay correct
- [ ] Stop payment: the breaker opens, bookings wait in PENDING\_PAYMENT, the reconciler heals them after restart
- [ ] Stop Redpanda: outbox rows pile up, then drain after restart with nothing lost
- [ ] Kill a worker mid-job: the job is retried and no second email goes out
- [ ] Kill a booking replica under load: traffic continues
- [ ] Restart Postgres during a hold flood: clients get 503 or retry, and no seat is left half-written
- [ ] Add 3 seconds of latency to payment with Toxiproxy: timeouts and the breaker behave as designed
- [ ] Cut the network between booking and payment with Toxiproxy and see the same recovery
- [ ] Skew a webhook timestamp past the tolerance and confirm it is rejected

**Backup and recovery**

- [ ] A `pg_dump` script per database; restore into a fresh container, compare row counts, and time it (that is your measured RTO)
- [ ] Read about WAL archiving and point-in-time recovery and write 10 lines; try `pg_basebackup` plus archived WAL if you have time
- [ ] `mongodump` and restore for the catalog; note what is rebuildable (the Redis seat view from the event log, the sales table from events)
- [ ] A one-page disaster recovery note: source of truth per store, RPO and RTO targets, restore order, what to rebuild

**Decision records in `docs/adr/` (10 to 15 lines each: context, options, decision, consequences)**

- [ ] 1\. Postgres for bookings and MongoDB for the catalog
- [ ] 2\. Outbox pattern instead of publishing to Kafka inside the request
- [ ] 3\. Saga with compensation instead of a distributed transaction
- [ ] 4\. `SKIP LOCKED` holds instead of optimistic locking
- [ ] 5\. At-least-once delivery with idempotent consumers instead of exactly-once
- [ ] 6\. Multi-region (not built): a home region per event, async replication, global read replicas of the catalog, and what fails over and how
- [ ] Short notes: full event sourcing vs your `seat_events` log, and why Kafka transactions are out of scope
- [ ] Tag `phase-10`

**Done when:** all nine drills have a written result, a restore from backup is timed, and the cluster survives deleting any single pod.

## Phase 11: Prove it and ship it

Syllabus sections 13 to 15, 30, 60, 61 at full scale. Goal: replace every X on your resume with a measured number and put the system on a public URL.

**Seed data and EXPLAIN ANALYZE**

- [ ] A seed script that loads 1,000,000 seats across 200 events, plus users and 100,000 bookings, using `COPY`; note how long it takes
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` before and after each index for the hold query, the `my bookings` cursor query and the organizer sales query; record plan type and milliseconds in `docs/perf.md`
- [ ] Check index sizes; drop one unused index and measure the insert speed difference

**k6 load tests (run each 5 times and keep the median; note your machine specs)**

- [ ] Flash sale: ramp to 500 virtual users for 2 minutes against 10,000 seats; afterwards run a SQL check that no seat has two active bookings (must return 0 rows); record successes, conflicts, 429s, p50, p95, p99 and requests per second
- [ ] Browse: event detail and list with the cache on and off; record p95 for both
- [ ] Scaling curve: the hold endpoint with 1, 2 and 3 booking replicas; chart requests per second and p95, and name the bottleneck (lock waits or database CPU)
- [ ] Mixed traffic: 80% browse, 15% hold, 5% book
- [ ] Soak test for 15 minutes; watch memory, open connections and file descriptors for leaks
- [ ] Put thresholds in the k6 scripts (p95 limit, error rate under 1%) so a short smoke version can run in CI; save results as JSON under `loadtest/results/`

**Deploy**

- [ ] Pick the target: one small VPS running the Compose stack is the simplest way to host every service (kind stays your local cluster)
- [ ] Provision it with a firewall (22, 80, 443), a non-root user and SSH keys only
- [ ] A subdomain with an A record and a Let's Encrypt certificate; HTTPS only
- [ ] A production Compose file: no database ports exposed, secrets from an env file, restart policies, resource limits, log rotation
- [ ] CI deploy job: push images, then `docker compose pull && up -d` over SSH, run a smoke test, roll back to the previous tag if it fails
- [ ] Public read-only Grafana dashboards (viewer only, no admin exposed) or screenshots if you prefer not to expose it
- [ ] Public API docs at `/docs`, a demo account, one small demo event with 200 seats, and a nightly reset
- [ ] A nightly backup cron on the server and one verified restore
- [ ] Write down the monthly cost

**Write-up and interview prep**

- [ ] README: what it is, architecture diagram, how to run it in 3 commands, how to run each test level, the load-test table, links to the decision records, known limits
- [ ] A 90 second screen recording: two browsers watching the same seat map update live, then a flash-sale run
- [ ] Resume entry from the template with your real numbers, the Live link, and the skills line updated
- [ ] Practise the 8 interview questions out loud with the diagrams, and a 3 minute walkthrough of the whole system
- [ ] List 5 honest weaknesses of the project and what you would do next
- [ ] Final gate: tag `v1.0.0`, repository public, secret scan clean, CI badge green

**Done when:** a stranger can open the live URL, book a demo seat, and see your numbers in the README that you can reproduce with one command.
