# CLAUDE.md — Valence OS standing rules

These rules apply to every session on this repository. They restate the binding constraints from `Valence-OS-Scoping-Doc.md` and win over any conflicting instruction in an individual prompt except an explicit, deliberate override from Zach.

## Scope

**Current authority chain:** `PHASE-3-SPEC.md`, `EXPANSION-ENGINE-SPEC.md`, and the additive `INTERNAL-OPS-SPEC.md` define the completed build through Stage 10. `ADOPTION-CAMPAIGN-SPEC.md`, `ACCOUNT-COPILOT-SPEC.md`, `ADOPTION-COMMS-SPEC.md`, and `COMPANY-INTEL-SPEC.md` are the additive **Stage 11**, **Stage 12**, **Stage 13**, and **Stage 14** authorities (D-99/D-105/D-108/D-110). Read all seven before changing scope. The trust boundaries, design rules, tests-green discipline, decisions log, and **mock-only data** remain binding. Objects and fields outside those specs still require asking first.

- The one remaining gate is **data governance, not scope**: build everything, connect nothing real. Every external touchpoint (email, recordings, calendar, transcription, LLM endpoint, notification channel, file storage, hosting) is an adapter with a mock implementation. Flipping any adapter to a real source requires the hosting/data-handling conversation at Valence to have happened and is recorded in `decisions.md`. `CONNECTIONS.md` is the registry.
- Phase 3 through Stage 10 is complete. New numbered scope requires an explicit authority update; each stage lands with tests, both-theme screenshots, a decision entry, and a HANDOFF update before the next begins.
- **`EXPANSION-ENGINE-SPEC.md` is the completed expansion authority** (Zach, 2026-07-31, D-81/D-83). It interleaved Stage 5.5, Stage 7 signals, Stage 7.5, and Stage 9 with Phase 3; those slices are now built. Where it and the Phase 3 spec overlap, the expansion spec remains the authority for the data model.
- **`INTERNAL-OPS-SPEC.md` is additive and in force for Stage 10** (D-95). It generalizes existing records and adds internal forecasting, asks/escalation, reviews/reporting, coverage, feedback, and portfolio analytics without weakening the single-editor or no-auto-send rules. Its integrity foundations in Stage 10.0 land before later slices.
- **`ADOPTION-CAMPAIGN-SPEC.md` is additive and in force for Stage 11** (Zach, 2026-08-01, D-99). A campaign is a time-boxed, measurable intervention against one stable cohort inside an existing program. It adds one concept and *links* to eleven existing ones — it does not clone tasks, comms, moments, champions, MAP, or the playbook. Its §5 measurement contract is binding and non-obvious: a baseline locks a **series** not a point, comparators must be **disjoint** from the treated cohort, a rolled-back baseline **invalidates** the comparison, and signal-triggered pre/post evaluations carry the regression-to-the-mean caution. The app never writes that a campaign *caused* a change.
- **`ACCOUNT-COPILOT-SPEC.md` is additive and in force for Stage 12** (D-105). A grounded, read-only analyst built as predefined workflows — not an agent. Its non-obvious rules: access control is applied **before** the model, never asked of it; retrieved prose is untrusted data that cannot reach the planner or define a tool; every material claim cites a retrieved record snapshot that actually entails it, and an uncited factual claim fails validation rather than shipping; evidence coverage (`supported`/`partial`/`conflicted`/`insufficient`) replaces model confidence, and a numeric confidence badge is prohibited. **The LLM boundary does not inherit the extraction approval** — copilot payloads are a distinct `CONNECTIONS.md` class with their own runtime switch, and no stage flips it.
- **`ADOPTION-COMMS-SPEC.md` is additive and in force for Stage 13** (D-108). Communication sequences are plans over the existing `comms_entries`, never a sender or scheduler. Sequence state and expected dates are derived; a sent wave is an immutable operator-recorded fact. Session attendance is deployment engagement, calculated only for an explicitly linked cohort invitation wave and explicit audience attendees, with unknown classifications and privacy-floor cases withheld rather than guessed. No individual product usage or open/click tracking is introduced.
- **`COMPANY-INTEL-SPEC.md` is additive and in force for Stage 14** (Zach, 2026-08-02, D-110). Public company artifacts are immutable, span-cited, proposal-first mock records linked through a canonical company entity separate from the account. Only confirmed events with live evidence can annotate whitespace, enter a brief, or compose persisted convergence. Independence requires different kinds, occurrences, and origin groups; republications do not corroborate themselves. Source correction/retraction invalidates unsupported derivatives. Retrieval and extraction remain separate fail-closed connection classes.

- **Do not re-gate work that is no longer gated** (Zach, 2026-07-31, D-83). The frozen-scope regime and the Phase 2 evidence gates are retired; deferring a feature for "scope discipline," marking a design decision as blocking, or downgrading a schema change to a request for permission all reintroduce a gate that was deliberately removed. Defer something only when a *fact* forces it — data that does not exist yet, elapsed time that has not passed — and say which fact. The one standing gate is the data-governance one below.

_Superseded by the above, retained for history:_ ~~The scope is frozen; new object types or fields outside `stage-0/field-dictionary.md` require asking first. Build order is Stage 0 → v0.1 → … → v0.4, then stop. Declined items in Section 11 of the scoping doc stay declined.~~ The Section 11 declines and field dictionary remain the reference where none of the active additive specs applies.

## Trust boundaries (schema-level, non-negotiable)

- No table, column, or field may exist anywhere for a named individual's usage of the Nadia product. Champion engagement means deployment engagement (meetings, comms, advocacy), never product usage. Cohort usage data is aggregate only.
- Visibility works by inherited safe defaults: raw notes, stakeholder judgments, commercial strategy, and AI-generated interpretations default to internal-only. Generated client-facing outputs include only affirmatively promoted records, enforced in the generator code, not by convention.
- Stakeholder assessments (stance, influence, relationship strength) always carry a date and an evidence note.
- No sensitive personal data on people, ever: nothing on health, family, politics, or anything a works council would object to. People notes are professional observations only; rapport notes stay professional. Relationship-health signals (reciprocity, attendance, response time) are counts and distributions derived from our own correspondence — never sentiment inference, never product usage.

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
- `UX-FOUNDATION-SPEC.md` is the additive authority for canonical navigation,
  saved portfolio views, and the staged command-center/activity/outcomes path.
  Release 1 preserves the current account-tab taxonomy and trust boundaries.
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
