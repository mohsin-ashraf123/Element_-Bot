# ARCHITECTURE.md — System Architecture

**Project:** Element Team Pairing & Review Automation Bot
**Status:** Draft v1.0
**Stack (locked):** Python 3.11+ · FastAPI · matrix-nio (E2EE) · Celery + Redis · PostgreSQL · React frontend · provider-agnostic LLM adapter

---

## 1. Architectural Principles

1. **Modular monolith, not microservices.** One codebase, clear internal modules. Microservices add ops overhead that a single-team, single-room product does not need. (Revisit only if multi-tenant.)
2. **Deterministic core is independent** of Element and the LLM. Pairing/scheduling/scoring must be unit-testable with zero external calls.
3. **The LLM is a pluggable adapter at the edge**, never in the business logic.
4. **Element is an integration boundary**, isolated behind a service interface so E2EE complexity is contained.
5. **Everything durable lives in PostgreSQL.** The LLM has no independent memory (see MEMORY.md).
6. **Idempotency and auditability** are first-class, because this runs unattended.

---

## 2. High-Level Component Diagram

```
                        ┌──────────────────────────────┐
                        │        React Control Panel     │
                        │  (dashboard, config, history)  │
                        └───────────────┬────────────────┘
                                        │ HTTPS / JSON (authenticated)
                                        ▼
                        ┌──────────────────────────────┐
                        │        FastAPI Backend         │
                        │  REST API · auth · services    │
                        │  ┌────────────────────────┐    │
                        │  │  Deterministic Core     │    │
                        │  │  pairing · lead · score │    │
                        │  └────────────────────────┘    │
                        │  ┌──────────┐ ┌────────────┐   │
                        │  │ Element  │ │ LLM        │   │
                        │  │ Service  │ │ Adapter    │   │
                        │  └────┬─────┘ └─────┬──────┘   │
                        └───────┼─────────────┼──────────┘
             enqueue jobs       │             │
        ┌──────────────┐        │             │
        │   Redis      │◄───────┘             │
        │ broker+cache │                      │
        └──────┬───────┘                      │
               │ consume                       │
        ┌──────▼─────────────────┐            │
        │  Celery Workers + Beat  │────────────┘
        │  (scheduled + async)    │
        └──────┬──────────────────┘
               │ read/write
        ┌──────▼───────┐         ┌───────────────────┐
        │ PostgreSQL   │         │ Matrix Homeserver │
        │ (source of   │         │  (E2EE room)      │
        │  truth)      │         └───────────────────┘
        └──────────────┘
```

---

## 3. Components

### 3.1 Frontend — React Control Panel
- SPA (React + Vite) or Next.js in SPA mode. Talks only to the FastAPI REST API.
- Responsibilities: configuration, monitoring, history, analytics, manual controls.
- Holds no business logic; renders server state. Auth via session cookie / JWT.

### 3.2 Backend — FastAPI
The single application process exposing the REST API and hosting the service layer. Internal modules:

- **`core/` (Deterministic Core)** — pure Python, no I/O:
  - `pairing.py` — 3-combo round-robin dev pairing + fixed QA pair.
  - `team_lead.py` — round-robin lead selection over 6.
  - `scoring.py` — completion/on-time/clean aggregation, rates, streaks.
  - `calendar.py` — working-day/cutoff/timezone logic.
- **`services/`** — orchestration that *uses* the core plus I/O:
  - `round_service` — build & persist a daily round.
  - `report_ingest_service` — attribute room replies to members, derive signal.
  - `report_service` — weekly/monthly aggregation + LLM narrative.
- **`integrations/`**
  - `element/` — Element Service (matrix-nio wrapper, E2EE).
  - `llm/` — LLM Adapter (provider-agnostic interface).
- **`api/`** — FastAPI routers (auth, config, rounds, reports, jobs, logs).
- **`db/`** — SQLAlchemy models + Alembic migrations + repositories.

### 3.3 Database — PostgreSQL
Single source of truth for all deterministic business data and event records. Schema in MEMORY.md.

