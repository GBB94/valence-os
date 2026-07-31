# HANDOFF — Valence OS

_Written 2026-07-29 for a fresh session with no conversation history. Read this, then `CLAUDE.md`, then the scoping doc. It tells you what exists, what was deliberately left out, what is gated, how to run it, and the lines you must not cross._

## What this is

Valence OS is an internal, single-editor web app for one Valence Engagement Manager to run a few very deep Fortune-100 accounts end to end. It is built **strictly to the frozen scoping doc** (`Valence-OS-Scoping-Doc.md`, v3.2). The build order and trust boundaries in that doc and in `CLAUDE.md` are binding and win over any individual prompt except an explicit, deliberate override from Zach.

**Status: Phase 3 feature-complete build IN PROGRESS.** `PHASE-3-SPEC.md` (Zach, 2026-07-30) is the current authority and a deliberate override of the earlier "stopping point." The scoping-doc build order (Stage 0 → v0 → v4) plus the gap items, §5N (MAP), §5O (Files/tags) are complete and the frontend redesign to `DESIGN-GUIDE.md` landed on `main` — those are now the *foundation* Phase 3 extends, not the finish line. See `PHASE-3-SPEC.md §0b` for the reconciliation of what already exists vs. what this phase adds.

**The prior "do not resume building" guidance is retired by the Phase 3 spec.** Building to feature-complete is now the instruction; the evidence gates are gone. What stays binding: the §2 trust boundaries, the design guide, mock-only data, tests green, decisions logged. The single remaining gate is **data governance, not scope** — every external connection is a mock adapter until hosting/data-handling is cleared at Valence (see `CONNECTIONS.md`, and `PHASE-3-SPEC.md §9`). Phase 3 progress and the newly permitted dependencies are logged in `decisions.md` (regime change: D-73).

**Phase 3 progress (build order in `PHASE-3-SPEC.md §10`):**
- **Task Zero — done.** Docs regime change; job table (migration 0011) + single in-process worker (`app/jobs.py`, env-gated `VALENCE_OS_WORKER`, default off) + jobs API. D-73/D-74.
- **Stage 1 — done.** Guided onboarding, launch checklists, org-chart placeholders (migration 0012). New backend: `app/onboarding.py`, `app/intake.py`, `app/routers/onboarding.py`, editable templates under `app/templates/`. Two new queue triggers (`checklist_overdue`, `unidentified_placeholder`). Frontend: onboarding wizard (`Onboarding.jsx`, fires on account create), checklists panel in the Plan tab (`Checklists.jsx`), placeholder nodes + coverage on the graph. Screenshots in `design-screenshots/stage-1/` (both themes). D-75. **86 tests pass.**
- **Build order reordered by the Comprehensive Spec (Part 7), D-76.** New trust boundary in force: professional observations only, no sensitive personal data (D-76).
- **Stage 2 — done.** People module core (migration 0013): layer model on stakeholder roles + layer-lane graph view; full buying-committee role taxonomy (table recreated to widen the enum); evidence-enforced coach-vs-champion (`advocacy_events`, computed at read time); person profile card (`GET /api/persons/{id}/card`, `PersonCard.jsx`) assembling roles/stance-trajectory/commitments/edges/history/advocacy; new `app/people_core.py`. Screenshots in `design-screenshots/stage-2/`. D-77. **94 tests pass.**
- **Stage 3 — done.** Cadence engine + relationship health + coverage analytics (migration 0014, `app/cadence.py`): per-role cadence targets (derived by quadrant, floored for seniors, overridable), the `cadence_overdue` queue trigger (replaces `stale_stakeholder`) with content-carrying suggested touches, health panel on the person card (reciprocity/attendance are honest `unknown` pending adapters), and coverage compliance/layer-heat/detractor-watch in the sidebar. Screenshots in `design-screenshots/stage-3/`. D-78. **102 tests pass.**
- **Stage 4 — done (core).** Communications ingestion + shared association engine (migration 0015): mock email (.eml) / recording adapters (`app/adapters.py`, fixtures under `app/fixtures/`), one association engine that learns from corrections (`app/association.py`, supersede-not-delete hints), ingestion through the job table (`app/ingestion.py`: `sync_emails`, `ingest_recording`), `comm_messages` threaded onto the ledger, priority flagging + the `unanswered_email` queue trigger, and a Comms panel in the Ledger tab. **Deferred to Stage 5 (D-79):** the §4.4 new extraction targets (placeholder-fill, pull-signal, deployment-moment, value-story) + the review-screen redesign — folded in with their consumers. Screenshots in `design-screenshots/stage-4/`. **108 tests pass.**
- **Stage 5 — done.** Relationship intelligence (migration 0016): champion development pipeline (`champion_candidates`, evidence-gated validate/arm/maintain, single-thread-risk analytic), influence paths (pure BFS over `relationship_edges`, two-hop-strong beats one-hop-weak, one-click intro task), executive alignment (`exec_pairings` + derived last-touch + unpaired-exec exposure), role-based messaging library (`messaging_entries`, seeded from `app/templates/messaging_library.yaml`), meeting dynamics (derived attendance/went-quiet, on the person card), and the **deferred §4.4 extraction targets** (placeholder-fill, pull-signal, deployment-moment, value-story) with a keyboard-driven review-screen redesign. New backend: `app/people_analytics.py`, `app/routers/relationships.py`. Frontend: `People.jsx` wrapper with Champions/Influence/Exec/Messaging sub-tabs. D-80. **118 tests pass.** (Screenshots flaked — see `design-screenshots/stage-5/VERIFICATION.md`.)
- **Remaining:** Stage 6 generators (Part 5), Stage 7 triggers+calendar+change-detection (6.1, 6.2, 3.9 — incl. the "no validated second champion" and expansion/pull-signal plays deferred here), Stage 8 CONNECTIONS.md + e2e demo.

