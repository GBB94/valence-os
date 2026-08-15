# Stage 11.2 visual verification

Captured 2026-08-02 against a fresh `app.seed --reset` database served by the one-process setup
(FastAPI on :8000 serving `frontend/dist`), viewport 1600×1100, both themes.

| # | View | Files |
|---|---|---|
| 1 | Draft campaign → "Have we run this shape before?" — prior evidence with the honest match reason | `01-campaign-prior-evidence-{light,dark}.png` |
| 2 | Completed campaign → "What we learned" — retrospective with the per-intervention verdict | `02-campaign-retrospective-{light,dark}.png` |

Capture 1 needed a draft to be its subject: §11.3 scopes nearest-campaign evidence to *a new draft*,
and the seed ships only an active and a completed campaign. A "Nordics review-cycle retry" draft was
created through the API in the screenshot database rather than widening the gate to suit the picture.

## What the captures are meant to show

- **The match lands at tier 3, not tier 1.** Both cohorts are untagged segments, so the reason reads
  "Same global use case; audience tags unavailable for one or both shapes." That is the D-94 rule
  visible in the product: an empty tag set is "we have used this feature before," never "we have run
  this exact shape before." A tier-1 match here would be the bug.
- **The retrospective disagrees with the diagnosis.** The campaign diagnosed *capability* and built a
  worked example; the retrospective records *opportunity* — there was no slot in the review cycle.
  The seed is written to show that gap rather than a clean success, because the gap is the reusable
  finding.
- **A failed intervention is rendered as failed.** The clinic's verdict is `appeared_not_to_help`, in
  the risk hue with the word, never colour alone.

## Still open

- Keyboard tab-through is not verified here; these are rendered captures, not an interaction pass.
- The portfolio learning view now renders in Operations. A new rendered capture was not possible in
  the Stage 12 session because the in-app browser advertised no available browser session.
