# Stage 12 visual verification

Stage 12's account/portfolio Copilot panel and Operations surfaces are implemented, but no rendered
captures are claimed from this session. The required in-app browser connection was retried after the
closeout build and again reported no available browser session, so a both-theme screenshot or live
keyboard pass could not be run.

Executable validation completed instead:

- the production frontend build and lint pass;
- all 322 backend tests pass, including the executable 13-case replay/evaluation/activation/rollback
  path, zero-tolerance activation refusal, scoped retrieval, reviewed cursors, aliases/fuzzy
  candidates, bounded follow-ups, retry/dedupe, stale/private evidence, immutable provenance,
  correction review, preview-only drafting, audience/style rejection, export/restore, and
  decomposed release gates;
- the panel statically contains an explicit scope chip, dialog labeling, Escape handling, a focus
  trap, focus return, a frozen-field source drawer, canonical navigation, saved runs, feedback,
  explicit cursor advance, the interpreted change window, and preview-before-save internal drafting;
  and
- Operations renders the Stage 11 portfolio learning endpoint plus Copilot mode, run states,
  thresholds, active/versioned configurations with activation/rollback controls, the append-only
  correction queue, and style versions.

Still required when an in-app browser is available:

1. capture account Q&A, conflicted/disambiguation, what-changed, weekly, and Operations views in both
   light and dark themes;
2. tab through the panel, verify focus never escapes the modal, press Escape, and verify focus returns
   to the invoking control (including cmd-K invocation); and
3. open a claim source and verify navigation reaches the correct account workspace surface at a
   narrow split-screen viewport.
