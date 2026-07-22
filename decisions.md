# Decisions log

Non-obvious implementation decisions, newest first (CLAUDE.md process rule). Each: what + one-line rationale. Stage-0 decisions are proposals pending Zach's approval where marked.

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
