# RULES.md — Business & System Rules

**Project:** Element Team Pairing & Review Automation Bot
**Status:** Draft v1.0

Every rule below is meant to be explicit and unambiguous. Where the product still needs a human decision, it is marked **OPEN DECISION** with the default the system will use until overridden.

---

## 1. Roster & Roles

- **R1.1** The team has a configurable roster. Initial roster: 4 developers (Uzair, Saad, Faz, Hamza) + 2 QA (Habiba, Aqeel) = 6 members.
- **R1.2** Each member has: `name`, `matrix_user_id`, `role ∈ {DEVELOPER, QA}`, `active` flag.
- **R1.3** A member without a valid `matrix_user_id` cannot be attributed a report; the UI flags this as a config gap.
- **R1.4** Only an admin action changes the roster or roles.

---

## 2. Developer Pair Generation

- **R2.1** Exactly the **active developers** are paired each working day.
- **R2.2** With 4 developers there are 3 valid pair-splits (combos):
  - C1: (Uzair+Saad, Faz+Hamza)
  - C2: (Uzair+Faz, Saad+Hamza)
  - C3: (Uzair+Hamza, Saad+Faz)
- **R2.3** **Rotation** is round-robin C1 → C2 → C3 → C1 …, advancing one combo per working day. State is derived from stored history (last used combo), not from wall-clock, so it stays correct across restarts and skipped days.
- **R2.4** This guarantees each developer pairs with every other developer exactly once per 3 working days ("fair distribution, no blind repeat").

## 3. Randomization

- **R3.1** The rotation is **deterministic** (round-robin), not random — this maximises fairness and reproducibility, which the Operator asked for.
- **R3.2** Randomness is used only to pick the **starting combo** at first-ever initialisation (seeded and recorded), so the sequence is auditable afterwards.
- **R3.3** No number generation ever uses the LLM.

## 4. Avoiding Repeated Pairs

- **R4.1** Because only 3 combos exist for 4 devs, a repeat is unavoidable every 3 days; the rule is that the **same combo never appears on two consecutive working days**, and each combo is used equally often over any 3-day window.
- **R4.2** For future larger teams: track a pair-history matrix and prefer the least-recently-used valid combo. (Post-MVP; see Future.)

## 5. Handling Odd / Changed Developer Counts

> **OPEN DECISION — ODD DEV COUNT (default applied).** The current design assumes 4 developers. If the active developer count changes:
- **R5.1 (default)** If **even** count: regenerate the set of valid combos and resume least-recently-used round-robin.
- **R5.2 (default)** If **odd** count: form pairs from N−1 developers and assign the remaining developer a **solo "self-review" slot** for that day (counts for completion via their own report). *Alternative options the Operator may choose instead:* rotate who sits out; or form one group of three. **Default = solo self-review slot.**
- **R5.3** QA pair is excluded from this logic (always fixed, see §7).

## 6. New / Removed / Inactive Users

- **R6.1 New member:** added via admin; becomes eligible for pairing/lead starting the **next** working day (never retroactively inserted into a past round).
- **R6.2 Removed member:** marked inactive; excluded from future rounds; past records retained for history/reports.
- **R6.3 Inactive member:** excluded from pairing and Team Lead rotation while inactive; not counted as "missed" in performance for days they were inactive.
- **R6.4** Roster changes take effect at the next round boundary, never mid-round.

## 7. Fixed QA Pair

- **R7.1** Habiba + Aqeel are always paired together, every working day, in every daily message.
- **R7.2** Their pairing never rotates or randomises.
- **R7.3** It changes only if an admin explicitly edits the QA configuration.
- **R7.4** If one QA member is inactive, the QA line shows the remaining active member solo, and the pair auto-restores when both are active again.

## 8. Team Lead Selection & Rotation

- **R8.1** The Team Lead is chosen daily from **all 6 members** via round-robin (decided by Operator).
- **R8.2** The lead order is a configurable ordered list (default: roster order). Advance one position each working day; wrap around at the end.
- **R8.3** The lead cycle (period 6) is **independent** of the pairing cycle (period 3); this naturally varies lead–pair combinations.
- **R8.4** An inactive member is skipped in the lead rotation without consuming their turn.
- **R8.5** The Team Lead's responsibility is to ensure the day's review work is completed.

**RESOLVED — LEAD VERIFICATION:** Verification is **implicit** — the system infers completion purely from members' own reports. **No one manually confirms anything**; there is no "confirm" button. (This closes former OD-3.)

