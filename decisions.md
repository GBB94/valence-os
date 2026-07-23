# Decisions log

Non-obvious implementation decisions, newest first (CLAUDE.md process rule). Each: what + one-line rationale. Stage-0 decisions are proposals pending Zach's approval where marked.

## v0.3 (2026-07-23)

- **Repo relocated to `~/Desktop/Claude Projects/account-os`.** `~/Documents` became TCC-blocked for this process mid-session (no file reads/writes/renames). Desktop is readable; moved here. Toolchain (git history, .venv, seed DB) survived the move intact.
- **D-18 — Status enum `{on_track, at_risk, off_track, unknown}` confirmed (PA-1/G6).** Zach approved the default 2026-07-22. Two independent columns per dimension (value, rationale, assessed_on, change_condition); no composite. Setting a status stamps today as `assessed_on`; UI warns when an assessment is >30 days old (warning only — a manual status is never auto-set to unknown; only metric-derived indicators do that, and there are none in v0).
- **D-19 — Queue items derived every render; only snooze/resolve persists (attention_state overlay).** Builder computes candidates from the 6 v0.3-available triggers, applies the latest overlay per `item_key`, sorts by (priority, age desc). Renewal/import/play triggers absent by construction until their phases.
- **D-20 — Resurfacing is deterministic.** A snoozed item returns when `snooze_until <= today` OR the underlying object's `updated_at` is later than the overlay's `created_at` ("facts materially changed"). Resolved items return only on underlying change. Free-text `resurface_condition` is stored/shown but not auto-evaluated (no rules engine in v0).
- **D-21 — Snooze needs a date or condition; resolve needs a successor action.** Enforced by a table CHECK and in the API. The resolve UI creates a follow-up task in the item's program and links it, so risk is never merely hidden.
- **D-22 — Stale-stakeholder baseline.** Senior roles (champion/budget_owner/program_owner) with no meaningful touch in >21 days. Last touch derived from interaction participation; if never touched, the role's creation date is the baseline.

## v0.2 (2026-07-22)

- **D-14 — Closure rules enforced at DB and API layers.** Risk close requires `close_reason` and issue resolve requires `resolution_type` via CHECK constraints (`status='open' OR reason/type NOT NULL`) plus the transition endpoints; mitigation is a separate field that never changes status. Commitments close only through `/close` (records `acknowledged_by`, date, closer, note). Double-close returns 409, not a crash.
- **D-15 — Inbox conversion reuses the exact create path (`execution_ops.create`).** No divergent creation logic; conversion pre-fills `description` from `raw_text`, auto-links `source_interaction_id`, and defaults `program_id` to the source interaction's program. Account-level notes (null program) require choosing a program in the convert form (422 with guidance otherwise).
- **D-16 — Decision supersede is modeled, not deleted.** Creating a decision with `supersedes_id` flips the old one to `superseded` in the same transaction; both are retained (decisions are a log).
- **D-17 — Overdue / at-risk are derived at read time on the board, never stored.** Commitment/task `overdue` = open AND due_date < today; milestone `derived_at_risk` = upcoming AND (at_risk flag OR past target). Keeps status honest without stale stored flags.

## v0.1 (2026-07-22)

- **D-11 — Actor id columns (`audit_events.actor_id`, `capture_inbox_items.resolved_by`, `*.archived_by`) are plain TEXT, not FK→persons.** The acting operator is an app-level identity, not necessarily a domain Person row; FK-coupling every write to seeded people breaks fresh installs and tests. The field dictionary still models these as Person conceptually. Revisit when production identity (SSO) lands.
- **D-12 — Raw `sqlite3` + numbered `.sql` migrations, no ORM.** "Keep it boring." A `schema_migrations` table tracks applied versions; the runner applies any file whose version isn't recorded, one transaction each.
- **D-13 — Frontend served from `frontend/dist` by FastAPI in one process.** Vite dev server (5173) in development; built assets mounted at `/` otherwise. No separate web server (Section 8 single-process).

## Stage 0 (2026-07-22)

- **D-01 — Expansion modeled as a Program in `expansion` phase, not an Expansion-opportunity object.** The Expansion-opportunity object is v1; representing the AGCO-style 1k→3k expansion as a program keeps the seed within v0's object set. *Stands (only v0-legal option); G1 not separately objected to on 2026-07-22.*
- **D-02 — `Person.affiliation` (client | valence) instead of a separate user/internal object.** Lets a commitment's internal owner be a real Person without a new type. **Approved 2026-07-22 (PA-2).**
- **D-03 — Status enums `{on_track, at_risk, off_track, unknown}`.** Doc mandates two manual statuses but never enumerates values; chose the minimal set mapping to Section 6 semantic colors, `unknown` as honest default. *Proceeding on this default; re-confirm before v0.3 ships statuses (PA-1, gap G6).*
- **D-04 — Blockers are Risks/Issues flagged `is_blocker`, not a "blocker" object.** Module A ranks "active blockers" but names no such object; a flag avoids a new type. **Approved 2026-07-22 (PA-3).**
- **D-05 — `Milestone.at_risk` = manual flag OR derived from overdue target.** Queue needs an at-risk signal; smallest thing that works. **Approved 2026-07-22 (PA-4).**
- **D-06 — Attention queue items are derived each render; only snooze/resolve is persisted (AttentionState overlay).** Keeps the queue rules-based/explainable and avoids stale stored items; the overlay is queue mechanics, not a domain object. **Confirmed 2026-07-22: infrastructure, not a domain object; does not violate frozen scope.**
- **D-07 — AuditEvent + soft-delete present from the first migration.** CLAUDE.md standing rule; not deferred even though v0 has a single actor.
- **D-08 — Job table deferred until first long-running task.** v0's team-update export is synchronous over a few thousand rows; no worker needed yet (Section 8 "when jobs become needed").
- **D-09 — `Interaction.program_id` nullable, `account_id` required.** **Resolved 2026-07-22 (G2):** exec-level touches spanning programs are valid; every interaction still belongs to an account.
- **D-10 — Stale-stakeholder threshold = 21 days for senior roles.** Matches the morning-check scenario ("untouched for three weeks"); configurable, not a hard-coded benchmark in UI copy.
