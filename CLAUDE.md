# CLAUDE.md — Valence OS standing rules

These rules apply to every session on this repository. They restate the binding constraints from `Valence-OS-Scoping-Doc.md` and win over any conflicting instruction in an individual prompt except an explicit, deliberate override from Zach.

## Scope

**Current authority: `PHASE-3-SPEC.md`** (Zach, July 2026), a deliberate override of the frozen-scope regime below. Read it first. It retires the Phase 2 evidence gates and directs a feature-complete build in the order of its Section 10. The trust boundaries, the design rules, tests-green, decisions-logged, and **mock-only data** are all explicitly *unchanged and still binding*. What changes is only the scope/slice discipline: object types, fields, screens, and background infrastructure named in the Phase 3 spec are in-scope to build now. New objects/fields **outside** what that spec calls for still require asking first.

- The one remaining gate is **data governance, not scope**: build everything, connect nothing real. Every external touchpoint (email, recordings, calendar, transcription, LLM endpoint, notification channel, file storage, hosting) is an adapter with a mock implementation. Flipping any adapter to a real source requires the hosting/data-handling conversation at Valence to have happened and is recorded in `decisions.md`. `CONNECTIONS.md` is the registry.
- Follow the Phase 3 build order (spec §10); each stage lands with tests, both-theme screenshots, and a HANDOFF.md update before the next begins.

_Superseded by the above, retained for history:_ ~~The scope is frozen; new object types or fields outside `stage-0/field-dictionary.md` require asking first. Build order is Stage 0 → v0.1 → … → v0.4, then stop. Declined items in Section 11 of the scoping doc stay declined.~~ The Section 11 declines and the field dictionary remain the reference for anything the Phase 3 spec does *not* address.

## Trust boundaries (schema-level, non-negotiable)

- No table, column, or field may exist anywhere for a named individual's usage of the Nadia product. Champion engagement means deployment engagement (meetings, comms, advocacy), never product usage. Cohort usage data is aggregate only.
- Visibility works by inherited safe defaults: raw notes, stakeholder judgments, commercial strategy, and AI-generated interpretations default to internal-only. Generated client-facing outputs include only affirmatively promoted records, enforced in the generator code, not by convention.
- Stakeholder assessments (stance, influence, relationship strength) always carry a date and an evidence note.

## Data rules

- Mock/synthetic data only. No real client names, people, transcripts, or figures anywhere in this repo, including tests, seeds, comments, and commit messages.
- Canonical external data (CRM, Data team metrics) is read-only locally; operational interpretations go in labeled overlay fields with rationale, author, and date. Never recompute metrics; ingest them.
- No hard-coded benchmarks (no "75% weekly return" or similar in code or UI copy). Benchmarks are data: versioned, sourced, with population and period.
- Last-touch dates are derived from interactions, never hand-edited.
- Stale metric-derived indicators render as unknown, never as carried-forward good state.

## Engineering defaults

- SQLite with versioned migrations from the first table. Every schema change is a migration; no manual DB surgery.
- Soft-delete and archival for operational objects; append-only audit log for material changes (actor, timestamp, before/after, source).
- Long-running work goes through the job table; routine edits and navigation must feel instant.
- Timestamps in UTC; contractual dates (renewal, notice) stored as dates, not timestamps.
- Keep it boring: no caching layers, no external queues, no microservices, no speculative abstractions. The dataset is a few thousand rows.

## Design

- `DESIGN-GUIDE.md` is the standing design authority. It supersedes §6 of the
  scoping doc and the navigation inherited from the §5 module list. Read it
  before any frontend change.
- No raw hex values, no arbitrary pixel values. Everything comes from
  `tokens.css`. Both light and dark are first-class; a change that only works
  in one theme is not done.
- Color carries meaning only. Green, amber, and red are reserved for status.
  The accent is for interaction, never for state. The budget waterfall is the
  single documented exception and never shares a screen with status indicators.
- No state is conveyed by color alone. Every status pairs a color with a shape
  or a label.
- Every dated record shows the freshness language: age chip, decay ramp, and
  the cross-hatched unknown treatment for anything past its threshold. Stale
  data never renders as carried-forward good state.
- Navigation is Today, Accounts, Library, Operations. Account-scoped work lives
  in the account workspace tabs. Do not add a new top-level destination without
  asking.
- Capture is global and keyboard-first, never a place you navigate to.
- Quality floor is non-negotiable: 4.5:1 contrast audited in both themes,
  visible keyboard focus, semantic tables, `prefers-reduced-motion` and
  `color-scheme` honored, no flash of incorrect theme.
- After any structural UI change, re-verify the §2 trust boundaries still hold:
  no individual product usage anywhere, client-facing outputs include only
  promoted records, stakeholder assessments keep date and evidence.
- Schema changes are proposals, not blockers. Batch them with a one-line
  rationale and present them at the end of the phase.

## Process

- Log non-obvious implementation decisions in `decisions.md` with a one-line rationale.
- When the scoping doc is silent, build the smallest thing that passes the acceptance test. When it contradicts itself, stop and ask.
- The 30-second capture rule wins every tie: if a design choice makes post-call capture slower, choose the other design.