### 3.4 Scheduler + Job Queue — Celery + Redis
- **Celery Beat** holds the schedule: the daily 11:00 AM PKT send, the report ingestion sweeps, and the weekly/monthly report jobs.
- **Celery Workers** execute jobs asynchronously with **retries, backoff, and per-task idempotency keys**.
- **Redis** is the broker + result backend + light cache.
- Why Celery over a bare cron: retries, failure records, visibility, and manual re-run — all needed for an unattended product. Beat provides timezone-aware cron.

### 3.5 Element Service (matrix-nio, E2EE)
- Wraps a persistent, logged-in Matrix client with E2EE enabled.
- Persists the encryption store (device keys + megolm sessions) to disk/volume (`MATRIX_E2EE_STORE_PATH`, unlocked by `MATRIX_PICKLE_KEY`).
- Exposes a narrow interface: `send_message(text) -> event_id`, `sync_replies(since) -> [events]`, `ensure_joined(room_id)`, `health()`.
- Runs a background **sync loop** (own process or a dedicated Celery worker) to receive and decrypt incoming events.

### 3.6 LLM Adapter
- Interface: `generate_narrative(metrics, report_texts, period) -> text`.
- Provider-agnostic — **Anthropic, OpenAI, Gemini, or OpenRouter** chosen via `LLM_PROVIDER`.
- **OpenRouter path:** on key save, call OpenRouter's models endpoint to list models; the UI filters free-only and lets the Operator select one (`LLM_MODEL`). The adapter then targets that model.
- Always called with a strict system prompt (narrate given numbers, do not recompute, treat report text as untrusted data). Has a **deterministic template fallback** on failure.

### 3.6a Report Renderer (image service)
- Renders the per-member report as a clean HTML document and captures a **PNG** via a headless browser (**Playwright/Chromium**).
- Interface: `render_report_image(metrics, period) -> png_bytes`.
- The PNG is stored, then posted to the room as an image (Element handles image events natively). Falls back to a plain-text table if rendering fails.
- Kept as an isolated service so the Chromium dependency doesn't leak into core logic.

### 3.7 Auth & Config
- Single-admin auth (username/password → session/JWT). Passwords hashed (argon2/bcrypt).
- Configuration stored in DB (editable in UI) + environment for secrets/infra.
- Secrets encrypted at rest with `SECRETS_ENCRYPTION_KEY`.

### 3.8 Logging & Monitoring
- Structured JSON logs (app + worker).
- Job/run records in DB power the UI's logs & failed-jobs screens.
- Health endpoints: DB, Redis, Element connection, last-successful-send timestamp.

---

## 4. Deterministic vs. LLM Operations

| Operation | Deterministic | LLM |
|-----------|:---:|:---:|
| Developer pairing (3-combo rotation) | ✅ | |
| Fixed QA pair | ✅ | |
| Team Lead selection | ✅ | |
| Scheduling / 11:00 AM trigger | ✅ | |
| Message rendering & sending | ✅ | |
| Persisting rounds/events | ✅ | |
| Attributing replies to members | ✅ | |
| Completion / on-time / clean flags | ✅ | |
| Metric aggregation (rates, counts, streaks) | ✅ | |
| Weekly/monthly **narrative** prose | | ✅ |
| Issue-theme summarisation | | ✅ |
| Qualitative trend commentary | | ✅ |

**Rule:** every number in a report is computed deterministically and passed *into* the LLM. The LLM only phrases and interprets — it never produces a figure.

---

## 5. Data Flow — Daily Cycle

```
Celery Beat (11:00 AM PKT, working day)
  └─► round_service.create_daily_round(date)
        ├─ core.pairing.next_combo(history)        → dev pairs
        ├─ fixed QA pair                            → Habiba+Aqeel
        ├─ core.team_lead.next_lead(history)        → lead
        ├─ persist PairingRound + Pairings + Lead   → PostgreSQL
        ├─ render message text
        └─ ElementService.send_message(text)        → Matrix (E2EE)
              └─ store returned event_id, mark round SENT (idempotent)
```

