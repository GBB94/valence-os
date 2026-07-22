# Seed data — three mock accounts

All names, people, and figures are **fictional**. No real client data anywhere (CLAUDE.md data rule). Email domains use `.test`.

| File | Account | Programs | Notable state (as of today = 2026-07-22) |
|---|---|---|---|
| `valence-team.yaml` | — | — | 3 internal Valence people (used as internal owners) |
| `terravance.yaml` | Terravance Agricultural Systems | **3** (Global, Europe, Expansion) | multi-program; Europe blocked on works council; overdue cohort-summary commitment; expansion 1k→3k as a Program (see G1) |
| `northwind.yaml` | Northwind Financial Group | 1 (Advisor pilot) | overdue client nomination commitment; open SSO task |
| `bluepeak.yaml` | Bluepeak Health Systems | 1 (Foundation) | early phase; champion stale >21 days |

## What each seed exercises

- **Multi-program account** — Terravance (required).
- **Both account statuses diverging** — Terravance is delivery `on_track` but commercial `at_risk` (the exact "excellent adoption, weak expansion economics" story from Section 4).
- **Attention queue** across accounts: an overdue commitment (Terravance + Northwind), an active blocker (Terravance Europe works council), an at-risk milestone (Terravance Europe go-live), a stale champion (Bluepeak), open tasks (Northwind, Bluepeak).
- **Trust boundary respected** — nowhere is there a field for a named person's product usage; the cohort-summary commitment is explicitly *aggregate*.
- **Two-owner commitments** — client-owned commitments (Northwind nominations) still carry a Valence internal owner.

## Loading

These are Stage-0 paper artifacts. The v0 dev seed/reset command (built later) will load equivalents through migrations; the YAML here is the source of truth for that seed and for the walkthroughs and acceptance test.

## Fictional-data checklist
- [x] No real company names
- [x] No real people
- [x] No real figures (seat counts are illustrative)
- [x] No real transcripts or documents (links are `example.test`)
