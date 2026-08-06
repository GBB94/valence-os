# Stage 15 (RR-0/RR-1) — rendered verification

Captured live against the seeded mock account `acc-terravance` (three programs in `programmatic`,
`launch`, and `expansion`), served from `frontend/dist` by the backend. Both themes are first-class,
so each surface is captured in both.

| File | Surface |
| --- | --- |
| `readiness-compact-light.png` | Compact card in the command center's Operate lens, light |
| `readiness-compact-dark.png` | Same, dark |
| `readiness-detail-light.png` | Pillar detail slide-over (`active_expansion_plan`, `thin`), light |
| `readiness-detail-dark.png` | Pillar detail slide-over (`budget_owner`, `met`), dark |

## What the captures confirm

- **No composite score anywhere.** No grade, no percentage, no "n of m" count — in either mode.
  The card footer states the six conditions are independent.
- **No state by colour alone.** Every state pairs its colour with a mark *and* a word: `met` is a
  filled dot + "Met", `thin` a hollow ring + "Thin", `unknown` a slashed circle + "Unknown",
  `conflicted` a square + "Conflicted", `not_applicable` a flat neutral dash. The conflict mark is
  a square rather than a filled circle specifically so it is not read as a risk band.
- **Program scope is visible, never merged.** Each row names its program (`Europe Deployment`,
  `Global Coaching Rollout`, `Seat Expansion`); the two account-scoped pillars read `Scope: account`
  in the detail. The same pillar appears once per program with different states, which is the point.
- **Freshness is separate from state.** The detail head shows `Met` and `current` as two signals,
  and each component carries its own `current · 2026-07-12` chip against its own window.
- **Evidence is named, and provenance is labelled not coloured.** Every `met` component lists the
  records that decided it, each tagged `operator recorded` / `confirmed source`; `unsupported`
  renders dotted rather than in a status colour, because provenance is not business state.
  **Correction (2026-08-05):** this bullet previously said the component *links* those records. At
  the time of these two captures it did not — `Readiness.jsx` rendered each item as a plain `<li>`,
  and §5.3's drill-through to the native record was unbuilt. The screenshots always showed a plain
  list; the claim was wrong, not the capture. **The drill-through has since been built** (D-162);
  the captures for it are the section below, and `readiness-detail-*.png` above remain the pre-
  drill-through state.
- **Truncation has an escape hatch.** The compact cap is three; the "7 more" is an accent affordance
  opening the full in-scope set, so the cap is a presentation choice and not a filter on what exists.
- **A suggestion is not a task.** The detail footer reads "Suggested — not created", so a proposal
  never looks like accepted work already on someone's list.

## Not covered here

Keyboard tab-through and a measured contrast audit were not re-run for this stage; the components
reuse the existing `SlideOver`, `.card`, `.age`, and `rowActivation` primitives whose focus and
contrast behaviour was audited in earlier stages. The new CSS adds no colour of its own beyond the
existing status and accent tokens.

---

# RR-2 — proposed updates (2026-08-05)

Captured at 1440×1200 against the seeded database (`acc-northwind`, all programs), which holds one
real mock extraction run over the seeded kickoff interaction: 5 proposals plus 1 untriaged capture
note. Files: `rr2-preview-light.png`, `rr2-preview-dark.png`, `rr2-review-light.png`,
`rr2-review-dark.png`.

## What the captures show

- **Proposed updates card, Operate lens.** It sits directly below Relationship readiness, and that
  order is deliberate: a draft nobody has accepted is not an account condition and must not read
  like one. Three cards, the source line `From transcript · 2026-06-30 · mock extractor`, the count
  on the button reporting the whole scope (`Review all (5)`), and `2 more waiting in this scope.`
- **Nothing on the card decides anything.** There is no accept, reject, or resolve control — a
  decision needs the match candidates and the conflict preview beside it, and those live on the
  review surface. The footer says so: "Drafted from a source and waiting on a person. Nothing here
  has been applied."
- **Proposed-and-cited, never asserted.** Every proposal carries two marks with words, not colour:
  `Proposed` on a new dashed `.state-mark.draft` and `Cited` on a muted `.quiet`. Neither borrows a
  status hue (green/amber/red are account status) nor the accent (which is for interaction, and
  "Proposed" is a condition). Each quoted span renders in a dashed-left-border block.
