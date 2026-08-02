# Valence OS

An internal, **single-editor** web app for running a handful of very deep Fortune-100 accounts end to end — the execution ledger, stakeholders, commercial motion, evidence, and generated outputs in one place. Built for an Engagement Manager at Valence (who sells *Nadia*, an AI coaching product) to live in daily and brief the team in minutes.

> **Context / source of truth.** Phase 3, the Expansion Engine, and the Internal Operating Layer are implemented through Stage 10 under `PHASE-3-SPEC.md`, `EXPANSION-ENGINE-SPEC.md`, and `INTERNAL-OPS-SPEC.md`. `ADOPTION-CAMPAIGN-SPEC.md` and `ACCOUNT-COPILOT-SPEC.md` are the accepted **Stage 11** and **Stage 12** authorities; current implementation status is tracked in `HANDOFF.md`. `Valence-OS-Scoping-Doc.md` (v3.2) remains the original source of truth where the additive specs are silent. The standing rules are in `CLAUDE.md`, the Stage-0 paper model is in `stage-0/`, and non-obvious decisions are logged newest-first in `decisions.md`. All repository data is **mock/synthetic**. **One gate remains: build everything, connect nothing real** until Valence approves hosting and data handling.

## What it is (the one-paragraph tour)
Accounts contain **programs** (bounded deployments/commercial motions, each with a phase). Assigning an account kicks off a guided **onboarding pack** (intake parse, seeded plan, launch checklists with falling-behind escalation, org-chart placeholders for people you haven't identified). You **capture** interactions in under a minute; ambiguous notes land in a **capture inbox** and later convert — with no retype — into execution records. A rules-based, explainable **attention queue** ranks what needs you and why. The **People module** covers layers, buying-committee roles, cadence, relationship health, champion development, influence paths, executive alignment, messaging, and meeting dynamics. Mock communications flow through a job table and shared association engine. **Commercial** adds a reconciled whitespace map, explicit row seat inventory, value targets, funding pools, fiscal timing, and atomic back-scheduled asks to opportunities and contracts. Aggregate cohort **metrics** keep stable segment/view identity; stale evidence renders *unknown*. Generators produce editable, review-gated pre-call briefs, expansion business cases, value reviews/QBRs, champion kits, kickoff decks, and schedulable weekly drafts, with PPTX/PDF export. Client-facing output is promotion- and source-gated by construction; nothing is auto-sent. Visualizations include the stakeholder graph and a currency-safe budget waterfall. **AI** remains pluggable (offline mock, local LLM, or Claude API) and proposes structured updates for per-item acceptance. A recurring **signals engine** turns fresh usage bars, client pull, calendar moments, confirmed org changes, champion coverage, and account growth into explainable episodes; mock calendar, enrichment, and HRIS-shaped adapters exercise the flow without connecting real systems.

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
- **Run the tests:** `cd backend && .venv/bin/python -m pytest`  (322 tests)
- **Launch note:** use `python -m uvicorn …`, not `.venv/bin/uvicorn` — the console script bakes in an absolute shebang that breaks if the folder moves. If the venv itself was moved: `rm -rf .venv && uv venv --python 3.12 && uv pip install -e .`.

## Repo layout
```
PHASE-3-SPEC.md             completed comprehensive Phase 3 authority
EXPANSION-ENGINE-SPEC.md    completed Stages 5.5–9 expansion authority
INTERNAL-OPS-SPEC.md        Implemented Stage 10 internal operating layer authority
ADOPTION-CAMPAIGN-SPEC.md   Accepted Stage 11 authority — adoption campaigns (status in HANDOFF.md)
ACCOUNT-COPILOT-SPEC.md     Accepted Stage 12 authority — grounded account copilot (status in HANDOFF.md)
Valence-OS-Scoping-Doc.md   the original source of truth (v3.2)
CLAUDE.md                   standing rules (trust boundaries, data rules, design)
DESIGN-GUIDE.md             standing design authority (supersedes scoping-doc §6)
HANDOFF.md                  fresh-session onboarding + current build status
CONNECTIONS.md              executable real-data gate registry; every boundary is local/mock
decisions.md                decision log, newest first
stage-0/                    paper model + mock seed data (seed-data/*.yaml)
docs/                       documentation index, runbooks, and archived evidence
backend/
  app/                      FastAPI app: routers/, db.py (migration runner), seed.py, extractor.py,
                            jobs.py, onboarding.py, people_core.py, cadence.py, ingestion.py,
                            association.py, people_analytics.py, output_gen.py, queue.py …
  migrations/               0001…0034 landed; Stages 10–12 are complete
  tests/                    pytest (per-slice/-stage + full acceptance script)
frontend/src/               React views (one per module/tab) + api.js + tokens.css
```

## Build status

**Foundation — Section 9 build order complete:** Stage 0 → **v0** (capture / execution / attention / output) → **v1** (commercial & deployment) → **v2** (data & evidence) → **v3** (visualization) → **v4** (AI & automation), plus global search, cmd-K, export/restore, MAP, and the files library. Migrations 0001–0010.

**Frontend redesign — complete:** fully redesigned to `DESIGN-GUIDE.md` (eight phases A–H + a corrective pass + a punch-list pass). Backend, behavior, and the §2 trust boundaries unchanged; no schema changes. See `docs/archive/design-audit.md` for the retrospective value inventory.

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

**Phase 3 — feature-complete through Stage 9** (authority: `PHASE-3-SPEC.md`, with the expansion interleave in `EXPANSION-ENGINE-SPEC.md`). The one remaining gate is data governance (build everything, connect nothing real). Migrations 0011–0025.

| Stage | Delivered |
|---|---|
| **0 · Task Zero** | docs regime change; **job table + in-process worker** (env-gated), jobs API (migration 0011) |
| **1 · Onboarding + checklists** | guided onboarding pack, intake parse, seeded plan, launch checklists with falling-behind escalation, org-chart **placeholders** (migration 0012) |
| **2 · People module core** | stakeholder **layers** + full buying-committee taxonomy, evidence-enforced coach-vs-champion, layer-lane graph view, **person profile card** (migration 0013) |
| **3 · Cadence + health + coverage** | per-role **cadence engine** (content-carrying suggested touches), measured relationship-**health** panel, coverage/layer-heat/detractor analytics (migration 0014) |
| **4 · Ingestion + association** | mock email/recording **adapters**, one shared **association engine** (learns from corrections), ingestion via the job table, comms panel + priority flagging (migration 0015) |
| **5 · Relationship intelligence** | **champion pipeline**, **influence paths**, **exec alignment**, role-based **messaging library**, **meeting dynamics**, + §4.4 extraction targets (placeholder-fill / pull-signal / deployment-moment / value-story) with a keyboard-driven review screen (migration 0016) |
| **5.5 · Expansion nouns** | reconciled whitespace map with explicit row seat inventory; value-realization ledger with linked cohort evidence; funding/fiscal map/atomic ask calendar; revenue semantics (migrations 0017–0019, hardened in 0021) |
| **6 · Finished artifacts** | editable/review-gated briefs, business cases, value reviews/QBRs, champion kits and kickoff decks; scheduled weekly drafts; PPTX/PDF render; champion handoff history (migrations 0020–0021) |
| **7 · Signals, calendar, org change** | recurring condition episodes with clear/re-arm semantics, windows/hysteresis/freshness/cooldowns, remaining plays, client-pull precedence and value pacing; mock `.ics`, enrichment, and headcount adapters; confirmation-only org changes + succession (migration 0022) |
| **7.5 · Qualification, triggers, renewal, growth** | five explicit opportunity slots; sourced operational agreements with earned-trigger events; derived renewal command center; overlap-safe account growth plan and client-facing mutual twin (migration 0023) |
| **8 · Connection governance + e2e proof** | complete `CONNECTIONS.md` registry backed by a fail-closed runtime gate and Operations view; reproducible Phase 3 demo plus executable assigned-account → delivered-expansion-case test; cross-stage integration fixes (migration 0024) |
| **9 · Portfolio analytics + playbook** | count-and-denominator portfolio commercial analytics; explicit cell/funding links for velocity; currency-safe actual/projected revenue movement; deterministic shape matching; human-curated play/message promotion (migration 0025) |
| **10 · Internal operating layer** | account-level commitment provenance; period forecast locks/submissions/calibration; internal asks and snapshotted escalation chains; review/status governance and bidirectional no-surprises reporting; roster/coverage briefs; sourced cross-account product feedback and internal analytics (migrations 0026–0030) |
| **11 · Adoption campaigns** | cohort-scoped intervention plans, comparable locked baselines, explicit cautions, signal conversion, canonical Today integration, immutable retrospectives, and portfolio learning (migrations 0031–0033) |
| **12 · Account Copilot** | deterministic mock-only scoped analyst; frozen claim sources; reviewed change cursors; canonical weekly planning; bounded follow-ups/entity resolution; previewed internal drafts; correction review; executable golden activation/rollback controls (migration 0034) |

**Phase 3 feature-complete build — complete through Stage 12.** Production-mode items remain gated on the open §12 decisions and hosting approval. See `HANDOFF.md` for the current handoff.

**Stage 10 — implemented and externally adversarially reviewed.** `INTERNAL-OPS-SPEC.md` adds the internal operating layer: forecast, asks/escalations, reviews/reporting, roster/coverage, product feedback, and honest portfolio analytics. Migration 0030 closes the external review's leadership-report, forecast-unit, calibration, no-surprises, navigation, policy, Today, and usability findings. All external delivery remains disabled.

## Trust & correctness rules enforced in code (and tested)
- **No table or column anywhere for a named individual's product usage** — asserted by a test. Champion/relationship signals are deployment engagement (meetings, comms, advocacy) and derived counts only.
- **No sensitive personal data on people** — professional observations only; no health/family/politics. Relationship-health signals (reciprocity, attendance) are counts and response-time distributions from our own correspondence, never sentiment inference.
- Client-facing artifacts include **only** affirmatively promoted, sourced, non-negative records **by construction**; raw notes, stakeholder judgments, internal whitespace tactics, and unsourced plan items cannot leak. The weekly team update and pre-call brief are explicitly internal.
- Stakeholder assessments (stance, influence, relationship strength) **require a date + evidence note** (DB CHECK + API guard).
- Metric-derived indicators past their freshness threshold render as **unknown**, never carried-forward.
- Cross-account and cross-program references are rejected at the API and reinforced with database triggers where SQLite can express the relationship.
- Monetary movements enforce sign and ISO-currency semantics; mixed/unknown-currency recovered spend is never summed into a waterfall.
- **No hard-coded benchmarks** — benchmarks are versioned/sourced data with population + period.
- Versioned migrations from the first table; append-only audit log on every write; soft-delete throughout.
