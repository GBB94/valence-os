# Valence OS

An internal, **single-editor** web app for running a handful of very deep Fortune-100 accounts end to end — the execution ledger, stakeholders, commercial motion, evidence, and generated outputs in one place. Built for an Engagement Manager at Valence (who sells *Nadia*, an AI coaching product) to live in daily and brief the team in minutes.

> **Context / source of truth.** The current scope authority is `PHASE-3-SPEC.md` (the consolidated *Comprehensive Spec*, July 2026), a deliberate override of the earlier frozen-scope regime: build to feature-complete now, in its Part 7 order. `Valence-OS-Scoping-Doc.md` (v3.2) remains the original source of truth for anything the Phase 3 spec doesn't address. The standing rules that govern every change are in `CLAUDE.md`; the Stage-0 paper model (entity diagram, field dictionary, state transitions, attention rules, wireframes, acceptance script, mock seed) is in `stage-0/`; and every non-obvious decision is logged newest-first in `decisions.md`. All data in the repo is **mock/synthetic** — no real client names, people, or figures anywhere. **One gate remains: build everything, connect nothing real** — every external touchpoint (email, recordings, calendar, transcription, LLM, notifications, storage, hosting) is a mock adapter until the Valence hosting/data-handling conversation happens.

## What it is (the one-paragraph tour)
Accounts contain **programs** (bounded deployments/commercial motions, each with a phase). Assigning an account kicks off a guided **onboarding pack** (intake parse, seeded plan, launch checklists with falling-behind escalation, org-chart placeholders for people you haven't identified). You **capture** interactions in under a minute; ambiguous notes land in a **capture inbox** and later convert — with no retype — into **commitments** (two owners: who does it + the Valence follow-up owner), **risks**, **issues**, **decisions**, **tasks**, and **milestones**. A rules-based, explainable **attention queue** ranks what needs you and why. The **People module** models stakeholders by horizontal **layer** and the full buying-committee role taxonomy (coach-vs-champion enforced by advocacy evidence), with a per-person **cadence engine**, a measured **relationship-health** panel, a **champion development pipeline**, **influence-path** route-planning to people you haven't met, an **executive-alignment** map, a role-based **messaging library**, and **meeting-dynamics** attendance. **Communications ingestion** syncs a mock inbox and mock recordings through a **job table**, associates them to accounts/people, and flags priority emails. **Commercial** tracks expansion opportunities (staged budget) and contract versions (canonical copy + operational overlay). **Metrics** are ingested from the Data team (never recomputed; stale renders as *unknown*); a **value-story library** captures wins *and* negative evidence. Generators produce a weekly **team update**, a client-facing **QBR**, and a **Mutual Action Plan** — all excluding internal-only material *by construction*. Visualizations: a **stakeholder graph** (network / layer-lane / power-interest) and a **budget waterfall**. **AI**: pluggable transcript/email extraction (offline mock, your own local LLM, or the Claude API) proposing structured updates for per-item acceptance, plus a **plays** trigger engine.

## Stack
- **Backend:** Python 3.12 · FastAPI · SQLite with **versioned SQL migrations** (raw `sqlite3`, no ORM) · SQLite **FTS5** for global search.
- **Frontend:** React (Vite) · Cytoscape (stakeholder graph) · Recharts (budget waterfall) · a dense "instrument, not dashboard" UI redesigned to **`DESIGN-GUIDE.md`** (the standing design authority): a token system (`tokens.css`), self-hosted IBM Plex, three-state light/dark theming, a four-destination IA (Today / Accounts / Library / Operations) with a tabbed account workspace, and the freshness language on every dated record.
- **One process:** FastAPI serves the built frontend from `frontend/dist`; Vite dev server in development.
- **Optional:** the `anthropic` SDK, only for the API transcript-extraction backend.

## Run it

```bash
# 1. Backend env + deps (once)
cd backend
uv venv --python 3.12
uv pip install -e .                      # installs deps from pyproject.toml
#   (or: uv pip install "fastapi" "uvicorn[standard]" "pydantic" "pyyaml" "httpx" "pytest" "anthropic")

# 2. Load the mock seed (creates + migrates the DB)
.venv/bin/python -m app.seed --reset

# 3a. Serve everything from :8000 (build the frontend, then run the API)
cd ../frontend && npm install && npm run build
cd ../backend && .venv/bin/python -m uvicorn app.main:app --port 8000
#   open http://localhost:8000

# 3b. Or dev with hot reload (two terminals)
.venv/bin/python -m uvicorn app.main:app --port 8000 --reload   # terminal 1
cd ../frontend && npm run dev                                   # terminal 2 -> http://localhost:5173
```

- **Reset to clean mock data:** `cd backend && .venv/bin/python -m app.seed --reset`
- **Run the tests:** `cd backend && .venv/bin/python -m pytest`  (118 tests)
- **Launch note:** use `python -m uvicorn …`, not `.venv/bin/uvicorn` — the console script bakes in an absolute shebang that breaks if the folder moves. If the venv itself was moved: `rm -rf .venv && uv venv --python 3.12 && uv pip install -e .`.

## Repo layout
```
PHASE-3-SPEC.md             current scope authority (Comprehensive Spec; build order in Part 7)
Valence-OS-Scoping-Doc.md   the original source of truth (v3.2)
CLAUDE.md                   standing rules (trust boundaries, data rules, design)
DESIGN-GUIDE.md             standing design authority (supersedes scoping-doc §6)
HANDOFF.md                  fresh-session onboarding + current build status
decisions.md                decision log, newest first (D-01…D-80)
design-audit.md             redesign value inventory + contrast audit
stage-0/                    paper model + mock seed data (seed-data/*.yaml)
docs/archive/               superseded point-in-time briefs (history only)
backend/
  app/                      FastAPI app: routers/, db.py (migration runner), seed.py, extractor.py,
                            jobs.py, onboarding.py, people_core.py, cadence.py, ingestion.py,
                            association.py, people_analytics.py, output_gen.py, queue.py …
  migrations/               0001…0016 numbered SQL; every schema change is a migration
  tests/                    pytest (per-slice/-stage + full acceptance script)
frontend/src/               React views (one per module/tab) + api.js + tokens.css
```

## Build status

**Foundation — Section 9 build order complete:** Stage 0 → **v0** (capture / execution / attention / output) → **v1** (commercial & deployment) → **v2** (data & evidence) → **v3** (visualization) → **v4** (AI & automation), plus global search, cmd-K, export/restore, MAP, and the files library. Migrations 0001–0010.

**Frontend redesign — complete:** fully redesigned to `DESIGN-GUIDE.md` (eight phases A–H + a corrective pass + a punch-list pass). Backend, behavior, and the §2 trust boundaries unchanged; no schema changes. See `design-audit.md` for the value inventory.

| Phase | Delivered |
|---|---|
| **v0.1 capture** | accounts, programs, people, per-program stakeholder roles (dated + evidenced stance), 30-second interaction quick entry, capture inbox |
| **v0.2 execution** | tasks, commitments (two owners + due date), decisions, risks, issues, milestones; closure rules (mitigation ≠ closure, commitments close on acknowledgement, decisions supersede); inbox → object conversion, no retype |
| **v0.3 attention** | ranked, explainable portfolio queue (9 triggers, each explains itself) with snooze/resolve; two independent account statuses (delivery + commercial), no composite |
| **v0.4 output** | account history / interaction timeline with back-references; weekly team update (freshness-stamped, internal-only excluded by construction) |
| **v1 commercial & deployment** | expansion opportunities (staged budget, closed outcomes), contract versions (synced copy + operational overlay), phase gates, deployment moments, compliance/readiness lanes, scope changes, governance cadence, program timeline, renewal-window queue trigger |
| **v2 data & evidence** | metric definitions + observations w/ freshness (stale→unknown), versioned/sourced benchmarks, value-story library incl. negative evidence, CSV import adapter (preview/commit/rollback), QBR generator, operations screen |
| **v3 visualization** | Cytoscape stakeholder graph (size=influence, color=stance) + power-interest toggle, Recharts budget waterfall |
| **v4 AI & automation** | pluggable transcript extraction (mock / manual local-LLM / Claude API) under the Section-3 security model, plays trigger engine w/ effectiveness notes, notifications, pre-call briefing |
| **+ global search** | SQLite FTS5 across native records and stored summaries (Section 8) |
| **+ cmd-K palette** | keyboard-first command palette: nav + account jumps + live search (Section 6) |
| **+ account export/restore** | full per-account export → restore into a clean install, round-trip tested (Section 7 / success criterion #8) |

Also built beyond the numbered phases: timeline **swimlanes** (§5F), stakeholder **coverage** sidebar (§5C), metric **sparklines + bullet charts** (§6b), the **Mutual Action Plan** (§5N — client-facing joint plan from items promoted via a ★ on the Execution board), and the **Files & context library** (§5O — link-first, searchable, **tagged** list of source references with the records that cite each).

**Phase 3 — feature-complete build, in progress** (authority: `PHASE-3-SPEC.md`; build order in Part 7). The evidence gates are retired; the one remaining gate is data governance (build everything, connect nothing real). Migrations 0011–0016.

| Stage | Delivered |
|---|---|
| **0 · Task Zero** | docs regime change; **job table + in-process worker** (env-gated), jobs API (migration 0011) |
| **1 · Onboarding + checklists** | guided onboarding pack, intake parse, seeded plan, launch checklists with falling-behind escalation, org-chart **placeholders** (migration 0012) |
| **2 · People module core** | stakeholder **layers** + full buying-committee taxonomy, evidence-enforced coach-vs-champion, layer-lane graph view, **person profile card** (migration 0013) |
| **3 · Cadence + health + coverage** | per-role **cadence engine** (content-carrying suggested touches), measured relationship-**health** panel, coverage/layer-heat/detractor analytics (migration 0014) |
| **4 · Ingestion + association** | mock email/recording **adapters**, one shared **association engine** (learns from corrections), ingestion via the job table, comms panel + priority flagging (migration 0015) |
| **5 · Relationship intelligence** | **champion pipeline**, **influence paths**, **exec alignment**, role-based **messaging library**, **meeting dynamics**, + §4.4 extraction targets (placeholder-fill / pull-signal / deployment-moment / value-story) with a keyboard-driven review screen (migration 0016) |

**Remaining Phase 3 stages:** 6 · generators to finished artifacts (real `.pptx`, champion kit, expansion business case, schedulable team update); 7 · new triggers + calendar + org-change detection; 8 · `CONNECTIONS.md` registry + the end-to-end demo. Production-mode items (SSO/MFA, approved hosting/DB, encryption, off-site backups) remain gated on the five open decisions in §12 and hosting approval. §11 "declined" items stay out. See `HANDOFF.md` for the current handoff.

## Trust & correctness rules enforced in code (and tested)
- **No table or column anywhere for a named individual's product usage** — asserted by a test. Champion/relationship signals are deployment engagement (meetings, comms, advocacy) and derived counts only.
- **No sensitive personal data on people** — professional observations only; no health/family/politics. Relationship-health signals (reciprocity, attendance) are counts and response-time distributions from our own correspondence, never sentiment inference.
- Client-facing generators (team update, QBR) include **only** affirmatively-promoted, non-negative records **by construction** — raw notes and stakeholder judgments can't leak.
- Stakeholder assessments (stance, influence, relationship strength) **require a date + evidence note** (DB CHECK + API guard).
- Metric-derived indicators past their freshness threshold render as **unknown**, never carried-forward.
- **No hard-coded benchmarks** — benchmarks are versioned/sourced data with population + period.
- Versioned migrations from the first table; append-only audit log on every write; soft-delete throughout.
