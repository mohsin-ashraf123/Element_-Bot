# PRD.md — Product Requirements Document

**Project:** Element Team Pairing & Review Automation Bot
**Owner:** Mohsin
**Status:** Draft v1.0 (pre-implementation)
**Last updated:** 2026-07-15

---

## 1. Product Overview

A web-controlled automation system that manages a **daily team pairing and peer-review workflow** inside a single, end-to-end-encrypted Element (Matrix) room.

Every working day at 11:00 AM (Asia/Karachi), a bot posts the day's developer pairs, the fixed QA pair, and the assigned Team Lead. Team members then report their review work back into the same room. The system records these reports as a structured **performance signal**, and on a weekly and monthly basis produces human-readable performance reports (assisted by an LLM) that are posted back to the room.

The operator (Mohsin) controls and monitors everything from a custom React web control panel.

---

## 2. Problem Statement

The team runs a daily pairing + peer-review routine manually. This creates recurring pain:

- Someone has to **remember to post pairs every morning**, and pairs are often repeated unfairly or chosen ad hoc.
- There is **no reliable record** of who was paired with whom, who was Team Lead, and who actually completed their review each day.
- There is **no objective view** of performance or progress over a week or month — only vague memory.
- Weekly/monthly summaries, if they happen at all, are subjective and time-consuming.

The result: unfair rotation, no accountability trail, and no data-driven picture of team activity.

---

## 3. Product Vision

A **reliable, self-running automation product** — not a throwaway script — that:

1. Guarantees a fair, deterministic daily pairing and Team Lead rotation.
2. Posts to Element on time, every working day, without human intervention.
3. Captures completion/quality data as a real, defensible signal (never fabricated).
4. Turns that data into clear weekly and monthly insights using an LLM only where narrative genuinely helps.
5. Gives the operator full visibility and manual override through a web control panel.

---

## 4. Goals

- **G1** — Deterministic, fair daily developer pairing with no blind repeats.
- **G2** — Keep Habiba + Aqeel as a permanently fixed QA pair.
- **G3** — Assign a daily Team Lead via round-robin across all 6 members.
- **G4** — Send the daily pairing message to the configured room at exactly 11:00 AM PKT on working days.
- **G5** — Persist every pairing round, Team Lead, and Element event in the database.
- **G6** — Capture each member's daily review report as a structured performance record.
- **G7** — Generate and post weekly and monthly performance reports.
- **G8** — Provide a control panel for configuration, monitoring, history, and manual controls.
- **G9** — Use the LLM strictly for analysis/insight/narrative — never for deterministic logic.

---

## 5. Non-Goals

- **NG1** — Not a general-purpose Matrix bot. It operates on **one** configured room only.
- **NG2** — Not a task/project management tool. It does not assign the actual review *content* or track tickets.
- **NG3** — Not a chat assistant. It does not answer arbitrary questions in the room (MVP).
- **NG4** — Not a multi-tenant SaaS. Single team, single operator (MVP).
- **NG5** — The LLM does not compute scores, invent metrics, or make personnel judgements.
- **NG6** — No automated performance penalties, HR actions, or ranking that affects people's standing (out of scope; sensitive).

---

## 6. Target Users

| User | Role | Needs |
|------|------|-------|
| **Operator (Mohsin)** | Admin of the control panel | Configure everything, monitor bot health, view history/reports, run manual actions |
| **Team members (6)** | Subjects of the workflow, room participants | Receive daily pairs in Element, post their review reports |
| **Team Lead (daily)** | One of the 6, rotating | Ensure the day's paired review work is completed |

Only the Operator uses the web app. Team members interact only via Element.

---

## 7. Team Structure

Fixed roster of **6 members** (configurable in the app):

**Developers (rotating pairs):** Uzair, Saad, Faz, Hamza
**QA (fixed pair):** Habiba, Aqeel
**Team Lead:** selected daily from all 6 via round-robin.

---

## 8. Core Workflows

### 8.1 Developer Pairing Workflow

The four developers are split into **two pairs per working day**, rotating so that over time every developer pairs with every other developer fairly.

**Key mathematical fact:** with exactly 4 developers there are only **3 distinct ways** to split them into two pairs:

