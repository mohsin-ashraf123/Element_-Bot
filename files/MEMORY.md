# MEMORY.md — Memory & Data Strategy

**Project:** Element Team Pairing & Review Automation Bot
**Status:** Draft v1.0

**Core principle:** all deterministic business data lives in **PostgreSQL** as the single source of truth. The LLM has **no independent long-term memory** — it is stateless and receives, per call, exactly the structured context it needs. We do **not** dump everything into an "LLM memory" system.

---

## 1. Memory Philosophy

- **Structured DB for facts.** Pairings, leads, events, and performance records are precise, queryable, and auditable — perfect for a relational DB, wrong for a fuzzy vector/LLM memory.
- **LLM is stateless.** Any history the LLM needs for a report is *retrieved from the DB and passed into the prompt* at generation time. Nothing is "remembered" by the model between calls.
- **No vector database in MVP.** Data volume is tiny (6 members, one room). Retrieval is simple SQL by date range/member. A vector store is only worth considering far in the future for semantic search over years of report text (explicitly out of scope now).
- **Minimise data leaving the system.** Only what a given report needs is sent to the LLM (see §7 and PRD §15 privacy OPEN DECISION).

---

## 2. What the Bot Must Remember (and where)

| Memory | What it is | Store | Lifetime |
|--------|-----------|-------|----------|
| **Roster & roles** | The 6 members, Matrix IDs, role, active flag | DB (`members`) | Long-term |
| **QA fixed-pair config** | Habiba+Aqeel locked pairing | DB (`settings`) | Long-term |
| **Team Lead order** | Ordered round-robin list | DB (`settings`) | Long-term |
| **Pairing rotation state** | Which combo/lead is next | **Derived from DB history** (not stored as mutable state) | Long-term |
| **Daily pairing records** | Each round's pairs, QA, lead, date, combo | DB (`pairing_rounds`, `pairings`, `team_lead_assignments`) | Long-term |
| **Daily Element message/event** | Rendered text + Matrix event ID + send status | DB (`element_events`) | Long-term |
| **Performance records** | Per member/day: completed/on-time/clean/raw text | DB (`performance_records`) | Long-term |
| **Weekly/monthly reports** | Metrics JSON + narrative + **rendered PNG** + provider/model + posted event IDs | DB (`reports`) + image file/volume | Long-term |
| **Lead accountability** | Team outcome on each member's lead-days | DB (`lead_accountability`) | Long-term |
| **LLM provider/model** | Chosen provider (incl. OpenRouter) + selected model | DB (`settings`) | Long-term |
| **LLM insights** | The generated narrative text + prompt/model metadata | DB (`reports.narrative`, `reports.llm_meta`) | Long-term |
| **Configuration** | Schedule, cutoff, working days, attribution mode | DB (`settings`) | Long-term |
| **Job/run history** | Every scheduled/async job's status/attempts/error | DB (`jobs`) | Medium-term (retention policy) |
| **Audit log** | Manual actions & corrections | DB (`audit_log`) | Long-term |
| **E2EE store** | Matrix device keys + megolm sessions | **Encrypted file/volume** (not the app DB) | Long-term, restart-critical |
| **In-flight job payloads / cache** | Transient task data | Redis | Ephemeral |
| **Secrets** | Matrix token, LLM key | Env + encrypted-at-rest in DB (`SECRETS_ENCRYPTION_KEY`) | Long-term |

---

## 3. What Should NOT Be Stored (or stored carefully)

- **Full raw room history** — the bot stores only members' **attributed report messages**, not every message in the room. (Avoids over-collection and privacy creep.)
- **Nothing in an LLM "memory" service** — no persistent model-side memory.
- **Secrets in plaintext** — never; encrypted at rest, masked in UI, never logged.
- **Un-decryptable content** — a UTD event is recorded only as metadata (`undetermined`), not fabricated text.
- **Derived numbers as the source of truth** — metrics are **recomputed** from base records on demand/aggregation, so a correction to a base record naturally flows through. (Reports snapshot the numbers at generation time for the historical record.)

---

## 4. Data Model (relational sketch)

