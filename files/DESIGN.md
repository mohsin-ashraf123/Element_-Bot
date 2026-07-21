# DESIGN.md — Control Panel UI / UX

**Project:** Element Team Pairing & Review Automation Bot
**Status:** Draft v1.0
**Focus:** operational usability and control, not decoration.

The control panel is the Operator's cockpit for an unattended automation. Design priorities: (1) **see health at a glance**, (2) **trust the data**, (3) **intervene quickly and safely**.

---

## 1. Design Principles

- **Operational clarity first.** The most important question — "is the bot healthy and did today's message go out?" — must be answerable in under 3 seconds on the dashboard.
- **Every number is traceable.** Any metric links back to the raw records/events that produced it (no black boxes).
- **Safe actions.** Irreversible or override actions (send now on an already-sent day, corrections) require confirmation and are logged.
- **Read-only by default, edit deliberately.** Config screens separate viewing from editing to avoid accidental changes to a live system.
- **Single-admin, desktop-first** layout; **fully responsive down to mobile** — on phones the sidebar becomes a slide-in drawer (hamburger), stat cards collapse to a compact 2-column grid, and wide tables scroll. Compactness matters: cards must not each eat a full screen on mobile.

---

## 2. Global Layout

- **Left sidebar navigation** (persistent) + **top bar** (bot status pill, environment badge, admin menu/logout).
- **Bot status pill** always visible: `Running` / `Paused` / `Degraded` / `Error`, with the time of the last successful send.
- Content area renders the selected section.

### Primary Navigation
1. Dashboard
2. Team & Roles
3. Pairing History
4. Performance (Analytics)
5. Reports (Weekly / Monthly)
6. Element Room
7. Schedule & Rules
8. Jobs & Logs
9. Settings

---

## 3. Dashboard

The at-a-glance operational home.

- **Status cards:** Bot state · Element connection (connected/joined/E2EE OK) · Last successful send · Next scheduled send (countdown).
- **Today's round panel:** today's dev pairs, QA pair, and Team Lead; send status (`Scheduled` / `Sent ✓ at 11:00` / `Failed`); the actual message text + link to the Element event.
- **Today's reports strip:** per-member chips — `Reported ✓ on-time` / `Late` / `Awaiting` / `Undetermined ⚠`.
- **Alerts area:** failed jobs, send failures, decryption issues, config gaps (e.g., member missing Matrix ID).
- **Quick actions:** Send today's message now · Pause/Resume · Go to failed jobs.

DoD for this screen: an Operator glancing once knows if anything needs attention.

---

## 4. Bot Status (detail)

Expanded health view: connection details, E2EE store status, last sync time, Beat/worker heartbeats, recent send history (last 7 days with ✓/✗), and a manual **health-check** button.

---

## 5. Team & Roles

- **Member list:** name, Matrix user ID, role (Developer/QA), active toggle, config-gap warnings.
- **Add member (modal):** name + Element username (`@user:server`) + role. Opens from an "Add member" button; deliberate, focused modal.
- **Remove member:** a remove control on each row, with a confirmation noting that history is kept and the member is excluded from future rounds only.
- **QA fixed-pair config:** shows Habiba + Aqeel locked together. The QA pair is **also editable** (add/remove QA) for future changes, but behind a confirmation since it's intentionally friction-ful.
- **Team Lead order:** drag-to-reorder the round-robin list; preview "next N leads."

---

## 6. Element Room Configuration

- Homeserver URL, bot account, room ID (secrets shown masked, never in plain text).
- **Connection status:** joined? E2EE working? last message sent?
- **Test message** button (posts a clearly-marked test to the room, logged).
- Read-only reminder: "the bot must be a room member; it can only read messages sent after it joined. This room is **report-only** — every member message is treated as that member's daily report."

---

## 7. Pairing History