| Combo | Pair 1 | Pair 2 |
|-------|--------|--------|
| C1 | Uzair + Saad | Faz + Hamza |
| C2 | Uzair + Faz | Saad + Hamza |
| C3 | Uzair + Hamza | Saad + Faz |

The system rotates **round-robin** C1 → C2 → C3 → C1 …, one combo per working day. This guarantees each developer pairs with each other developer exactly once every 3 working days ("no blind repeat"). See RULES.md for the exact algorithm and for behaviour when team size changes.

**What a developer pair does (defined):** the two developers perform each other's / the day's assigned **peer review** and each posts a review report back into the room (see Performance Signal).

### 8.2 Fixed QA Pairing Workflow

Habiba + Aqeel are always paired together and appear in every daily message as a fixed QA pair. Their pairing never rotates. It only changes if the Operator explicitly edits the team configuration.

### 8.3 Daily Team Lead Workflow

Each working day, one member from all 6 is assigned Team Lead via round-robin (independent order from the pairing cycle). The Team Lead is named in the daily message and is **responsible for ensuring the day's review work is completed**. Verification is fully **implicit** — the system infers completion from members' own reports; **no one manually confirms anything**. Additionally, the day's Team Lead is held **accountable for the team's outcome that day**: the team's completion/on-time/clean rates on a lead-day are recorded against that lead as a separate "as Team Lead" metric (see RULES.md R8.6–R8.8).

### 8.4 Daily 11:00 AM Element Workflow

At 11:00 AM PKT on each working day, the bot composes and sends a message to the configured room, e.g.:

```
Pairs Today

Uzair + Saad
Faz + Hamza
Habiba + Aqeel

Saad will make sure all above today
```

The bot stores: the round date, the two dev pairs, the QA pair, the Team Lead, the exact rendered message, and the returned Matrix **event ID**.

### 8.5 Performance Signal (the basis of all reporting)

> **Resolved by the Operator.** The configured room is a **dedicated report-only channel** — no general chatter happens there. Every working day, each member posts exactly one report: either the standard clean message or a message with suggestions/issues.

Because the room is report-only, the system treats **any message from a known member on a working day as that member's daily report**. From it, it derives three deterministic facts per member per working day:

1. **Completion** — did the member post a report that day? (yes/no)
2. **Timeliness** — did it arrive before the daily cutoff? (on-time/late)
3. **Outcome** — was it **clean** (the standard message *"Review completed. No issues, concerns, or improvement recommendations identified."*) or did it contain **suggestions/issues**?

These three facts are the objective, non-fabricated performance signal. A pair assignment alone is **never** treated as performance.

**Attribution (resolved):** since the room is report-only, no thread-reply or keyword rule is needed — the bot maps `sender → member` and records the report directly. (Thread-reply remains an optional stricter fallback only if room usage ever changes.)

> **OPEN DECISION — TIMELINESS CUTOFF (default applied):** a report counts as on-time if posted by **23:59 PKT the same working day**; later = **late**; missing by the next working day's 11:00 AM = **missed**.

### 8.6 Weekly Reporting Workflow

Once per week (default: Friday after the daily cutoff, covering Mon–Fri), the system:
1. Deterministically aggregates **each member's** completion rate, on-time rate, clean vs. issues counts, current streaks, **plus each member's "as Team Lead" team-outcome metrics** for the days they led.
2. Passes the pre-computed metrics + the raw report texts to the LLM for a short readable narrative (issue themes, notable improvements). Provider is configurable (Anthropic / OpenAI / Gemini / OpenRouter).
3. Renders a clean **per-member table** as an HTML document, captures it as a **PNG image**, and posts the **image** to the room, followed by the short narrative as text.
4. Stores the metrics, narrative, model, and image **before** posting.

### 8.7 Monthly Reporting Workflow

Once per calendar month (default: last working day), the same pipeline runs over the whole month, plus week-over-week trend context — per-member table rendered as an image and posted, deterministic metrics first, LLM narrative second, everything stored.

---

## 9. Functional Requirements

### MVP (must-have)

