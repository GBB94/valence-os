# Valence OS

An internal, **single-editor** web app for running a handful of very deep Fortune-100 accounts end to end — the execution ledger, stakeholders, commercial motion, evidence, and generated outputs in one place. Built for an Engagement Manager at Valence (who sells *Nadia*, an AI coaching product) to live in daily and brief the team in minutes.

> **Context / source of truth.** This project is built to `Valence-OS-Scoping-Doc.md` (v3.2, scope frozen). The standing rules that govern every change are in `CLAUDE.md`; the Stage-0 paper model (entity diagram, field dictionary, state transitions, attention rules, wireframes, acceptance script, mock seed) is in `stage-0/`; and every non-obvious decision is logged newest-first in `decisions.md`. All data in the repo is **mock/synthetic** — no real client names, people, or figures anywhere.

## What it is (the one-paragraph tour)
Accounts contain **programs** (bounded deployments/commercial motions, each with a phase). You **capture** interactions in under a minute; ambiguous notes land in a **capture inbox** and later convert — with no retype — into **commitments** (two owners: who does it + the Valence follow-up owner), **risks**, **issues**, **decisions**, **tasks**, and **milestones**. A rules-based, explainable **attention queue** ranks what needs you and why. **Commercial** tracks expansion opportunities (staged budget) and contract versions (canonical copy + operational overlay). **Metrics** are ingested from the Data team (never recomputed; stale renders as *unknown*); a **value-story library** captures wins *and* negative evidence. Generators produce a weekly **team update** and a client-facing **QBR** — both exclude internal-only material *by construction*. Visualizations: a **stakeholder graph** and a **budget waterfall**. **AI**: transcript extraction (pluggable — offline mock, your own local LLM, or the Claude API) proposing structured updates for per-item acceptance, plus a **plays** trigger engine.

## Stack
- **Backend:** Python 3.12 · FastAPI · SQLite with **versioned SQL migrations** (raw `sqlite3`, no ORM) · SQLite **FTS5** for global search.
- **Frontend:** React (Vite) · Cytoscape (stakeholder graph) · Recharts (budget waterfall) · dense Linear-class UI, one neutral surface + one accent.
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
- **Run the tests:** `cd backend && .venv/bin/python -m pytest`  (60 tests)
- **Launch note:** use `python -m uvicorn …`, not `.venv/bin/uvicorn` — the console script bakes in an absolute shebang that breaks if the folder moves. If the venv itself was moved: `rm -rf .venv && uv venv --python 3.12 && uv pip install -e .`.

## Repo layout
```
Valence-OS-Scoping-Doc.md   the source of truth (v3.2, frozen)
CLAUDE.md                   standing rules (trust boundaries, data rules, design)
decisions.md                decision log, newest first (D-01…)
stage-0/                    paper model + mock seed data (seed-data/*.yaml)
backend/
  app/                      FastAPI app: routers/, db.py (migration runner), seed.py, extractor.py, search.py, output_gen.py, queue.py …
  migrations/               0001…0008 numbered SQL; every schema change is a migration
  tests/                    pytest (per-slice + full acceptance script)
frontend/src/               React views (one per module) + api.js
```

## Build status

**Section 9 build order — complete:** Stage 0 → **v0** (capture / execution / attention / output) → **v1** (commercial & deployment) → **v2** (data & evidence) → **v3** (visualization) → **v4** (AI & automation). Migrations 0001–0008.

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

Also built beyond the numbered phases: timeline **swimlanes** (§5F), stakeholder **coverage** sidebar (§5C), metric **sparklines + bullet charts** (§6b).

**Remaining doc-described capabilities:** a job table + in-process worker (§7/8 — deliberately deferred; all work is synchronous at this scale). Two need a small scope decision before building (they'd add an object or field): Mutual Action Plan (§5N) and tags on the Files & context library (§5O). Production-mode items (SSO/MFA, approved hosting/DB, encryption, off-site backups) are gated on the five open decisions in §12 and hosting approval. §11 "declined" items stay out.

## Trust & correctness rules enforced in code (and tested)
- **No table or column anywhere for a named individual's product usage** — asserted by a test.
- Client-facing generators (team update, QBR) include **only** affirmatively-promoted, non-negative records **by construction** — raw notes and stakeholder judgments can't leak.
- Stakeholder assessments (stance, influence, relationship strength) **require a date + evidence note** (DB CHECK + API guard).
- Metric-derived indicators past their freshness threshold render as **unknown**, never carried-forward.
- **No hard-coded benchmarks** — benchmarks are versioned/sourced data with population + period.
- Versioned migrations from the first table; append-only audit log on every write; soft-delete throughout.
