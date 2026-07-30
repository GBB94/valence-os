# HANDOFF — Valence OS

_Written 2026-07-29 for a fresh session with no conversation history. Read this, then `CLAUDE.md`, then the scoping doc. It tells you what exists, what was deliberately left out, what is gated, how to run it, and the lines you must not cross._

## What this is

Valence OS is an internal, single-editor web app for one Valence Engagement Manager to run a few very deep Fortune-100 accounts end to end. It is built **strictly to the frozen scoping doc** (`Valence-OS-Scoping-Doc.md`, v3.2). The build order and trust boundaries in that doc and in `CLAUDE.md` are binding and win over any individual prompt except an explicit, deliberate override from Zach.

**Status: feature-complete backend + a completed frontend redesign, both on `main`.** The Section 9 build order (Stage 0 → v0 → v4) is complete, plus the doc-described gap items, §5N (MAP), and §5O (Files & context library incl. tags). Then the **frontend was fully redesigned to `DESIGN-GUIDE.md`** (the standing design authority, which supersedes scoping-doc §6) — eight phases + a corrective pass, all landed on `main`. See the "Design system & information architecture" section below and `design-audit.md`.

**On "do not resume building" — read carefully, the two statements are not in conflict.** The *product feature set* is at its intended stopping point: no new object types, screens, or capabilities on your own initiative — the next product step is real-world use, and v4-of-the-product gets scoped only after real calls are captured and the §12 questions are answered at Valence. That is separate from the *presentation layer*, which was deliberately reopened by `DESIGN-GUIDE.md` and is now done. Design/visual refinements that honor the guide and the trust boundaries are fine; new product features are not.

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

# Tests (from backend/) — 67 tests, all green
.venv/bin/python -m pytest

# Frontend dev (from frontend/) — Vite on :5173, proxies API to :8000
npm run dev
npm run build                             # emits frontend/dist, served by the API in prod-ish mode
```

- DB path override: env var `VALENCE_OS_DB`; default file `valence_os.sqlite`.
- Migrations live in `backend/migrations/` as numbered `NNNN_*.sql`. The runner in `app/db.py` applies any file whose version isn't in `schema_migrations`. **Every schema change is a migration — no manual DB surgery.** Latest is `0010_source_reference_tags.sql`.
- Git: commit as `git -c user.name='Sam' -c user.email='noreply@example.test' commit`, trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`, then `git push -q origin main`. Private repo `github.com/GBB94/valence-os`, `gh` authed as `GBB94`.

## What's built (by module → doc section)

Backend routers in `backend/app/routers/`, frontend views in `frontend/src/views/`. Migrations 0001–0010.

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

- **Job table + in-process worker (§7/8).** Deliberately not built. At this scale (a few thousand rows) all work is synchronous and instant; a queue would be speculative infrastructure the doc's "keep it boring" rule forbids. Do **not** build the job table or any §7/8 production-mode machinery.
- **Real Claude-API extractor.** The `api` backend in `app/extractor.py` is dormant on purpose. The build order puts AI *after* enough real manual capture to know the true extraction schema, and §12 decision #3 (may AI call an external LLM?) is still open. **Do not wire any external API or key. The mock extractor stays mock** until Zach re-opens this after real capture.
- **Polish pass.** Explicitly declined for now — don't spend a session on cosmetic refinement unasked.
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
6. **Frozen scope.** New object types or fields outside `stage-0/field-dictionary.md` require asking Zach first (the bar: retire an existing object or show evidence from real use). The `tags` field added 2026-07-29 was individually approved; that approval does not generalize.
7. **Slice discipline.** Build one self-contained slice, then stop for review. An earlier session was corrected for "building ahead" without per-slice approval — do not repeat it. Right now the correct move is to **not build** absent a new instruction.

## Where to look

- `Valence-OS-Scoping-Doc.md` — source of truth (frozen, v3.2).
- `CLAUDE.md` — standing rules (restates the binding constraints).
- `decisions.md` — decision log, newest first (D-59 is the tags slice).
- `README.md` — living project tour + run instructions + build-status table.
- `stage-0/field-dictionary.md` — the allowed object/field set; the fence for invariant #6.