- **FR-1** Configure the 6 members (name, Matrix user ID, role) in the web app, including **adding and removing members via a modal** — developers and the QA pair (QA editable with confirmation).
- **FR-2** Deterministic daily developer pairing via the 3-combo round-robin.
- **FR-3** Fixed QA pair (Habiba + Aqeel) always present.
- **FR-4** Daily Team Lead via round-robin over all 6.
- **FR-5** Send daily message to the configured **encrypted** room at 11:00 AM PKT on working days.
- **FR-6** Persist rounds, pairs, Team Lead, rendered message, and Matrix event ID.
- **FR-7** Ingest **report-only** room messages, map sender → member, and store completion/timeliness/outcome per member per day, including per-lead-day accountability metrics.
- **FR-8** Web dashboard: bot status, next scheduled run, recent rounds, recent errors.
- **FR-9** Pairing history view.
- **FR-10** Manual controls: "Send today's message now", "Regenerate today's pairing", "Pause/resume bot".
- **FR-11** Logs & failed-jobs view.
- **FR-12** Single-admin authentication for the control panel.
- **FR-13** Secure storage of Element/LLM secrets (encrypted at rest).

### Post-MVP (should/could)

- **FR-14** Weekly report: per-member table **rendered as an image (PNG)** and posted to the room + LLM narrative text.
- **FR-15** Monthly report: same per-member image + narrative.
- **FR-16** Performance analytics screens (charts, per-member trends, "as Team Lead" view).
- **FR-17** Configurable schedule, cutoff, working days, holidays.
- **FR-18** Manual data correction (fix/mark a member's report) with audit trail.
- **FR-19** LLM provider config incl. **OpenRouter** — fetch models, filter free-only, select a specific model.
- **FR-20** Real @-mentions/pings of members in Element.
- **FR-21** Notifications to Operator on failures (email/Matrix DM).

---

## 10. Non-Functional Requirements

- **NFR-1 Reliability:** the daily 11:00 AM send must succeed with automatic retry; a missed send must be detectable and recoverable.
- **NFR-2 Idempotency:** no duplicate daily message for the same date, even if a job runs twice.
- **NFR-3 Determinism:** identical inputs → identical pairing/lead output; fully reproducible and auditable.
- **NFR-4 Security:** secrets encrypted at rest; control panel behind auth; least-privilege bot (one room).
- **NFR-5 Privacy:** minimise what is sent to the LLM; document exactly what leaves the system (see §12).
- **NFR-6 Observability:** structured logs, job status, and error surfaces in the UI.
- **NFR-7 Maintainability:** single modular codebase; deterministic core independent of LLM and Element.
- **NFR-8 Timezone-correctness:** all scheduling anchored to Asia/Karachi with DST-safe handling.
- **NFR-9 Recoverability:** persistent E2EE store; bot can restart without losing the ability to send/read.

---

## 11. Element / Matrix Interaction Requirements

- The room is **end-to-end encrypted (E2EE)** — confirmed by Operator.
- The bot uses a dedicated Matrix account and must be **joined to the room before** it can read messages (E2EE cannot decrypt history sent before it joined).
- The bot's encryption state (device keys, megolm sessions) must be **persisted** across restarts.
- The bot must both **send** the daily message and **read** members' replies — so E2EE reliability is on the **critical path** for the performance signal, not just for sending.
- The bot operates on **one room only** (`MATRIX_ROOM_ID`); it must not act on any other room.

---

## 12. LLM Responsibilities

**LLM is used for (and only for):**
- Reading pre-computed metrics + raw report texts to write the **weekly/monthly narrative**.
- Classifying/summarising **issue themes** found in review reports.
- Highlighting qualitative **trends and improvements** in plain language.

**LLM is never used for:**
- Pairing, Team Lead selection, scheduling, or any DB operation.
- Computing scores, rates, or counts (all numbers come from the deterministic layer).
- Deciding whether a report was completed/on-time/clean.

**Guardrail:** the LLM receives already-computed numbers and is instructed to narrate them, never to recalculate or invent. Report texts fed to the LLM are treated as untrusted (prompt-injection aware — see §15).

**Provider:** the LLM provider is configurable — Anthropic, OpenAI, Gemini, or **OpenRouter**. With OpenRouter, the app fetches the account's model list, lets the Operator filter **free-only** models and pick a specific model. Provider/model choice affects only narrative generation.

---

## 13. Admin / Control Panel Requirements

- Single-admin login.
- Team & role management; QA fixed-pair config; Team Lead order config.
- Element room configuration and connection status.
- Schedule/cutoff/working-days/holiday settings.
- Dashboard with bot health and next run.
- Pairing history, performance analytics, weekly/monthly reports.
- Logs and failed-jobs with retry.
- Manual controls (send now, regenerate, pause/resume, correct data).

Full UX in DESIGN.md.

---

## 14. Error & Failure Scenarios

| Scenario | Required behaviour |
|----------|--------------------|
| 11:00 AM send fails (network/Matrix down) | Retry with backoff; mark round `send_failed`; surface in UI; recoverable manual send |
| Job runs twice | Idempotency key per (date, job-type) prevents duplicate message |
| E2EE decryption failure (UTD) on a reply | Log the un-decryptable event; mark that member's report as `undetermined`, not "missed"; alert Operator |
| Bot not joined / kicked from room | Detect on startup and before send; block send; alert |
| LLM fails/times out (reports) | Fall back to a deterministic templated report; mark narrative as "LLM unavailable"; still post metrics |
| Member has no Matrix ID mapped | Skip attribution for them; flag in UI as config gap |
| Odd/changed team size | Re-derive pairing combos; handle per RULES.md |
| DB unavailable | Fail safe: do not send un-recordable messages; alert |

---

## 15. Security & Privacy Considerations

- **Secrets at rest:** Matrix token/password, LLM key, and E2EE store encrypted using `SECRETS_ENCRYPTION_KEY`.
- **Least privilege:** bot scoped to one room; control panel behind auth; no public endpoints beyond what's needed.
- **Data to LLM:** members' report texts + names + metrics leave the system when generating narratives. This is PII-adjacent. Requirements: (a) document it, (b) allow disabling LLM (fall back to templates), (c) OPEN DECISION on redaction below.
- **Prompt injection:** report texts are untrusted; the LLM prompt must instruct it to treat report content as data, ignore embedded instructions, and never recompute numbers.
- **No irreversible actions from room content:** nothing a room member types can change configuration or trigger admin actions.
- **Audit trail:** manual corrections and admin actions are logged.

> **OPEN DECISION — LLM DATA PRIVACY:** Do real names and full report texts get sent to a third-party LLM, or should names be pseudonymised (e.g., "Developer A") and report texts truncated/redacted before leaving the system? Also: is member consent required? Decide before enabling weekly/monthly LLM narratives.

---

## 16. Future Expansion Possibilities

- Multiple rooms / multiple teams (multi-tenant).
- Real @-mentions and interactive commands in the room.
- Larger, dynamic teams with generalised pairing (blossom/round-robin algorithm for N players).
- Slack/Teams adapters behind the same core.
- Configurable performance signals (reactions, structured forms, ticket integrations).
- Operator notifications and on-call alerting.
- Historical export / BI dashboards.

---

## 17. MVP Scope (explicit)

**In MVP:** FR-1 to FR-13 — team config, deterministic pairing (dev rotation + fixed QA + Team Lead), reliable 11:00 AM encrypted send, full persistence, **report ingestion + performance signal capture**, dashboard, history, manual controls, auth, secret storage.

**Explicitly deferred to Post-MVP:** weekly/monthly **report generation & LLM narratives** (FR-14/15), analytics charts, advanced settings, corrections UI, mentions, notifications.

**Rationale:** the daily loop + reliable, correctly-attributed data capture must be proven first. Reports are only trustworthy once the underlying signal is being captured reliably for a few weeks. Building reports before verifying signal quality would produce exactly the "fake performance report" the Operator wants to avoid.

---

## 18. Open Decisions Summary

- ✅ **RESOLVED — REPORT ATTRIBUTION** — room is report-only; any known member's message that day = their report — §8.5
- ✅ **RESOLVED — TEAM LEAD VERIFICATION** — implicit, no manual confirm; lead is accountable for the team that day — §8.3
- **OPEN — TIMELINESS CUTOFF** (default: 23:59 PKT same day) — §8.5
- **OPEN — LLM DATA PRIVACY** (real names/texts vs pseudonymised) — §15 — *decide before enabling LLM narratives*
- **OPEN — WORKING DAYS / HOLIDAYS** (default: Mon–Fri, no holiday calendar in MVP) — §10
- **OPEN — SCORE MODEL** — single composite "score" per member, or only raw rates? See RULES.md