**Running Phase 3 test count: 118** (was 67 at Phase 2 close). Backend still requires Python 3.12 (`.venv/bin/python -m pytest`).

## How to run / seed / test

Repo lives at `~/Desktop/Claude Projects/valence-os` (moved out of `~/Documents`, which is macOS-TCC-blocked — do not move it back). Backend is Python 3.12 + FastAPI + raw `sqlite3`; frontend is React (Vite).

```bash
# Backend (from backend/)
.venv/bin/python -m uvicorn app.main:app --port 8000
#   ^ run uvicorn as a module. The .venv/bin/uvicorn console script has a stale
#     hardcoded shebang from before the repo moved and will fail — use -m uvicorn.

# Seed / reset mock data (from backend/)
.venv/bin/python -m app.seed --reset      # wipe DB, apply migrations, load mock accounts
.venv/bin/python -m app.seed              # load into existing DB

# Tests (from backend/) — 118 tests, all green
.venv/bin/python -m pytest

# Frontend dev (from frontend/) — Vite on :5173, proxies API to :8000
npm run dev
npm run build                             # emits frontend/dist, served by the API in prod-ish mode
```

- DB path override: env var `VALENCE_OS_DB`; default file `valence_os.sqlite`.
- Migrations live in `backend/migrations/` as numbered `NNNN_*.sql`. The runner in `app/db.py` applies any file whose version isn't in `schema_migrations`. **Every schema change is a migration — no manual DB surgery.** Latest is `0016_stage5_relationship_intelligence.sql`.
- Git: commit as `git -c user.name='Sam' -c user.email='noreply@example.test' commit`, trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`, then `git push -q origin main`. Private repo `github.com/GBB94/valence-os`, `gh` authed as `GBB94`.

## What's built (by module → doc section)

Backend routers in `backend/app/routers/`, frontend views in `frontend/src/views/`. The table below is the **pre-Phase-3 foundation** (migrations 0001–0010); the Phase 3 additions (migrations 0011–0016: jobs, onboarding/checklists/placeholders, People module, cadence/health, ingestion/association, relationship intelligence) are in the **Phase 3 progress** list above.

| Area | Doc | Built |
|---|---|---|
| Capture / interactions / inbox | §5A, v0.1 | interactions, source references (link-first), capture inbox → convert-without-retype |
| Execution objects | §5B, v0.2 | commitments (two owners), tasks, risks, issues, decisions, milestones — soft-delete, close/resolve flows |
| Attention queue | §5C, v0.3 | rules-based, explainable ranking; stakeholder-coverage sidebar |
| Output generators | §5D, v0.4 | weekly team update, QBR — **client-safe by construction** |
| Commercial & deployment | §5G–J, v1 | expansion opportunities (staged budget), contract versions (canonical + overlay), phase gates, deployment moments, compliance items, scope changes, governance |
| Data & evidence | §5K–L, v2 | metric definitions + observations (freshness → stale renders **unknown**), versioned/sourced benchmarks, value-story library (incl. negative evidence), CSV import (preview/commit/rollback), operations screen |
| Visualization | §6b, v3 | stakeholder graph (Cytoscape), budget waterfall (Recharts), sparklines + bullet charts, timeline swimlanes |
| AI & automation | §5M, v4 | **pluggable** transcript extractor proposing structured updates for per-item accept/reject; plays trigger engine; notifications |
| Global search / cmd-K | §6 | SQLite FTS5 (migration 0008) |
| Portfolio export/restore | — | account export/import bundle |
| Mutual Action Plan | §5N | client-visible ★ promotion flag (migration 0009); MAP assembled from promoted items only |
| Files & context library | §5O | link-first, searchable, **tagged** source references + who-cites-each (migration 0010 = tags) |

The pluggable extractor (`app/extractor.py`): `get_extractor(backend)` returns a **mock** or an `api` backend; manual paste has its own endpoint. All three funnel through `validate_proposals()`, a strict predefined mutation set. **The mock extractor is the only one wired.** The `api` backend code exists but is dormant — see gated items.

## Design system & information architecture (2026-07-30 redesign)

The frontend was fully redesigned to **`DESIGN-GUIDE.md`** (repo root), which is now the standing design authority and **supersedes scoping-doc §6**. Read it before any frontend change. Highlights a future session must respect:

- **Tokens are law.** `frontend/src/tokens.css` is the single source of raw values (both theme palettes, `--sp-*` spacing, radii, type, motion). No raw hex or arbitrary pixels outside it. The one exception: canvas/SVG charts resolve tokens via `getComputedStyle` with a mirror-value fallback (SVG/canvas attributes can't take `var()`).
- **Fonts are self-hosted** (vendored IBM Plex woff2 under `frontend/src/assets/fonts`) — no CDN, no font npm dependency.
- **Three-state theme** (System/Light/Dark) via `data-theme` on `<html>` + a pre-paint script in `index.html`. Both themes are first-class; a change that only works in one is not done.
- **Navigation is four destinations** — Today, Accounts, Library, Operations — plus the **account workspace** (sticky context header + seven tabs: Overview, Ledger, People, Plan, Commercial, Evidence, Outputs). Program is a filter, not a nav branch. Capture is global (`c` shortcut / top bar), never a destination. Don't add a top-level destination without asking.
- **The Ledger** (`frontend/src/views/Ledger.jsx`) is one merged chronological master-detail table (interactions + execution objects + untriaged capture). **Today** is grouped by urgency band with the attention rail.
- **Freshness language** (`AgeChip`, `Unknown` in `ui.jsx`) appears on dated records; stale metric-derived values render Unknown, never carried-forward — this is a trust boundary, not decoration.
- **Colour carries meaning only:** status hues (green/amber/red) for state, the indigo accent for interaction, financial tokens for the waterfall (the single exception; it never shares a screen with status). State never rides on colour alone — badges pair colour with a shape.
- Shared primitives live in `frontend/src/ui.jsx` (`Btn`, `Badge`, `Card`, `PageHeader`, `SegTabs`, `Tooltip`, `AgeChip`, `Unknown`, `SlideOver`, `Empty`).

The redesign shipped as eight stacked PRs (`redesign-a-foundation` … `redesign-h-close`, PRs #1–#8). It changed **no backend, no behavior, and no schema**, and the §2 trust boundaries were re-verified (67/67) after the restructure. Open audit item: an automated contrast/keyboard pass in both themes (the browser extension wouldn't connect during the build, so verification was by build + review + a manual click-through).

## What's deferred, and why

- **Job table + in-process worker (§7/8).** ~~Deliberately not built.~~ **Built in Phase 3 Task Zero** (migration 0011, `app/jobs.py`; env-gated auto-worker `VALENCE_OS_WORKER`, default off — tests drive jobs synchronously). The Phase 3 spec made it a prerequisite because transcription/email-sync/association/scheduled generation are background work. This deferral is retired.
- **Real external connections stay mock.** Every external touchpoint is a mock adapter — the **real Claude-API extractor** (`api` backend in `app/extractor.py`) is present but dormant, and the email/transcription/calendar/enrichment/notification adapters return fixtures. Flipping any switch to real requires the Valence hosting/data-handling conversation and is recorded in `decisions.md` + the `CONNECTIONS.md` registry (Stage 8). §12 decision #3 (may AI call an external LLM?) is still open. **Do not wire any external API, key, or real source.**
- **Stages 6–8 not yet built.** Generators to finished artifacts (Part 5), new triggers + calendar + change detection (6.1/6.2/3.9), and `CONNECTIONS.md` + the e2e demo. See the Phase 3 progress list for what's done through Stage 5.
- **§11 "declined" items.** Stay declined. Do not reintroduce them as "improvements."

## Gated on the five open decisions (§12)

None of these block the current mock-data build; **all** must be answered at Valence before production architecture that's expensive to reverse:

1. Store complete transcripts, or only references/summaries/approved extracts?
2. Which systems are canonical for CRM, usage metrics, contracts, client docs?
3. May AI processing call an external LLM, or must it use an approved Valence service/environment? _(blocks wiring the real extractor)_
4. Approved internal stack: identity, hosting, database, storage, logging, backups?
5. Personal tool, or a credible path to other Engagement Managers using it?

Production-mode items (SSO/MFA, approved hosting/DB, encryption at rest, off-site backups) are gated on these plus hosting approval. Don't build them speculatively.

## Invariants a future session must not break

These are enforced in code and in tests. If you touch nearby code, keep them true:

1. **No individual product-usage data, ever.** No table, column, or field for a named individual's usage of the Nadia product. Champion engagement = deployment engagement (meetings, comms, advocacy), never product usage. Cohort usage is aggregate only. Guarded by `test_capture_v0_1.py::test_no_individual_usage_field_anywhere` — do not weaken it.
2. **Client-facing output is safe by construction.** Team update, QBR, and MAP generators include only affirmatively promoted / non-negative records, enforced in the generator code, not by convention. Internal-only fields are never even queried into a client artifact. (Tested: a planted "INTERNAL" record never appears in output.)
3. **Stakeholder assessments carry a date + evidence.** Stance, influence, relationship strength always require an assessed-on date and an evidence note.
4. **Mock/synthetic data only.** No real client names, people, transcripts, or figures anywhere — including tests, seeds, comments, commit messages.
5. **No hard-coded benchmarks.** Benchmarks are data: versioned, sourced, with population and period. Stale metric-derived indicators render **unknown**, never carried-forward good state. Metrics are ingested, never recomputed.
6. **Scope = the Phase 3 spec.** The frozen-scope regime is **retired** (D-73): object types, fields, screens, and background infrastructure named in `PHASE-3-SPEC.md` are in-scope to build now, in its Part 7 order. New objects/fields **outside** what that spec calls for still require asking Zach first; the `stage-0/field-dictionary.md` fence still applies to anything the spec doesn't address.
7. **Stage discipline.** Build one Phase 3 stage at a time; each stage lands with tests, both-theme screenshots, a `decisions.md` entry, and a HANDOFF update before the next begins. (The old "do not build absent a new instruction" rule is superseded — the standing instruction is to build to feature-complete in the spec's order.)

## Where to look

- `PHASE-3-SPEC.md` — **current scope authority** (the consolidated Comprehensive Spec; build order in Part 7).
- `Valence-OS-Scoping-Doc.md` — the original source of truth (v3.2); still governs anything the Phase 3 spec doesn't address.
- `CLAUDE.md` — standing rules (restates the binding constraints).
- `decisions.md` — decision log, newest first (D-80 is Stage 5; Phase 3 runs D-73→D-80).
- `README.md` — living project tour + run instructions + build-status table.
- `stage-0/field-dictionary.md` — the allowed object/field set; the fence for anything outside the Phase 3 spec (invariant #6).
