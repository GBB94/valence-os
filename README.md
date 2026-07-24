# Valence OS

Internal single-editor web app for managing F100 deployments and expansions. Built to `Valence-OS-Scoping-Doc.md` (v3.2, scope frozen). Standing rules in `CLAUDE.md`; Stage-0 paper model in `stage-0/`; decision trail in `decisions.md`.

**Build order:** Stage 0 ✅ → **v0.1 capture ✅ (current)** → v0.2 execution → v0.3 attention → v0.4 output.

## Stack
- Backend: Python 3.12 · FastAPI · SQLite with versioned SQL migrations · raw `sqlite3`, no ORM.
- Frontend: React (Vite), single accent, dense power-user layout.
- One process: FastAPI serves the built frontend from `frontend/dist`; Vite dev server in development.

## Run it

```bash
# 1. Backend deps (once)
cd backend
uv venv --python 3.12
uv pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7" "pyyaml>=6.0" "httpx>=0.27" "pytest>=8.0"

# 2. Load the mock seed (creates + migrates the DB)
.venv/bin/python -m app.seed --reset

# 3a. Production-ish: build the frontend, serve everything from :8000
cd ../frontend && npm install && npm run build
cd ../backend && .venv/bin/python -m uvicorn app.main:app --port 8000
#   open http://localhost:8000

# 3b. Or dev with hot reload (two terminals)
.venv/bin/python -m uvicorn app.main:app --port 8000 --reload   # terminal 1
cd frontend && npm run dev                                      # terminal 2 -> http://localhost:5173
```

> Note: launch uvicorn as `python -m uvicorn` (not `.venv/bin/uvicorn`). The console
> script bakes in an absolute shebang, so it breaks if the project folder is moved;
> `python -m` uses the location-independent interpreter symlink. If the venv itself
> was moved, recreate it: `rm -rf .venv && uv venv --python 3.12 && uv pip install ...`.

Reset to clean mock data anytime: `python -m app.seed --reset`.
Run backend tests: `cd backend && .venv/bin/python -m pytest`.

## What v0 does (execution ledger — all four slices)
- **v0.1 capture** — accounts, programs, people, per-program stakeholder roles (dated + evidenced stance); 30-second interaction quick entry (account required, program optional); capture inbox for untriaged notes.
- **v0.2 execution** — tasks, commitments (two owners + due date), decisions, risks, issues, milestones; closure rules enforced (mitigation ≠ closure, commitments close on acknowledgement, decisions supersede); inbox → object conversion with no retype.
- **v0.3 attention** — the ranked, explainable portfolio queue (six triggers, each explains itself) with snooze/resolve rules; the two independent account statuses (delivery + commercial), no composite.
- **v0.4 output** — account history / interaction timeline with back-references; one-click weekly team update, freshness-stamped, internal-only material excluded by construction.

Versioned migrations from the first table; append-only audit log on every write; soft-delete throughout.

**The full Stage-0 acceptance script passes** (capture → commitment + risk → queue → history → team update, no new object type). Run `cd backend && .venv/bin/python -m pytest` — see `tests/test_acceptance_full.py`.

## v1–v4 (all scoped phases, complete)
- **v1 commercial & deployment** — expansion opportunities (staged budget, closed outcomes), contract versions (synced copy + operational overlay), phase gates, deployment moments, compliance/readiness lanes, scope changes, governance cadence, program Timeline, renewal-window queue trigger.
- **v2 data & evidence** — Data-team metric definitions + observations with freshness (stale→unknown), versioned/sourced benchmarks, value-story library incl. negative evidence, CSV import adapter (preview/commit/rollback), QBR generator (client-facing, visibility-excluded by construction, content-typed, stamped), operations screen.
- **v3 visualization** — Cytoscape stakeholder graph (size=influence, color=stance, edge=type) + power-interest toggle, Recharts budget waterfall, richer metric views.
- **v4 AI & automation** — transcript extraction (local swappable mock under the Section 3 security model; per-item human acceptance), plays trigger engine with effectiveness notes, notifications, pre-call briefing.

Migrations 0001–0007. 51 backend tests. The frozen-scope object model was never exceeded; every closure/visibility/trust rule is enforced in code (and tested), not by convention.

## Trust boundaries enforced now
- No table or column anywhere for a named individual's product usage (there's a test asserting this).
- Stakeholder stance requires a date + evidence note (DB CHECK + API guard).
- Raw notes and stakeholder judgments are internal-only by default.