- **The combined review keeps two vocabularies and two command sets.** The slide-over lists the 5
  proposals (`proposed` · `accept · edit and accept · reject · use existing · supersede`) and the 1
  capture note (`untriaged` · `Your capture note` · `Your Note` · `convert · dismiss`) in one
  newest-first list. The note carries no span and no `Cited` mark. Nothing was copied between the
  two stores to produce this view.

## Measured

- **Contrast**, computed-style walk over the 28 text nodes on both surfaces: light floor **5.44**,
  dark floor **5.12** (the `Review all` link in dark). Both clear the 4.5:1 quality floor.
- **No horizontal overflow** at 1440 (`scrollWidth === clientWidth`).
- Focus is the global `:focus-visible` outline; the card's link and the slide-over reuse the audited
  `SlideOver` and `.readiness-more` primitives rather than introducing new focus behaviour.

## Fixed during the rendered pass

- The card's own meta lines (`From …`, `N more waiting …`) sat flush to the card edge while the
  proposal rows were inset, because only `.proposal-row` carried padding. `.proposal-card > .rowmeta`
  now takes the card gutter.
- The source line printed its date twice — `sourceLabel()` already includes the interaction date and
  the component appended `fmtDate(...)` on top of it.

---

# §5.3 evidence drill-through (2026-08-05)

The piece RR-1 was missing: §8.3's "evidence opens the native record or source location", asserted
at §11.5 as "evidence links open the correct native target". Captured at 1440×1000 against
`acc-terravance`, all programs, on the `Champion continuity` pillar in the `Global Coaching Rollout`
scope — chosen because it is the only seeded pillar whose evidence spans two different destination
tabs. Files: `readiness-evidence-links-light.png`, `readiness-evidence-links-dark.png`.

## What the captures show

- **Every evidence record is now the link.** `stakeholder role Dana Okafor`, `advocacy event
  advocacy without us on 2026-06-28`, and `stakeholder role Lucia Moretti — Program owner` each
  render the record label as an accent `.linklike` button, with the kind still muted in front of it
  and the provenance chip still behind it. The accent is correct here and not a state colour: a
  link is interaction, which is exactly what the accent is reserved for.
- **The route is the server's, and it is explicit.** `readiness._EVIDENCE_TARGET` maps each of the
  eighteen routed kinds to a `(tab, subview)` pair beside `_ev()`, the single point where every
  evidence item is constructed. The client renders a button or does not; it never guesses a
  destination from a type name.
- **Three kinds deliberately have no route and read as plain text.** `account_field` and
  `program_field` name a column on a record the pillar has already identified — their id is
  `table.column`, not a record id — and `source_reference` is provenance attached to another record.
  They ship `native_target: null`, and a backend test asserts them *by name*, so an unrouted kind
  has to be a decision somebody wrote down rather than an omission.

## Verified live in the running app

Clicked through in the browser rather than asserted only in tests:

| Evidence | Lands on |
| --- | --- |
| `funding_pool` (Budget owner identified) | `/accounts/acc-terravance/commercial?section=funding`, **Funding** sub-tab active |
| `advocacy_event` (Champion continuity) | `/accounts/acc-terravance/people?section=champions`, **Champions** sub-tab active |

The People route needed the tab's sub-panel to become navigation state the way Commercial's already
was — otherwise a `champion_candidate` opened People and landed on its default Map, which is
"opens the tab that contains it", not §8.3. `navigation.js` validates `section` **per tab** rather
than against a merged set, so a Commercial section arriving on People is dropped rather than
round-tripped into a value that tab cannot render.

## Measured

- **Contrast** over the evidence list, computed-style walk in both themes: light floor **5.44**
  (the muted kind prefix and the provenance chip; `.linklike` itself is **8.51**), dark floor
  **5.12**. Both clear the 4.5:1 quality floor.
- **No new CSS.** `.linklike` already existed at `index.css:465` and is used elsewhere, so the
  drill-through adds no colour, no pixel value, and no focus behaviour of its own.
- **Keyboard.** The three evidence buttons are real `<button>` elements carrying no `tabindex`, at
  positions 1–3 of the slide-over's four focusable elements (after `Close`). `.linklike` clears
  `border` but not `outline`, so the global `:focus-visible { outline: 2px solid var(--accent) }`
  at `index.css:403` applies to them. This was confirmed by DOM inspection of the tab order and the
  computed outline, not by a hardware Tab — the browser tooling available here exposes no key-press
  primitive, which is the same limit recorded for Stage 12.