- **R8.6 Team Lead accountability.** On the day a member is Team Lead, that day's **team outcome is also attributed to the lead** as their leadership responsibility. Concretely, per lead-day the system records the team's completion rate, on-time rate, and clean rate for that day against the lead. If the team's reports are missing, late, or poor on a given day, the responsibility sits with that day's lead — the system reflects this automatically (no human judgement needed).
- **R8.7** Reports therefore show, for each member, both their **individual** metrics and their **as-Team-Lead** metrics (how their team performed on the days they led). This is a separate, clearly-labelled dimension — not mixed into individual completion.
- **R8.8** Lead-day accountability uses the same signal (members' reports); it never fabricates a judgement and never requires a manual confirmation step.

## 9. Daily Schedule & Timezone

- **R9.1** Daily message sends at **11:00 AM Asia/Karachi** on working days.
- **R9.2** Timezone anchored to `Asia/Karachi`; scheduling must be DST-safe (Pakistan currently observes no DST, but the code must not assume UTC offset).
- **R9.3 Working days (default):** Monday–Friday. Weekends: no send.

> **OPEN DECISION — HOLIDAYS (default applied).** No holiday calendar in MVP; public holidays are treated as normal working days unless the Operator pauses the bot or adds a holiday list (Post-MVP).

## 10. Daily Message Content Rules

- **R10.1** Message must contain: the two developer pairs, the QA pair, and the Team Lead responsibility line.
- **R10.2** Format follows the Operator's example ("Pairs Today … / X will make sure all above today").
- **R10.3** Names are plain text in MVP (real @-mentions are Post-MVP).
- **R10.4** The exact rendered text and returned Matrix event ID are stored with the round.

## 11. Duplicate-Message Prevention (Idempotency)

- **R11.1** At most **one** daily message per (room, date). Enforced by idempotency key `daily_send:{date}`.
- **R11.2** If a send job runs again for an already-sent date, it is a no-op that logs "already sent."
- **R11.3** A manual "send now" for an already-sent date requires explicit Operator confirmation and is recorded as a manual override.

## 12. Failed Element Messages

- **R12.1** Transient send failures retry with exponential backoff (e.g., 3 attempts).
- **R12.2** After final failure, the round is marked `send_failed`, surfaced in the UI, and the Operator is alerted (Post-MVP alerting).
- **R12.3** A `send_failed` round can be re-sent manually or by the next health-check catch-up.
- **R12.4** The system never marks the day "complete" if the message was never delivered.

## 13. Failed Scheduled Jobs

- **R13.1** Every job records status, attempt count, and error.
- **R13.2** Failed jobs appear in the failed-jobs UI and can be re-run manually.
- **R13.3** Only **one** Celery Beat instance runs (prevents double scheduling).
- **R13.4** A missed scheduled run is detectable via "last successful send" health check.

## 14. Report Ingestion / Performance Signal

- **R14.0 Dedicated report-only room.** The configured room is used **only** for this workflow: the bot's daily message and members' daily reports. Members do not hold general chatter there. Each member posts **one report per working day** — either the standard clean message or a message containing suggestions/issues. This is a stated product requirement, not just a convention.
- **R14.1** The performance signal comes from **members' report messages in the room**, not from the pairing itself.
- **R14.2** Per member per working day, the system derives:
  - `completed` — a report from that member was seen that day,
  - `on_time` — posted before the cutoff,
  - `clean` — matched the standard "no issues" message; else `has_issues` (a suggestion/issue) with the raw text stored.
- **R14.3** The standard clean message is: *"Review completed. No issues, concerns, or improvement recommendations identified."* Matching is case-/whitespace-normalised.

**RESOLVED — REPORT ATTRIBUTION (simplified).** Because the room is report-only, **any message from a known member's Matrix ID on a working day is that member's daily report** — no thread-reply or keyword requirement is needed. The bot maps `sender MXID → member` and records the report. (Thread-reply is retained only as an optional stricter fallback if the room's usage ever changes.)

> **OPEN DECISION — TIMELINESS CUTOFF (default applied).** On-time = posted by **23:59 PKT the same working day**. Missing by the next working day 11:00 AM = **missed**.

- **R14.4** Multiple reports from the same member in one day: the **last on-time** message before cutoff is authoritative; extras are retained but not re-counted.

## 15. Performance Scoring

- **R15.1** Scoring is deterministic. Base metrics per member over a period:
  - completion rate = completed days / eligible days,
  - on-time rate = on-time / completed,
  - clean rate = clean / completed,
  - current streak (consecutive on-time completions).
- **R15.2** "Eligible days" excludes days the member was inactive/new.
- **R15.3** The LLM never computes or alters these numbers.

> **OPEN DECISION — COMPOSITE SCORE.** Should the product surface a single composite "score" per member, or only the raw rates above? **Default: raw rates only** (safer, avoids a misleading single number). A weighted composite can be added later if the Operator defines the weights.

## 16. Pair-Level Performance

- **R16.1** Pair-level metrics are derived by joining both members' daily records for days they were paired (e.g., "both completed on time" rate for that pair).
- **R16.2** Pair metrics are shown where useful; individual metrics remain primary.

## 17. Missing / Undetermined Data

- **R17.1** No report attributed → `missed` for that eligible day.
- **R17.2** A reply that **cannot be decrypted** (E2EE UTD) or cannot be attributed is marked **`undetermined`**, *not* `missed`, and flagged for Operator review. This prevents penalising members for a system fault.
- **R17.3** Reports never fabricate values for missing data; gaps are shown as gaps.

## 18. LLM Failure Rules

- **R18.1** If the LLM fails/times out during report generation, the system uses a **deterministic template narrative** built from the computed metrics and marks the report "narrative: LLM unavailable."
- **R18.2** Numbers are always shown regardless of LLM status.
- **R18.3** Report texts sent to the LLM are treated as untrusted; the prompt instructs the model to ignore embedded instructions and never recompute figures.

## 19. Report Generation & Posting

- **R19.1** Weekly report: default trigger Friday after cutoff, covering that Mon–Fri.
- **R19.2** Monthly report: default trigger last working day of the month, covering the calendar month.
- **R19.3** Reports are stored (metrics + narrative + image + model + timestamp) **before** being posted, so a posting failure never loses the report.
- **R19.4** Posting uses the same idempotency + retry rules as daily messages.
- **R19.5 Report content is per-member.** Each report shows **every member on their own row** (completion, on-time, clean, streak) — not a single team blurb. It also shows each member's **"as Team Lead"** metrics (team outcome on the days they led, per R8.6).
- **R19.6 Report is posted as an image.** The bot renders the per-member table as a clean HTML document, captures it as a **PNG** (headless browser), and posts the **image** to the room, followed by the short AI/template narrative as text. Rationale: images render identically everywhere and avoid Matrix/Element markdown-table limitations.
- **R19.7** If image rendering fails, the bot falls back to posting a plain-text table + narrative, and flags the render failure in the UI.

## 19a. LLM Provider Rules

- **R19a.1** The LLM provider is configurable: Anthropic, OpenAI, Gemini, or **OpenRouter**.
- **R19a.2** For OpenRouter, after the key is saved the system **fetches the available model list**, lets the Operator **filter free-only models** and **select a specific model** to use for narratives.
- **R19a.3** All provider keys are encrypted at rest and never displayed in plaintext.
- **R19a.4** The selected provider/model applies only to narrative generation; it never touches deterministic logic.

## 20. Data Correction

- **R20.1** The Operator may correct a member's daily record (e.g., mark a genuinely completed report the parser missed).
- **R20.2** Every correction is written to an **audit log** (who, when, old→new, reason).
- **R20.3** Corrections update derived metrics on next aggregation; historical reports already posted are not rewritten (a corrected re-issue can be posted manually).

## 21. Manual Admin Actions

- **R21.1** Allowed manual actions: send today's message now, regenerate today's pairing (before send), pause/resume bot, re-run a failed job, correct data, re-send a failed/late report.
- **R21.2** Regenerating a pairing after the message was already sent is **not** allowed (would create inconsistency); only a documented override with a new message is possible.
- **R21.3** Nothing typed by a room member can trigger an admin action or change configuration.
- **R21.4** All manual actions are logged.

---

## 22. Consolidated Open Decisions

| ID | Decision | Status / Default |
|----|----------|-----------------------|
| OD-1 | Report attribution method | ✅ **RESOLVED** — reply (thread) to the daily 11 AM message |
| OD-2 | Timeliness cutoff | 23:59 PKT same working day (default) |
| OD-3 | Team Lead verification | ✅ **RESOLVED** — implicit; no manual confirm; lead is accountable for the team that day (R8.6–R8.8) |
| OD-4 | Odd developer count | Solo self-review slot (default) |
| OD-5 | Holidays | Treated as working days, manual pause (default) |
| OD-6 | Composite score | Raw rates only, no single score (default) |
| OD-7 | LLM data privacy (real names/texts) | Open — must decide before LLM narratives (PRD §15) |
