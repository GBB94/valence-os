# Stage 16 — the account drop zone — verification (2026-08-06)

Eleven captures, both themes, plus one narrow viewport. **Two rendering defects were found by
capturing and both are fixed** — which is the argument for doing this rather than reasoning about
it, since neither was visible in the tests, the token audit, or the DOM.

## Correction to the previous version of this file

The earlier version of this file said there were no captures because capture was *"blocked at the
environment's capture layer."* **That was wrong.** The failure was the tool, not the environment:
`browser_open_local_preview` cannot be screenshotted (*"Current display surface not available for
capture"*), but `browser_open_session` with `headless: true` captures normally. Every image in this
folder came from a headless session against the running dev server. Nothing about the environment
had to change.

The mistake mattered, so it is worth naming: a blocked capture was recorded as a fact about the
world when it was a fact about one code path, and that reading is what kept the pair unwritten.

## What was found

**1. `Accept all 3` lost its count.** The accept-all control rendered as `Accept all` — the number
was simply absent. `.btn` sets a fixed `height` and `overflow: hidden` (the latter for the `::after`
sheen), and with `white-space` unset the label wrapped to a second line that was then clipped:
`clientHeight: 24, scrollHeight: 32`. A control that states how many records a command touches must
not be able to drop that number. Fixed with `white-space: nowrap`; that turned it into a 3px
horizontal clip under flex pressure, fixed in turn with `flex-shrink: 0`.

**2. The grounding split view never stacked, and broke a hash one character per line.**
`ACCOUNT-INTAKE-SPEC.md` §11.2 requires the split to stack "rather than shrinking into two
unreadable columns," and the CSS had a rule for it — but as `@media (max-width: 60rem)`, against the
*viewport*. `ProposalReview` renders both full-width on the Ledger tab and inside a 480px slide-over,
so on a 1440px viewport the breakpoint read 1440px while the actual column was 391px and never
fired. The 12rem label track then left the value column **7px** wide, and `overflow-wrap: anywhere`
— which is correct, a `sha256:` digest has no break opportunity — turned the content hash into a
1136px-tall column of single characters. Both breakpoints are now `@container` queries against the
box that actually constrains the layout: `.proposal-review` for the split, `.proposal-facts` for the
fact rows (inside the split it only gets half the pane, so the review's width is the wrong number to
ask about).

Both branches measured after the fix:

| `.proposal-review` width | split columns | fact row | `dd` |
| --- | --- | --- | --- |
| 1284px (Ledger tab) | `608px 608px` | `192px 408px` | 408 × 16 |
| 443px (slide-over) | `391px` — stacked | `1fr` | 391 × 16 |

## Captures

| File | Surface |
| --- | --- |
| `dropzone-{light,dark}.png` | Drop target on the Operate lens, at rest |
| `dragover-{light,dark}.png` | Mid-drag — accent border **and** the label changes to "Drop to add to …" |
| `review-{light,dark}.png` | `ProposalReview` slide-over: `Accept all 3`, spans quoted, `Cited` marks |
| `duplicate-{light,dark}.png` | Duplicate receipt naming the earlier drop and offering its drafts |
| `citation-deleted-{light,dark}.png` | Split view with a degraded citation — source deleted |
| `dropzone-narrow-620-light.png` | 620px viewport |

## Measured, not reasoned about

- **Contrast, both themes, all ≥ 4.5:1.** Primary ink 15.98 (light) / 16.44 (dark); secondary ink
  4.81 (light) / 5.71 (dark) — the floor across the drop zone label and hint, the grounding heading,
  filename and note, and the fact-row `dt`/`dd`.
- **No horizontal overflow** at 1440px or 620px, before or after the split fix.
- **No clipped controls** across 8 routes × 2 themes (94–118 buttons per page): every
  `scrollWidth ≤ clientWidth` and `scrollHeight ≤ clientHeight`.
- **Focus-visible** rules present — the global rule at `index.css:413`, and `.intake-zone`'s own.
- **Keyboard and ARIA on the drop zone**: `role="button"`, `tabIndex={0}`, an `aria-label` naming
  the account, `aria-busy` while sending, and Enter/Space opening the file picker.
- **Degraded citation marks nothing.** With the source deleted, the pane shows the heading, the
  filename and a server-authored sentence, and renders **no** `<mark>` — the span is degraded, not
  removed, and nothing arbitrary is highlighted.
- **State is never colour alone.** Receipt outcomes are text (`DRAFTED`, `ALREADY DROPPED`); the
  drag state changes the label as well as the fill.
- **Suites after the fixes:** 256 frontend, `npm run lint` exit 0, clean `npx vite build`. The
  changes are CSS-only.

## Not captured

- `never_captured` and unlocatable citations. `deleted` is captured and the three share one render
  path, differing only in the server-authored heading and note — but that is an argument, not a
  capture, and it is recorded here as one.
- The 620px viewport for the split view specifically. The split's stacking is now measured directly
  at 391px, which is narrower than the 620px case would produce.