- **Calendar / table** of past rounds: date · Combo (C1/C2/C3) · dev pairs · QA pair · Team Lead · send status · Element event link.
- Filters by date range and member.
- Row expands to show the exact message text and ingestion outcome for that day.
- Proves fairness visually (e.g., "each pairing appears equally").

---

## 8. Performance (Analytics)

*(Populated once ingestion runs; charts arrive in Phase 4.)*

- **Per-member view:** completion rate, on-time rate, clean rate, current streak — as numbers **and** a small trend line. Each metric links to the underlying days.
- **Pair-level view:** for each pairing, "both on-time" rate and issue counts, where useful.
- **Team overview:** aggregate rates over selectable periods.
- **Undetermined/missed breakdown:** so faults are visible separately from genuine misses.

Design rule: never show a metric without a way to drill into the days that produced it.

---

## 9. Reports (Weekly / Monthly)

- **List** of generated reports (period, generated-at, posted status, LLM vs template).
- **Report detail:** the **per-member table** (every member on their own row: completion, on-time, clean, streak, plus their "as Team Lead" metrics) is shown exactly as it is **rendered into an image and posted to the room**. Below it, the short narrative clearly labelled "AI-generated summary," with a banner if the **template fallback** was used.
- A note makes clear the table is **posted to the room as a PNG image** (renders identically everywhere), followed by the narrative text.
- Actions: **Re-generate**, **Re-post to room** (confirmation + logged).
- Every figure in the narrative should also exist in the table (traceability).

---

## 10. Schedule & Rules

- Daily send time (default 11:00), timezone (Asia/Karachi), working days (Mon–Fri toggles).
- Timeliness cutoff (default 23:59 same day).
- Report attribution mode (thread-reply default / strict-format option).
- Weekly/monthly trigger settings.
- Each rule shows its current value and whether it's a resolved decision or still a default (surfacing the OPEN DECISIONs from RULES.md).

---

## 11. Jobs & Logs

- **Jobs table:** type (daily-send, ingest, weekly-report, …), scheduled time, status, attempts, error, actions (**Re-run**, view detail).
- **Failed jobs** filter front-and-centre.
- **Logs stream:** filterable structured logs (level, component, date).
- **Audit log:** manual actions and data corrections (who/when/old→new/reason).

---

## 12. Manual Controls (grouped, guarded)

Accessible contextually and from a dedicated panel:
- Send today's message now (confirm if already sent → recorded as override).
- Regenerate today's pairing (allowed **only** before send).
- Pause / Resume bot.
- Correct a member's daily record (confirm + reason → audit).
- Re-run failed job.
- Re-generate / re-post a report.

All guarded actions show a confirmation modal stating exactly what will happen and note that the action is logged.

---

## 13. Settings

- Admin account (change password).
- **LLM provider selection** — Anthropic / OpenAI / Gemini / **OpenRouter**. For OpenRouter: paste key → **fetch models** → **free-only filter** → **select a specific model**. Keys are entered here directly, stored encrypted, and shown masked.
- Enable/disable AI narratives (off = deterministic templates).
- Pseudonymise names to LLM toggle (privacy — OPEN DECISION).
- Secret rotation guidance (never displays raw secrets).
- Appearance (light/dark).
- Backup status (Phase 5).

---

## 14. Empty / Error / Degraded States (don't skip these)

- **Empty:** before any rounds exist, screens explain what will appear and link to setup steps.
- **Degraded:** if Element is disconnected or E2EE is failing, the dashboard shows a prominent banner and disables send actions with an explanation.
- **Undetermined data:** always visually distinct from "missed" so the Operator never misreads a system fault as a member's failure.

---

## 15. Interaction Flow Examples

- **Morning check:** open Dashboard → status green, "Sent ✓ 11:00", reports strip filling in → done.
- **Something failed:** red alert on Dashboard → Jobs & Logs → inspect error → Re-run or manual send → confirm.
- **Weekly review:** Reports → open latest → verify metrics table → read AI summary → Re-post if needed.

The whole design optimises for a quick daily glance plus fast, safe intervention when the automation needs a human.