```
members(id, name, matrix_user_id, role, active, created_at, deactivated_at)

settings(key, value_json, updated_at, updated_by)         -- schedule, cutoff, QA pair, lead order, attribution mode

pairing_rounds(id, round_date, combo_index, status,        -- status: pending|sent|send_failed
               created_at)

pairings(id, round_id → pairing_rounds, member_a_id,
         member_b_id, pair_type)                            -- pair_type: DEV|QA|SOLO

team_lead_assignments(id, round_id → pairing_rounds, member_id)

element_events(id, round_id → pairing_rounds, kind,         -- kind: daily_message|report_post
               matrix_event_id, rendered_text, status,
               sent_at, error)

performance_records(id, member_id → members, record_date,
                    completed, on_time, outcome,            -- outcome: clean|has_issues|undetermined|missed
                    source_event_id, raw_text, created_at,
                    corrected, corrected_by)

lead_accountability(id, round_id → pairing_rounds, lead_member_id,  -- team outcome on this member's lead-day
                    team_completion, team_on_time, team_clean)      -- derived from that day's performance_records

reports(id, period_type, period_start, period_end,          -- period_type: weekly|monthly
        metrics_json, narrative, narrative_source,          -- narrative_source: llm|template
        image_path,                                          -- rendered per-member PNG posted to the room
        llm_provider, llm_model, llm_meta_json,
        generated_at, posted_image_event_id, posted_text_event_id, status)

jobs(id, job_type, scheduled_for, status, attempts,
     idempotency_key, error, started_at, finished_at)

audit_log(id, actor, action, target, old_value, new_value,
          reason, created_at)
```

Uniqueness/idempotency:
- one `pairing_rounds` per `round_date`;
- one `element_events(kind=daily_message)` per round;
- `jobs.idempotency_key` unique (e.g., `daily_send:2026-07-15`);
- one authoritative `performance_records` per (member, record_date) — extra reports retained but not double-counted.

---

## 5. Rotation State = Derived, Not Stored

The "next combo" and "next lead" are **computed from history**, not held as a mutable counter:
- Next combo = the combo after the last used `combo_index` in the most recent working-day round (wrapping C1→C2→C3).
- Next lead = position after the last assigned member in the configured lead order (skipping inactive).

Why: it's crash-safe, restart-safe, and self-correcting after skipped days — no drift between a counter and reality.

---

## 6. Retrieval for Reporting

Reporting never scans the LLM's "memory"; it queries the DB deterministically.

**Weekly report retrieval:**
1. `SELECT` all `performance_records` where `record_date` ∈ [week_start, week_end] and member active.
2. `core.scoring.aggregate()` → per-member rates, streaks, pair-level joins, **and per-member "as Team Lead" metrics** from `lead_accountability` (numbers only).
3. Collect the associated `raw_text` for `has_issues` records in the period.
4. Pass **(metrics_json + issue texts + period label)** to the LLM adapter for narrative.
5. Render the per-member table to a **PNG** (report renderer) for posting as an image.

**Monthly report retrieval:** same, over the calendar month, plus the previous weeks' aggregates for week-over-week trend context.

**What the LLM receives:** pre-computed numbers + relevant report texts only — never the whole DB, never other members' unrelated data beyond the period, never secrets.

---

## 7. Data Sent to the LLM (privacy boundary)

- Default: member names + period metrics + issue report texts.
- **OPEN DECISION — LLM DATA PRIVACY (see PRD §15):** optionally pseudonymise names ("Developer A") and/or truncate report texts before they leave the system. Must be resolved before enabling Phase 4 narratives.
- Report texts are treated as **untrusted input** (prompt-injection aware): the LLM is instructed to treat them as data, ignore embedded instructions, and never recompute numbers.

---

## 8. Retention & Backups

- **Long-term (keep):** members, rounds, pairings, leads, element_events, performance_records, reports, audit_log.
- **Medium-term (prune):** `jobs` older than a retention window (e.g., 90 days), keeping failures longer.
- **Ephemeral:** Redis cache/queue payloads.
- **Backups (Phase 5):** Postgres dumps **and** the E2EE store must both be backed up; losing the E2EE store means lost ability to decrypt ongoing room history. Document a restore runbook.

---

## 9. Summary

- Deterministic facts → **PostgreSQL** (queryable, auditable, corrections flow through).
- Encryption keys → **persistent encrypted store/volume** (restart-critical).
- Transient job data → **Redis**.
- LLM → **stateless**, fed retrieved structured context per report; no independent memory, no vector DB in MVP.
- Store **only** attributed reports, not the whole room; never fabricate missing data; keep numbers as the source of truth and let the LLM narrate them.
