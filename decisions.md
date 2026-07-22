# Decisions log

Non-obvious implementation decisions, newest first (CLAUDE.md process rule). Each: what + one-line rationale. Stage-0 decisions are proposals pending Zach's approval where marked.

## Stage 0 (2026-07-22)

- **D-01 — Expansion modeled as a Program in `expansion` phase, not an Expansion-opportunity object.** The Expansion-opportunity object is v1; representing the AGCO-style 1k→3k expansion as a program keeps the seed within v0's object set. *Pending confirm (gap G1).*
- **D-02 — `Person.affiliation` (client | valence) instead of a separate user/internal object.** Lets a commitment's internal owner be a real Person without a new type. *Pending confirm (PA-2).*
- **D-03 — Status enums `{on_track, at_risk, off_track, unknown}`.** Doc mandates two manual statuses but never enumerates values; chose the minimal set mapping to Section 6 semantic colors, `unknown` as honest default. *Pending confirm (PA-1, gap G6).*
- **D-04 — Blockers are Risks/Issues flagged `is_blocker`, not a "blocker" object.** Module A ranks "active blockers" but names no such object; a flag avoids a new type. *Pending confirm (PA-3).*
- **D-05 — `Milestone.at_risk` = manual flag OR derived from overdue target.** Queue needs an at-risk signal; smallest thing that works. *Pending confirm (PA-4).*
- **D-06 — Attention queue items are derived each render; only snooze/resolve is persisted (AttentionState overlay).** Keeps the queue rules-based/explainable and avoids stale stored items; the overlay is queue mechanics, not a domain object. *Confirm this isn't considered a "new object type."*
- **D-07 — AuditEvent + soft-delete present from the first migration.** CLAUDE.md standing rule; not deferred even though v0 has a single actor.
- **D-08 — Job table deferred until first long-running task.** v0's team-update export is synchronous over a few thousand rows; no worker needed yet (Section 8 "when jobs become needed").
- **D-09 — `Interaction.program_id` required for now; account-level interactions unresolved.** Flagged as gap G2; awaiting decision on allowing null program_id with account_id.
- **D-10 — Stale-stakeholder threshold = 21 days for senior roles.** Matches the morning-check scenario ("untouched for three weeks"); configurable, not a hard-coded benchmark in UI copy.
