# Account OS

Internal single-editor web app for managing F100 deployments and expansions. Built to `Account-OS-Scoping-Doc.md` (v3.2, scope frozen). Standing rules in `CLAUDE.md`; Stage-0 paper model in `stage-0/`; decision trail in `decisions.md`.

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

## What v0.1 does (capture slice)
- Accounts, programs, people, per-program stakeholder roles (dated + evidenced stance).
- Interaction quick entry (the 30-second path): account required, program optional (account-level touches allowed), participants, summary, internal-only notes, and ambiguous notes dropped straight to the **capture inbox** with no classification.
- Capture inbox: view untriaged items, dismiss (auditable). Conversion to commitments/risks/tasks lands in v0.2.
- Versioned migrations from the first table; append-only audit log on every write; soft-delete.

Portfolio home, execution board, and history are intentionally placeholders until their slices (v0.2–v0.4) — nothing scaffolded ahead.

## Trust boundaries enforced now
- No table or column anywhere for a named individual's product usage (there's a test asserting this).
- Stakeholder stance requires a date + evidence note (DB CHECK + API guard).
- Raw notes and stakeholder judgments are internal-only by default.
