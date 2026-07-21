# PHASES.md — Development Roadmap

**Project:** Element Team Pairing & Review Automation Bot
**Status:** Draft v1.0

A practical path from foundation → MVP → reliable reporting → production hardening. Each phase lists Objective, Features, Technical Work, Dependencies, Expected Output, and Definition of Done (DoD).

---

## Phase 0 — Foundation & Setup

**Objective:** Establish the skeleton, environments, and the deterministic core (no Element, no LLM yet).

**Features:** none user-facing; internal scaffolding.

**Technical work:**
- Repo structure (`core/`, `services/`, `integrations/`, `api/`, `db/`, `frontend/`).
- `docker-compose` with `web`, `worker`, `beat`, `postgres`, `redis`.
- Postgres + SQLAlchemy models + Alembic migrations for: `members`, `pairing_rounds`, `pairings`, `team_lead_assignments`, `settings`, `jobs`.
- `.env.example` with all variables (see ARCHITECTURE/PRD).
- Deterministic core: `pairing.py`, `team_lead.py`, `calendar.py` + **unit tests** (no I/O).

**Dependencies:** stack decisions (done).

**Expected output:** running containers; passing unit tests for pairing/lead/calendar.

**DoD:** `docker-compose up` works; given a history, the core returns the correct next combo and next lead deterministically; migrations apply cleanly.

---

## Phase 1 — Element Connectivity (E2EE) Proof

**Objective:** Reliably send and receive in the encrypted room. This de-risks the hardest part first.

**Features:** internal; a "connection status" check.

**Technical work:**
- Element Service on matrix-nio with E2EE enabled.
- Persistent encryption store (`MATRIX_E2EE_STORE_PATH` + `MATRIX_PICKLE_KEY`) mounted as a volume.
- `ensure_joined(room_id)`, `send_message()`, sync loop that receives + decrypts events.
- Health checks: connected, joined, last-sync.

**Dependencies:** Phase 0; Operator provides Matrix credentials + room ID; **bot account already joined to the room**.

**Expected output:** bot sends a test message to the encrypted room and successfully decrypts a manually-posted reply.

**DoD:** send works; a reply typed in Element is received and decrypted after a restart (proves store persistence); UTD events are logged, not crashed on.

---

## Phase 2 — MVP: Daily Pairing Loop

**Objective:** The full automated daily loop, end to end.

**Features (MVP):** FR-1…FR-6, FR-10 (subset), FR-12, FR-13.
- Team/role config (via seed + minimal API).
- Deterministic dev pairing + fixed QA + Team Lead.
- Celery Beat 11:00 AM PKT working-day trigger.
- Render + send daily message; persist round + event ID.
- Idempotency + retry on send.
- Single-admin auth; encrypted secret storage.
- Manual "send now" / "pause-resume".

**Technical work:**
- `round_service.create_daily_round()`.
- Beat schedule (timezone-aware) + idempotency key `daily_send:{date}`.
- Auth (session/JWT), secrets encryption with `SECRETS_ENCRYPTION_KEY`.

**Dependencies:** Phases 0–1.

**Expected output:** every working day at 11:00 AM the correct message appears in the room and is recorded.

**DoD:** three consecutive working days auto-send correctly with rotating combos + rotating lead; no duplicate on double-run; manual send + pause work.

---

## Phase 3 — MVP: Report Ingestion (Performance Signal)

**Objective:** Capture the performance signal correctly — the foundation for all reporting.

**Features (MVP):** FR-7, FR-9, FR-11, plus manual correction (FR-18 subset).
- Attribute room replies to members (thread-reply rule).
- Derive `completed` / `on_time` / `clean` per member per day.
- Store `performance_records`; handle `undetermined` (UTD/unattributable).
- Pairing history + logs/failed-jobs UI.
- Manual data correction with audit log.

**Technical work:**
- `report_ingest_service` in the sync loop (report-only room → any known member's message = their report; map sender → member).
- Standard clean-message matcher (normalised) to classify clean vs suggestion/issue.
- Cutoff logic; `undetermined` vs `missed` handling; per-lead-day accountability roll-up.

**Dependencies:** Phases 1–2.

**Expected output:** members' daily reports show up as structured records with correct flags.

**DoD:** over a test week, completion/on-time/clean flags match reality; a UTD event yields `undetermined` (not `missed`); a correction is audited and updates aggregates.

> **Gate before Phase 4:** run Phases 2–3 live for **2–4 weeks** to validate signal quality. Reports built on an unproven signal would be untrustworthy (the exact thing to avoid).

---

## Phase 4 — Post-MVP: Weekly & Monthly Reports

**Objective:** Turn validated data into readable weekly/monthly reports (deterministic metrics + LLM narrative).

**Features:** FR-14, FR-15, FR-16 (basic), FR-19 (provider config), and OD-7 resolution.
- Deterministic aggregation (rates, streaks, pair-level, per-member "as Team Lead").
- LLM Adapter narrative with template fallback; provider config incl. **OpenRouter** (fetch models, free-only filter, model select).
- **Report renderer:** per-member table → HTML → **PNG** via Playwright; post image + narrative to room.
- Store report (metrics, narrative, image, provider/model); analytics screens.

**Technical work:**
- `scoring.py` aggregation; `report_service.generate(period)`.
- LLM Adapter + strict prompt (numbers-in, narrate-only, injection-safe); OpenRouter model listing.
- `report_renderer` (Playwright/Chromium) HTML→PNG; Element image send.
- Weekly/monthly Beat triggers; report persistence before posting.
- Basic analytics charts in the UI.

**Dependencies:** Phase 3 + validated signal; LLM provider + key; Playwright/Chromium in worker image; **OD-7 (privacy) decided**.

**Expected output:** weekly/monthly per-member reports rendered as images, posted, and stored; numbers verifiable against raw records.

**DoD:** report numbers reconcile exactly with the DB; image renders and posts (text fallback works); LLM failure falls back to template; OpenRouter model selection works; privacy decision implemented.

---

## Phase 5 — Production Hardening

**Objective:** Make it robust, observable, and operable unattended.

**Features:** FR-17, FR-21, plus ops.
- Configurable schedule/cutoff/working-days; optional holiday list.
- Operator alerts (email/Matrix DM) on failures.
- Backups (Postgres + E2EE store), restore runbook.
- Rate-limit/backoff tuning; structured logging + dashboards.
- Full manual-controls surface.

**Technical work:**
- Alerting hooks; backup jobs; monitoring endpoints; catch-up/missed-run recovery.

**Dependencies:** Phase 4.

**Expected output:** system runs for weeks unattended; failures are visible and recoverable.

**DoD:** simulated failures (Matrix down, LLM down, worker restart) recover per RULES.md; backups restore successfully; alerts fire.

---

## Phase 6 — Future Enhancements (optional)

Multi-room/multi-team, real @-mentions & room commands, generalised pairing for N members, additional signal sources (reactions/forms), Slack/Teams adapters, BI export. Each is independently scoped later.

---

## Sequencing Summary

```
P0 Foundation → P1 Element E2EE → P2 Daily Loop (MVP) → P3 Signal Ingestion (MVP)
   → [2–4 week validation gate] → P4 Reports → P5 Hardening → P6 Future
```

The hardest risk (E2EE) is tackled early (P1); reports are deliberately withheld until the signal is proven (post-P3 gate).
