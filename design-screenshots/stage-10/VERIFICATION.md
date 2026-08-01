# Stage 10 visual verification

## Automated verification completed

- Frontend lint passes with no warnings in `Internal.jsx` or `PortfolioInternal.jsx`.
- The production frontend build completes successfully.
- All 238 backend tests pass, including generated-artifact, immutable-manifest, bidirectional no-surprises,
  account-scope, lock/submission, escalation-snapshot, coverage, feedback-loop, search, and
  export/restore acceptance paths.
- A clean temporary database applies migrations 0001–0030, loads the five-account mock seed,
  and returns no rows from `PRAGMA foreign_key_check`.
- A populated migration-0025 database upgrades through 0026–0030 without changing its account,
  person, or commitment row counts; `foreign_key_check` remains empty and `integrity_check` is `ok`.
- `Internal.jsx` and `PortfolioInternal.jsx` were mechanically reformatted after the external
  review; their maximum line lengths are now 116 and 97 characters respectively.

## Browser limitation

Both-theme interactive browser capture was attempted again after migration 0030 but could
not be completed because no in-app browser was attached to this workspace session. This is a
verification limitation, not a passing visual claim; no unrelated browser mechanism was used
as a substitute.

Before release, run the app locally and capture the following in both themes:

1. Account workspace → Internal → Forecast, including an unsupported Commit evidence treatment.
2. Internal → Asks, including a Commit-linked ask and its escalation chain.
3. Internal → Reviews, including governed red response fields and all three review generators.
4. Internal → Coverage, including role-scoped, 14-day coverage, and return brief controls.
5. Accounts → Internal → Overview, including the no-surprises blocker and typed exclusion flow.
6. Accounts → Internal → Forecast, Coverage, and Feedback, including a sourced occurrence.
7. Accounts → Portfolio analytics, confirming the Stage 9 route remains reachable.
