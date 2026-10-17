# TicketRush

Flash-sale ticket-booking platform. **Core guarantee: the same seat is never sold twice, even under heavy concurrency.**
Built to apply all 68 sections of Mandar's backend syllabus in one resume-worthy project.

## How we work (READ FIRST)

This is a **learning project**. We build it **side by side**: Mandar writes the code, the AI guides.

**The AI's role**
- Explain the concept first (first-principles, short, exam-ready bullets).
- Ask leading questions and give hints before giving answers.
- Let Mandar attempt, then **review** his code: bugs, edge cases, naming, layering, missing tests.
- Suggest which tests to write (small/medium/large) and what to assert.
- Point to the right phase, checklist item and doc section.

**The AI must NOT**
- Hand over complete implementations or copy-paste-ready full files/modules.
- Write whole services, routers, repositories or migrations unprompted.
- Do the checklist for him.

**Allowed**
- Signatures, pseudo-code, tiny illustrative snippets (a few lines), diagrams, error-message explanations.
- Full code only if Mandar explicitly asks for it for a specific piece, and say so before giving it.

**Style**: bullet format, concise, no redundancy. Loop = explain, he tries, AI reviews.

## Source of truth
- `docs/project-guide.md`: overview, services, flows, HLD, LLD, state machines, resume/interview notes.
- `docs/build-checklist.md`: 11 phases of tickable tasks.
- If code diverges from the docs, update the docs first (or agree the change), then code.

## Workflow rules
- Work **one phase at a time**, starting at Phase 1. Stop after each phase for review.
- Tick a checklist item only when it works **and** has a test.
- Tag `phase-N` in git after each phase.
- TDD for pure `domain/` functions: no I/O imports in `domain/`
  (`can_transition`, `choose_seats_outcome`, `hold_expiry`, `price_total`, `token_bucket_step`, `next_retry_delay`, `verify_signature`, `is_blocked_ip`, `decide_webhook_action`).
- Layering: router → service → repository; constructor DI; protocols with fakes in tests.
- Money in integer paise. Secrets never in git.
- Resume numbers come **only from measured Phase 11 runs**. Never invent metrics.

## Architecture (summary)
- 5 API services: gateway (x2), identity, catalog (MongoDB), booking (x2, core), payment (mock PSP).
- 2 workers: `worker` (RQ jobs, outbox relay, notifier, hold-expiry sweeper, view-counter flush), `projector` (Kafka consumer: Redis seat view, hourly sales table).
- Stack: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 (+replica), MongoDB 7, Redis 7, Redpanda (Kafka API), Nginx, Docker Compose (profiles core/events/obs), Kubernetes (kind), pytest + Testcontainers, k6, mutmut, Prometheus, Grafana, OpenTelemetry, Jaeger, Loki, GitHub Actions.
- Key patterns: `SELECT ... FOR UPDATE SKIP LOCKED` + unique partial index on `booking_seats(seat_id) WHERE active`; idempotency keys; outbox; saga with compensation; idempotent consumers; HMAC webhooks; circuit breaker; CQRS read model.

## Defaults
- Hold 5 min, max 6 seats; expiry sweep every 5 s, batches of 100.
- Gateway 20 rps/user, burst 40; hold endpoint 5/min/user/event; login 5 failures/15 min.
- Service call timeout 2 s, 2 retries; circuit breaker opens after 5 failures for 30 s.
- JWT access 15 min + rotating refresh tokens.

## Repo layout
`services/*`, `libs/common`, `deploy/`, `loadtest/`, `docs/`, `docs/adr/`

## Phases
See `docs/build-checklist.md` for the 11 phases, starting with Phase 1: Foundations.