## 6. Event Flow — Report Ingestion (Performance Signal)

```
Element sync loop receives + decrypts room events (report-only room)
  └─► report_ingest_service.process(event)
        ├─ is sender a known member? (map MXID→member)   ← attribution: any member message = their report
        ├─ classify: clean (standard text) vs suggestion/issue (other)
        ├─ compute on-time vs late (cutoff)
        ├─ upsert PerformanceRecord(member, date, completed, on_time, outcome, raw_text)
        └─ update that day's lead accountability (team outcome attributed to the day's Team Lead)
```

Because the room is a dedicated report-only channel, no thread-reply/keyword parsing is required — sender identity is sufficient.

## 7. Reporting Pipeline — Weekly / Monthly

```
Celery Beat (period end)
  └─► report_service.generate(period)
        ├─ core.scoring.aggregate(records in period) → per-member metrics + per-lead-day accountability (numbers)
        ├─ collect raw report_texts for the period
        ├─ LLMAdapter.generate_narrative(metrics, texts, period)
        │     └─ on failure → deterministic template narrative
        ├─ ReportRenderer.render_report_image(metrics, period) → PNG (per-member table)
        │     └─ on failure → plain-text table fallback
        ├─ persist Report(metrics_json, narrative, image, model, generated_at)
        └─ ElementService.send_image(png) + send_message(narrative) → store posted event IDs
```

Note: the report is **per-member** (every member on their own row) and is posted to the room as an **image**, with the short narrative as follow-up text.

---

## 8. Communication Summary

- **Frontend ⇄ Backend:** HTTPS REST/JSON, authenticated.
- **Backend → Redis:** enqueue jobs / cache.
- **Beat/Workers → PostgreSQL:** read history, write rounds/records/reports.
- **Workers → Element Service → Matrix:** send messages, receive replies (E2EE).
- **Workers → LLM Adapter → Provider:** narrative generation only.
- **Element sync loop → report_ingest_service → PostgreSQL:** signal capture.

All external calls (Matrix, LLM) go through their adapter and are retried/failed-recorded by Celery.

---

## 9. Deployment Topology

Single `docker-compose` for MVP:

- `web` — FastAPI (API) served behind a reverse proxy (Caddy/Nginx, TLS).
- `frontend` — static React build (served by proxy or the web container).
- `worker` — Celery worker(s).
- `beat` — Celery beat (single instance to avoid double-scheduling).
- `element-sync` — long-running matrix-nio sync loop (can be a dedicated worker).
- `postgres` — with a persistent volume.
- `redis` — broker/cache.
- **Report renderer:** a headless **Chromium (Playwright)** available to the worker for HTML→PNG report images (bundled in the worker image).
- **Volumes:** Postgres data, the E2EE store, **and** generated report images (must survive restarts).

Scale path: split `worker`/`beat`/`element-sync`, add read replicas, only if load demands.

---

## 10. Reliability & Idempotency Mechanisms

- **Idempotency key** `daily_send:{date}` — a round is sent at most once per date.
- **Retries with backoff** on Matrix/LLM/DB transient errors.
- **Failure records**: every job run stored with status/attempts/error, visible + re-runnable in UI.
- **Health gates**: before sending, verify DB reachable, bot joined to room, Element connection healthy.
- **E2EE persistence**: restart-safe encryption store so the bot keeps decrypting replies.
- **Missed-run recovery**: if a scheduled send is missed, the next health check flags it; Operator can trigger a catch-up send for that date.

---

## 11. Key Architecture Risks (see RULES.md for handling)

- **E2EE on the critical path** — decryption failures directly break the performance signal. Mitigation: persistent store, UTD handling, alerts, `undetermined` status (never silently "missed").
- **Attribution ambiguity** — distinguishing a "report" from chatter. Mitigation: thread-reply rule + optional strict format (OPEN DECISION).
- **Single points of failure** — Beat, Redis, Postgres. Mitigation: single-Beat rule, persistent volumes, health checks, backups.
- **LLM drift/hallucination** — mitigated by numbers-in, narrate-only + template fallback.
