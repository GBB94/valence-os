# Stage 16 — the account drop zone — verification (2026-08-06)

**There are no captures in this folder, and that is the finding.**

Every other stage in `design-screenshots/` carries a both-theme pair because `CLAUDE.md` requires
one: *"a change that only works in one theme is not done."* Slices 1–3 of `ACCOUNT-INTAKE-SPEC.md`
shipped without that pair. This file records why, what was done instead, and what is therefore still
unverified — rather than leaving an empty folder that reads as an oversight, or a claim of visual
verification that was never performed.

## Why there are no captures

Capture is blocked at the environment's capture layer, not in the app. Established by probe:

1. `browser_open_local_preview` first rejected a page written to the session scratchpad —
   *"File is not under any active workspace root."*
2. Moved to `.scratch/probe.html` inside the workspace, the preview opened normally.
3. `browser_screenshot` against that trivial static page failed with *"Current display surface not
   available for capture."*

A page with no application code, no theme, and no JavaScript fails identically. The failure is
therefore not attributable to the drop zone, the dev server, or anything Stage 16 changed. The
probe file was removed afterwards.

## Compensating verification that was performed

Not a substitute for the captures. Recorded so the next session knows what it does not have to
redo, and what it does.

- **Token audit.** Every token used by the new CSS is defined in **both** theme blocks of
  `tokens.css`: `--bg-surface`, `--bg-sunken`, `--line-hairline`, `--line-strong`,
  `--shadow-control`, `--ink-primary`, `--ink-secondary`, `--font-mono`, `--t-micro`. No raw hex and
  no arbitrary pixel values were introduced.
- **Non-chromatic state.** The citation mark carries three signals — a border, a background shift,
  and an inline label — none of which is colour alone. It renders as a mark in a monochrome
  rendering.
- **Suites.** 795 backend, 256 frontend, clean `npx vite build` (Slices 1–4).

## What is still unverified, and needs the captures

- Rendered contrast at 4.5:1 for the citation mark against both surfaces, measured rather than
  reasoned about.
- The split view at a narrow viewport — whether the source pane and the proposal list stack or
  scroll, and whether the marked passage stays in view when they do.
- Focus-visible treatment on the drop target and on the accept-all control.
- That a long retained document's scroll container does not push the page into horizontal overflow.

## Surfaces to capture when the environment allows

| Surface | Both themes |
| --- | --- |
| Drop target on the Operate lens, idle and mid-drag | required |
| Drop receipt naming a duplicate and its earlier drop | required |
| `ProposalReview` split view — marked passage located, exact match | required |
| The same with a degraded citation: `deleted`, `never_captured`, and unlocatable | required |
| Accept-all bar in its offered state, and blocked with the reason | required |
| Narrow viewport (620px) for the split view | light is sufficient |
