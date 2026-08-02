# Stage 10 visual verification

## Automated verification completed

- Frontend lint passes with no warnings in `Internal.jsx` or `PortfolioInternal.jsx`.
- The production frontend build completes successfully.
- All backend tests pass (266 at capture time), including generated-artifact, immutable-manifest,
  bidirectional no-surprises, account-scope, lock/submission, escalation-snapshot, coverage,
  feedback-loop, search, and export/restore acceptance paths.
- A clean temporary database applies migrations 0001–0031, loads the five-account mock seed,
  and returns no rows from `PRAGMA foreign_key_check`.
- A populated migration-0025 database upgrades through 0026–0031 without changing its account,
  person, commitment, decision, or generated-document row counts; `foreign_key_check` remains
  empty and `integrity_check` is `ok`.
- `Internal.jsx` and `PortfolioInternal.jsx` were mechanically reformatted after the external
  review; their maximum line lengths are now 116 and 97 characters respectively.
- The suite is timezone-deterministic: fixtures derive dates from the app's own UTC clock via
  `tests/conftest.py:utc_day()`, and the full suite passes at `Pacific/Kiritimati` (UTC+14) and
  `Pacific/Midway` (UTC−11) as well as locally.

## Both-theme capture — completed 2026-08-01

Captured against a clean seeded database (`app.seed --reset`) served by the one-process setup
(FastAPI on :8000 serving `frontend/dist`), viewport 1600×1100. The earlier sessions' browser
limitation no longer applied.

| # | View | Files |
|---|---|---|
| 1 | Account → Internal → Forecast, unsupported Commit and Best Case | `01-account-internal-forecast-{light,dark}.png` |
| 2 | Account → Internal → Asks, ask carrying an escalation | `02-account-internal-asks-{light,dark}.png` |
| 3 | Account → Internal → Reviews, governed red response fields and all three generators | `03-account-internal-reviews-red-response-{light,dark}.png` |
| 4 | Account → Internal → Coverage, roster plus call/coverage/return brief controls | `04-account-internal-coverage-{light,dark}.png` |
| 5 | Accounts → Internal → Overview, no-surprises blocker and report-eligible red origins with the typed-exclusion action | `05-portfolio-internal-overview-blocker-{light,dark}.png` |
| 6 | Accounts → Internal → Feedback, one theme across two accounts with loop counts | `06-portfolio-internal-feedback-{light,dark}.png` |

Capture 3 selects `off track` so the recovery owner / due / action / leadership-handling fields
the §1.3 response rule requires are visible; the assessment was not saved.

Capture 5 required a planted red: the seed ships no `off_track` account, so `acc-northwind` was
set to `commercial_status='off_track'` **in the disposable screenshot database only** — not the
dev database — to exercise the blocker.

Item 7 of the previous list (Stage 9 `Portfolio analytics` still reachable) is confirmed in
captures 5 and 6: the `Book · Portfolio analytics · Internal` segmented control is visible in
both, with all three destinations present.

## Two defects this pass found

Both were invisible to the test suite and appeared only once the screen was rendered.

1. **`.risk-text` was applied but defined in no stylesheet.** The unsupported-forecast evidence
   cell carried a class with no rule behind it, so an unsupported Commit rendered in default
   body text — no risk treatment at all, against the standing rule that state pairs colour with
   a shape or label. Replaced with an `.evidence-gap` treatment built from the existing
   `--status-risk` token and the existing `.state-mark` shape, so it picks up the dark-theme hue
   automatically (verified `#C0392F` light, `#E5645A` dark).

2. **Evidence named the missing rule as a machine key.** The column printed
   `budget_owner_engaged_30d, ask_date_in_period`. The checker already returns a written
   `explanation` per rule, so the UI now renders that ("Budget owner has a meaningful touch in
   the prior 30 days.") behind a `Missing:` prefix. §10.2 asks the treatment to name the missing
   rule; it now names it in the operator's language rather than the schema's.

## Still open

- **Keyboard tab-through is not verified here.** These are rendered captures, not an interaction
  pass. The enabling semantics (semantic tables, tokenised focus ring, real `button` elements)
  are in place and were reviewed statically, but a live tab-through across the Internal sub-tabs
  has not been performed.
- The no-surprises blocker card renders without a status treatment — heading and row are plain
  text, so it reads informational rather than blocking. Same class of defect as (1); left alone
  rather than widening this pass.
