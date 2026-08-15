# Account Path Slice 2 — rendered verification

Captured live against the seeded mock account `acc-terravance` in `All programs` scope (three
programs: `Europe Deployment` in `launch` and blocked, `Global Coaching Rollout` in `programmatic`,
`Seat Expansion` in `expansion`), served from `frontend/dist` by the backend. Both themes are
first-class, so each surface is captured in both.

| File | Surface |
| --- | --- |
| `operate-light.png` | Orientation band — Next best move + three program lanes, light |
| `operate-dark.png` | Same, dark |
| `groups-light.png` | Execution groups — latest interaction, You own, Waiting on customer, readiness, Next on account, light |
| `groups-dark.png` | Same, dark |
| `narrow-light.png` | 620px viewport — the path goes vertical and the state word returns to each step |

## What the captures confirm

- **One recommended move, and it says why.** The move is the band-1 unresolved blocker; the
  supporting line is the deterministic selection reason (`Risk is an unresolved blocker`), not a
  restatement of the title. No sparkle, no percentage, no ranking language.
- **Absent facts render as facts.** The move shows `No due date` explicitly; the gate items in
  `You own` show `No due date` and `Unassigned`. Nothing substitutes a program owner, and nothing
  is suppressed for having an empty owner or date.
- **No state by colour alone, anywhere in the path.** Every phase step pairs a symbol with the
  state word: `✓ complete`, `◆ current`, `○ not started`, `▲ blocked`, `— waived`,
  `— not applicable`, `? unknown` (cross-hatched). At full width, compact lanes hide the state
  *word* to fit, so the button carries `aria-label` from `phaseAria()` — the accessible name keeps
  the state and its reason even where the visible label is the symbol plus the phase.
  `narrow-light.png` shows the word returning at ≤1000px.
- **A blocked phase names its reason inline.** `Launch ▲ blocked` is followed by the blocker
  sentence in the risk tone, so the reader never has to hover to learn what is blocking.
- **No fabricated aggregate phase.** Three programs, three lanes, sorted urgent-first
  (`Europe Deployment` leads because it has a blocked step and an at-risk go-live). There is no
  account-level phase pill anywhere.
- **One action, one place.** `Fund the executive sponsor touch` and `Prepare for Europe go-live`
  appear under `From the latest interaction`; neither repeats in `You own`, and the move itself
  appears in neither group.
- **Source labels are distinct from provenance.** `From Jul 12 call`, `From Jun 28 meeting`, and
  `Program standard` render as a neutral pill; readiness `operator recorded` / `confirmed source`
  provenance keeps its own chip in the side column. Different name, different style, same row is
  possible without collision.
- **Execution coverage and readiness coverage are never merged.** `Relationship readiness` reports
  its own state — three `⃠ Unknown` pillars and the "Six independent conditions — no combined
  score" footer — from its own request. Coverage was `complete` for this capture, so no execution
  notice renders; the two notices are separate components and never fold into one claim.
- **Empty states are explicit.** `Waiting on customer` renders "No open customer wait — No customer
  responsibility is open for this scope", not a blank card.

## Audits run

- **Contrast, both themes, measured live** on `.path-step-reason`, `.path-step button`,
  `.path-step-state`, `.path-row-title`, `.path-row-reason`, `.path-row-meta`, `.path-source`,
  `.path-urgency`, `.path-move-reason`, `.path-move h2`, `.path-milestone`, `.path-gate-link`, and
  the section meta line. Range 4.80–18.08; the floor is the 11px blocked-phase reason at 4.80 and
  the section meta at 4.81. Nothing under 4.5.
- **Focus.** No rule in the Account Path CSS sets `outline`, so the global
  `:focus-visible { outline: 2px solid var(--accent) }` applies to every phase step, row action,
  `View all programs`, and the milestone and gate links. Confirmed the step buttons are reachable
  and take focus (18 of them in this scope).
- **Reduced motion.** The two transitions added by this slice (`.path-step button` and
  `.path-row` background) are covered by the existing global
  `@media (prefers-reduced-motion: reduce)` block, which forces `transition-duration: 0.01ms
  !important` on all elements. No new animation or transform was introduced.
- **Narrow width.** At 620px the orientation grid collapses to one column, the rail's divider moves
  from `border-left` to `border-top`, the step list stacks vertically, and row actions become
  40px-min touch targets. Verified by computed style, not by eye alone.
- **Tokens only.** No raw hex and no arbitrary pixel value in the ~130 lines of CSS this slice adds.

## Deliberate divergences from the spec, visible here

- **The "Needs action" list is gone, not moved.** It ranked the same overdue/blocked/due-soon
  records that `Next best move` and `You own` now rank from one deterministic ordering; keeping
  both would have put two competing orders of one record set on one screen (§3, §7.3).
- **The move title drops the house `h2` eyebrow styling.** The global `h2` in this codebase is a
  section eyebrow — uppercase, tracked, tertiary ink. Applied to a full sentence it read as a
  label rather than as the move, so `.path-move h2` keeps the heading semantics and takes primary
  ink at sentence case.
- **The phase filter narrows to gate items only.** Only a gate item carries a `phase`; a Task
  belongs to a program, not to whatever phase that program is in today. Selecting a phase says so
  in a callout rather than silently reassigning work.

## Not covered here

Component-level DOM tests. The frontend harness is `node --test src/*.test.js` over plain modules —
there is no React renderer, jsdom, or testing-library in the repo — so §11.11's presentation rules
were extracted into `frontend/src/accountPath.js` and covered by 15 tests there instead. Adding a
renderer to satisfy a checklist item is a larger change than this slice, and is not one this slice
should decide.

---

# Account Path Slice 3 — rendered verification

Captured live against the seeded mock account `acc-northwind`, program `Advisor Manager Coaching
Pilot` (`prog-nw-pilot`, phase `launch`), served from `frontend/dist` by the backend. Both themes
are first-class, so each surface is captured in both.

| File | Surface |
| --- | --- |
| `slice3-required-now-light.png` | `Required now` card — three current-phase gaps and the route out, light |
| `slice3-required-now-dark.png` | Same, dark |
| `slice3-requirement-panel-light.png` | Requirement panel — four axes, plan line, decision trail, controls, light |
| `slice3-requirement-panel-dark.png` | Same, dark |
| `slice3-exception-form-dark.png` | Governed decision form — kind, reason, expiry — nested over the panel |
| `slice3-waived-panel-dark.png` | The same requirement with a live waiver: state unchanged, revoke offered |
| `slice3-essentials-expanded-light.png` | `Show fewer` state — all five gaps plus the suppression disclosure open |
| `slice3-narrow-light.png` | 620px viewport — the card goes full width, nothing clipped |
| `slice3-focus-ring-light.png` | The focus ring on a full-bleed requirement row, drawn inside the card |

## What the captures confirm

- **A plan date never reads as a verdict.** `Overdue · due 2026-06-03` sits in the row beside
  `⃠ Unknown`; the panel's plan line says `Expected by 2026-06-03 — past its planned date` and
  names the playbook that scheduled it. The state chip is untouched by either. A requirement that
  was evidenced after its date says `evidenced after its planned date` instead of returning to the
  gap list.
- **Four axes, never three and never one.** The panel shows `State`, `Freshness`,
  `Evidence coverage`, and `Applicability` side by side, each with its own word and its own mark.
  There is no combined figure anywhere on the surface, and the card's footer says so outright:
  `Independent conditions, no combined score.`
- **A suppression is subtractive and it is reported.** With a waiver in force the requirement
  leaves `Required now` and appears under `▾ Not applicable and waived (1) — suppressed, not
  evidenced`. Its state stays `Thin` — the decision never promotes it — and the missing-evidence
  block reads "Nothing outstanding is being asked while the decision above is in force".
- **A governed decision is undoable and its history survives.** With a live waiver the panel drops
  `Mark not applicable` and offers `Revoke waiver`; after revoking, the trail shows
  `Waiver · Revoked` carrying both the original reason and the revocation reason, and the
  requirement returns to the gap list.
- **No control writes a state.** The panel's action row renders from `requirementControls()`, whose
  every entry writes either a native record or an exception. There is no status control on the
  surface, and `controlsWriteNoState()` asserts the absence in the test suite rather than leaving
  it to review.
- **A legacy tick is labelled a planning record.** Where a compatibility row exists the panel says
  `Marked complete … in the legacy checklist` followed by "That tick is a planning record, not
  evidence. Readiness still reports the state below."
- **Absent facts render as facts.** `Freshness: Not applicable`, `Not scheduled by a playbook`, and
  `Not reported` coverage all render as their own words. Nothing borrows the benign end of an enum.

## Audits run

- **Contrast, both themes, measured live** over every text node in `.req-essentials` and
  `.req-suppressed` (46 nodes), each against its own painted ancestor background. Light floor 4.81
  (the 11px card description); the `Overdue · due …` chips measure 5.43. Dark floor 5.53. Nothing
  under 4.5 in either theme.
- **Focus.** The global `:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px }`
  is the only rule in play — nothing in the Slice 3 CSS sets `outline`. Both new controls are
  natively focusable (`<button>` for the expander, `<summary>` for the disclosure). The audit did
  find the ring being clipped and that is fixed; see the defect list below.
- **Reduced motion.** Slice 3 adds no animation and no transition. The two that apply to the card
  are inherited from `.card` and `.btn`, and the existing global
  `@media (prefers-reduced-motion: reduce)` block forces `transition-duration: 0.01ms !important`
  on all elements — confirmed by reading the rule out of the live stylesheet, not by assumption.
- **Narrow width.** At 620px `document.scrollWidth` equals `innerWidth` — no horizontal scroll —
  and no descendant of the card overflows its box or clips its own content. The card goes full
  width, the gap rows stack, and the due chip wraps onto its own line where the row is too tight to
  hold it inline.
- **Tokens only.** No raw hex and no arbitrary pixel value in the CSS this slice adds.

## Defects this pass found, and the fixes

Live rendering caught five things the pure-module tests could not, three of them because the
component had drifted from the module the tests assert. Each is now covered by a test or by a
measured audit.

1. **`View all 5` was clipped against the card border.** In the ~365px aside the button shrank and
   wrapped into the header's own edge. The title block now absorbs the shrink
   (`flex: 1 1 14rem; min-width: 0`) and the route out never does (`flex: none; white-space:
   nowrap`).
2. **A bare red date carried the whole claim.** The compact row rendered `2026-06-03` beside a red
   mark, leaving the reader to infer from colour what kind of date it was — against the standing
   "no state by colour alone" rule. `planStatus()` now emits `due_label`
   (`Overdue · due …` / `Due …`) and a test pins both directions.
3. **The exception status vocabulary did not match the server, and it cost a control.**
   `exceptionHistoryRows()` mapped `active`/`expired`; `playbooks._exception_status` emits
   `live`/`revoked`/`lapsed`. A live waiver therefore read as unrecognised and *lost its revoke
   control while still suppressing the requirement*. The mapping is corrected, an unknown status
   now fails closed to `Status not recognized` and is never live, and a test reads
   `backend/app/playbooks.py` and asserts every status the Python emits has a label here — so the
   pairing cannot drift again silently.
4. **`View all N` routed to a dead end, and a suppressed requirement was unreachable.** The link
   went to a page that lists no requirements, and a recorded waiver could never be reviewed or
   revoked afterwards. The card now expands in place (`Show fewer`, `aria-expanded`), and
   `suppressedRequirements()` backs a `<details>` disclosure that is the route back to the decision.
5. **The focus ring was clipped on every full-bleed row.** `.card` sets `overflow: hidden`, so a
   row spanning the card's full width lost the vertical edges of its ring and kept only the
   horizontals. `.readiness-row.clickable:focus-visible` and the disclosure summary now use
   `outline-offset: -2px`, the same treatment `.company-event-focused` already uses, and the ring
   measures 3px inside the card edge on both sides. The fix lands on the shared row class, so it
   also repairs the readiness pillar lists that row came from.

Defects 1, 3, and 4 were possible because the panel hand-rolled its action row instead of rendering
`requirementControls()`. It renders from the shared module now, which is what makes the
"no control writes a state" test load-bearing rather than decorative.

## Not covered here

Component-level DOM tests, for the same reason as Slice 2: the harness is `node --test src/*.test.js`
over plain modules, with no React renderer or jsdom in the repo. The presentation rules live in
`frontend/src/requirementDetail.js` and are covered there. This pass is why that gap is worth
naming twice — three of the five defects above are exactly the class a renderer test would have
caught, and a pure-module test cannot.

---

# Account Path Slice 4 — rendered verification (2026-08-05)

Verified live against the running backend (`frontend/dist` served by FastAPI, migrations 0001–0045
applied) on the seeded mock account `acc-bluepeak`, using proposals produced by real extraction runs
over mock transcript and email fixtures. Both themes were audited by loading into each.

The PNGs were captured in a later session, after the headless screenshot path started working; the
audit text below predates them and was computed-style and DOM state read from the live page.

| File | Surface |
| --- | --- |
| `slice4-review-light.png` | Combined review surface — 3 proposals and 1 capture note in one list, each keeping its own status word and mark, light |
| `slice4-review-dark.png` | Same, dark |
| `slice4-decision-light.png` | A proposal's decision surface open — editable draft, reason field, the five commands, and the per-command "why" block, light |
| `slice4-decision-dark.png` | Same, dark |

## What was verified in the running app

- **One review surface, reached two ways.** The Overview card's `Review all (2)` opens the
  slide-over. Pasting a mock transcript into Ledger → *Extract from a transcript* and running the
  extractor rendered the same `.proposal-review` component below the form, with the run's two fresh
  proposals (`New risk`, `New task`) at the top of the account's pending list. The card itself
  resolves nothing — it has no accept, reject, or resolve control anywhere in its markup, and a scan
  of the whole page after the run found **zero** bare `Accept` / `Reject` buttons, i.e. no surviving
  legacy `mutation_type` row.
  *Observed scope note:* the run's proposals are not isolated from the account's other pending
  items — `sourceInteractionId` falls back to the account scope when the run carries no
  `interaction_id`, so the capture note and the earlier run's commitment appear in the same list.
  That is the combined read model working as specified, not a filter failing, but it is worth
  knowing before reading the screen as "what this run produced".
- **The two stores stay separate in one list.** The combined list rendered three rows: a capture
  note (`untriaged`, `Your capture note`, offering only Convert and Dismiss) alongside two
  extraction proposals (`proposed`, offering the full command set). Each side keeps its own status
  vocabulary and its own commands, as RR-2 requires — the read model composes them, it does not
  merge them.
- **A command is live only when it can succeed, and says why when it is not.** On the drafted
  commitment, `Accept as drafted` was disabled with `Needs Responsible party, Internal owner, Due
  date`; `Reject` with `Give a reason — the next reviewer reads it, not the proposal`;
  `Use existing record` with `Pick the record that already holds this`; `Supersede` with `No other
  proposal covers this material`. `Open source` was live, because a reviewer who cannot read the
  source cannot review. Every `aria-describedby` on a disabled button resolved to the matching id in
  the `.proposal-why` block.
- **Accepting writes once and drains the row.** `Accept as drafted` on the drafted risk toasted
  `Created risk`, removed that row from the list, and dropped the card's count from
  `Review all (2)` to `Review all (1)` behind the still-open slide-over.
- **The reviewer stays in the queue.** After the accept, `surfaceStillOpen: true`,
  `slideOverOpen: true`, and the two remaining rows were still on screen. Closing the slide-over
  afterwards re-rendered the command center with no error callout — the account refresh happens once,
  on close. (This is the defect D-148 records: before the fix the same check returned
  `surfaceStillOpen: false` after every single decision.)
- **`Open source` shows the record's own values and omits what it does not have.** Kind, Content
  hash, and Extractor rendered; Provider and Locator were absent rather than shown empty.
- **Match candidates render per check, not per record.** A duplicate proposal rendered two candidate
  radios sharing one target id under different `check` values — the reason the React key is
  `${check}:${id}`. `Use existing record` stayed disabled until one was chosen, then toasted
  `Closed against the existing record`.

## Both themes

Audited by reloading into each theme (`valence-theme` in localStorage), with a decision panel open
and `Open source` expanded, over every visible leaf text node inside the slide-over:

| Theme | Leaf nodes checked | Below 4.5:1 | Tokens unresolved |
| --- | --- | --- | --- |
| light | 37 | 0 | 0 |
| dark | 37 | 0 | 0 |

`.proposal-decision` resolves to `--bg-sunken` in both (`#eff1f4` / `#080a0f`) and the selected row's
leading rule to `--accent` (`#3a34c4` / `#7c74f0`). No raw hex or arbitrary pixel value was
introduced; the whole `.proposal-*` block is token-only.

**No state is carried by colour alone.** The accent rule on the selected row is *interaction*, not
state — the row's state stays in its words and its marks (`proposed`, `untriaged`, `Your note`), and
the marks render identically on the preview card and the review surface because both import the same
`Marks` component.

## Two environment traps, recorded so the next session does not misread them

1. **Flipping `data-theme` imperatively does not fully recompute styles in the headless engine.**
   `--ink-secondary` reported its dark value on the element while the element's computed `color`
   stayed at the light one, producing a false dark-theme contrast failure on `.btn.ghost`
   (2.99:1). Reloading into dark gives `rgb(162, 169, 182)` and passes. Audit a theme by loading
   into it.
2. **`:focus-visible` never matches in that session** — the offscreen window holds no focus, so
   `document.activeElement` is set while `el.matches(':focus')` is false. Focus-ring checks by that
   route are inconclusive, not failing. What can be asserted statically: the global
   `:focus-visible { outline: 2px solid var(--accent) }` applies to every button in the surface,
   every input/select/textarea sits inside `.field` and so takes the border+ring treatment, and the
   slice introduced no `outline: none` anywhere.

## Not covered here

Component-level DOM tests, for the same reason as Slices 2 and 3: the harness is
`node --test src/*.test.js` over plain modules, with no React renderer or jsdom. The decision rules
live in `frontend/src/proposalReview.js` and are covered there by 19 tests. Everything in the first
section above was found or confirmed by loading the app, not by the suite — including the
slide-over-closing defect, which a green suite of 75 tests did not see.

---

# Account Path Slice 5 — rendered verification (2026-08-05)

Captured live against the seeded mock account `acc-northwind`, program `Advisor Manager Coaching
Pilot` (`prog-nw-pilot`, phase `launch`), served from `frontend/dist` by the backend with migrations
0001–0046 applied. The fixture was built through the Slice 5 endpoints themselves — two phase gates
(a `launch` gate `Pilot launch readiness` with two items, a `programmatic` gate
`Programmatic expansion readiness` with one), gate→requirement links at both `required` and
`optional` necessity, action links at both `advances` and `follow_up_for`, and one reviewed
interaction evidence — so every surface below renders from records the API wrote, not from a seed.
Both themes are first-class, so each surface is captured in both.

| File | Surface |
| --- | --- |
| `slice5-gate-band-light.png` | Gate readiness band — verdict, every unmet condition named, `Advance to Programmatic`, light |
| `slice5-gate-band-dark.png` | Same, dark |
| `slice5-advance-override-light.png` | The blocked transition — the override path listing what it will *not* satisfy, light |
| `slice5-advance-override-dark.png` | Same, dark |
| `slice5-requirement-links-light.png` | Requirement panel — linked action, gate requirement link, evidence with its review stamp, light |
| `slice5-requirement-links-dark.png` | Same, dark |
| `slice5-tracked-disclosure-light.png` | `Tracked by a linked action` — the route back to a requirement the dedupe removed from the gaps, light |
| `slice5-tracked-disclosure-dark.png` | Same, dark |

## What the captures confirm

- **A gate verdict names conditions; it never scores them.** The band reads `blocked` followed by
  `1 required condition outstanding; 2 incomplete gate items` and then lists each one by name. There
  is no percentage, no "readiness score", and no bar. Partial coverage renders as
  `insufficient data`, which is a separate word from `blocked` — a gate that could not be evaluated
  never reads as one that was evaluated and failed.
- **An override accepts a gap without satisfying it.** `Advance anyway` records the transition and
  restates the unmet conditions in the history as still unmet. The requirement panels behind it are
  unchanged: the same states, the same freshness, the same coverage. Nothing about a phase move
  writes a readiness value, which is the point of `test_an_override_records_the_unmet_conditions_
  without_satisfying_them` and `test_waiving_a_gate_moves_no_phase_and_satisfies_no_requirement`.
- **An action advances a requirement without becoming evidence for it.** The linked Task appears
  under `Linked records` with its relation, and the requirement's state is untouched by the link.
  Attaching evidence of a kind the definition does not accept was tried live: it attached with
  `supporting: false` and the sentence "The requirement definition does not accept this kind, so it
  is on the record but cannot change the state." A count-based evaluator (`breadth_engaged_contacts`)
  stayed `thin` through a `supporting: true` attachment, because the count is the count.
- **`Unblocks the …` is the server's clause and appears exactly once.** The next-best-move reason
  reads `Commitment is 21 days overdue and needs an internal follow-up · Unblocks the Launch gate
  "Pilot launch readiness"`. The client no longer appends its own copy (D-149), and the clause is
  claimed only from an explicit `required` gate link — an `optional` link renders no such phrase.
- **Timeline dependencies come only from explicit links.** The secondary band under the chart shows
  `Dependencies` / `Blocks` with the linked record named and the note beneath, plus the standing
  line "Explicit relationships only. Nothing here is inferred."
- **A tracked requirement stays reachable.** The dedupe correctly drops a linked condition from
  `Required now` — the work is the Task's — and the `Tracked by a linked action (n)` disclosure is
  the route back to the panel that manages its evidence and gate links. It reads as a disclosure,
  not a queue: the gap list above it is unchanged by its presence.

## Audits run

- **Contrast, both themes, measured live** over every visible leaf text node in `.path-verdict`,
  `.path-history-card`, `.req-essentials`, `.req-tracked` (130 nodes) and in the open requirement
  panel `.req-detail` plus the expanded disclosure (102 nodes), each against its own painted
  ancestor background, and over the timeline `.path-deps-band` (7 nodes) on the Plan tab. **Nothing
  below 4.5:1 in either theme.** Light floor 4.81 (the 11px axis labels and card description);
  dark floor 5.12 (the 12px `.path-gate-link`). The `Advance to Programmatic` primary button
  measures 5.32 in dark.
- **Themes were loaded, not toggled.** Per the trap recorded in the Slice 4 section, each theme was
  entered by writing `valence-theme` and reloading, so the computed `color` and the token both
  reflect the theme actually in force.
- **No state by colour alone.** The verdict pairs its word with a symbol (`.path-verdict-symbol`);
  the gate link renders as a named link rather than a coloured chip; the tracked disclosure carries
  its meaning in the summary sentence, not in its rule.
- **Tokens only.** The CSS this slice adds introduces no raw hex and no arbitrary pixel value.
- **Suites.** 584 backend tests green (37 of them `test_account_path_slice5.py`), 103 frontend tests
  green.

## Two defects this pass found, and the fixes

Both were invisible to the suites and were found by loading the app — the same class of defect the
Slice 3 pass recorded, and for the same reason.

1. **Linking an action made a requirement unreachable.** `execution_path._requirement_row` excludes
   a linked requirement from `current_phase_gaps` on purpose (§13.6 — the work belongs to the
   record). But `AccountEssentialsGaps` is the only mount of `RequirementPanel`, and it lists only
   the gaps. The moment a requirement became tracked it lost the one surface that can add evidence,
   link a gate, or revoke a decision. `trackedRequirements()` and the `.req-tracked` disclosure are
   the route back, with a test that pins both halves: the tracked row is listed, and the gap list is
   *unchanged* by the disclosure — it must not become a second queue.
2. **`Linked records` rendered a bare "record" bullet with a dead button.** `linkedRecords()` read
   `record_type` / `label` / `native_target`; the server ships `{type, id, description}` and no
   target of its own, because the link is the §13.6 dedupe index entry rather than a queue row. The
   function now builds the target from the two fields that do arrive, and an unroutable kind renders
   as plain text instead of a control that navigates nowhere. A test pins the shipped shape.

A third, smaller one: `⊘interaction` in the evidence list ran together, because the mark sits
immediately before the kind word with no whitespace node between the elements. `.req-evidence > li >
.state-mark` now carries its own margin.

## Not covered here

Component-level DOM tests, for the same reason as Slices 2–4: the harness is
`node --test src/*.test.js` over plain modules, with no React renderer or jsdom in the repo. Both
defects above are exactly the class a renderer test would have caught and a pure-module test cannot
— which is now the third consecutive slice to say so.

---

# Account Path Slice 6 — rendered verification (2026-08-05)

Captured live against the seeded mock account `acc-terravance`, served from `frontend/dist` by the
backend with migrations 0001–0049 applied. The scene comes from `seed._seed_shared_plan_demo`, which
builds it through the app's own code paths — `playbooks.instantiate`, `path_links.link_action`,
`path_links.link_milestone_action`, and the promotion columns the router writes — so the seed cannot
produce a state the app would refuse. It deliberately leaves work unpromoted and promotes one
requirement whose readiness is `unknown`, because both halves of §16 are only legible together.
Both themes are first-class, so each surface is captured in both.

| File | Surface |
| --- | --- |
| `slice6-plan-light.png` | The customer's document — programs, milestone groups, agreed conditions, light |
| `slice6-plan-dark.png` | Same, dark |
| `slice6-diagnostics-light.png` | The operator's document — unshared counts, withheld with reasons, source manifest, light |
| `slice6-diagnostics-dark.png` | Same, dark |
| `slice6-preview-light.png` | The §16.4 promotion preview, opened from the ledger before anything is shared, light |
| `slice6-preview-dark.png` | Same, dark |

## What the captures confirm

- **The two documents never read as one surface.** Everything above `Not on this plan` is what a
  customer would see. The diagnostics card is inset on `--bg-sunken` behind a dashed rule and
  carries the words `Internal — never rendered into the shared document` in its own header. No
  count, reason, or manifest line from it appears above it.
- **Promotion is the only route in.** The Europe program shows exactly the two items the seed
  promoted, grouped under `Europe go-live`; the diagnostics card states `2 tasks and 5 requirements
  not on this plan.` The unpromoted work is absent from the artifact rather than greyed out in it.
- **A requirement reaches a customer only under a label written for one.** The shared condition
  reads `Budget owner confirmed in writing` — the internal wording (`Evidenced budget authority`)
  appears nowhere in the artifact. Its support line reads `Tracked by shared plan items`, which is
  the §16.3 client-visible source, not the readiness provenance.
- **A refusal is stated, not hidden.** `Executive sponsor confirmed` was promoted by an operator and
  is withheld, and the diagnostics card says why: `Held back because no readiness reading is
  available in this scope.` Nothing about it — not the label, not the fact of the promotion —
  reaches the artifact.
- **`Other agreed work` is not a milestone and carries no status.** The bucket ships
  `client_status: null`, and the view renders no chip there. An unknown treatment would have claimed
  something could not be read when there was never anything to read.
- **The preview is the artifact, not a second rendering of it.** Opening `☆ Add to mutual plan` on an
  unshared commitment shows `Would appear as` over the five fields that would travel, followed by
  `Nothing else from this record travels. Notes, internal reasoning, evidence, and commercial detail
  stay where they are.` The label field is absent here on purpose: §16.3 requires a rewritten label
  for a *requirement*, whose internal wording is written for us; a commitment's description is
  already the shared text.

## Audits run

- **Contrast, both themes, measured live** over every visible leaf text node in `.plan-header`,
  `.plan-purpose`, `.plan-body`, and `.plan-diagnostics` (102 nodes each pass), and over the
  promotion slide-over (17 nodes each pass), each against its own painted ancestor background.
  **Nothing below 4.5:1 in either theme.** Plan light floor 4.81 (the 11px diagnostics `rowmeta`);
  plan dark floor 5.32 (the `Save as draft` primary button). Slide-over light floor 5.44, dark floor
  5.32 (`Confirm and share`).
- **Themes were loaded, not toggled.** Per the trap recorded in the Slice 4 section, each theme was
  entered by writing `valence-theme` and reloading. Setting `data-theme` on the root directly does
  *not* work here — `App.jsx:48` owns the attribute from its own state and overwrites it.
- **No state by colour alone.** Every status renders a mark, a symbol, and a word
  (`✓ Complete`, `◦ In progress`, `▲ Blocked`, `· Not started`, `– Not applicable`), pinned by a
  frontend test asserting all five pairs are distinct.
- **Tokens only.** The CSS this slice adds introduces no raw hex and no arbitrary pixel value.
- **Suites.** 621 backend tests green (37 of them `test_account_path_slice6.py`), 117 frontend tests
  green.

## Four defects this pass found, and the fixes

The first three were invisible to the suites and were found by loading the app — the fourth was
found by a test written to pin a contract the first three suggested was worth pinning.

1. **The stamp line printed `[object Object]`.** `summary.next_milestone` is the projected milestone
   dict, not a string. `stampLine` now reads `.name` and `.target_date`, and a test asserts the
   rendered line does not match `/\[object Object\]/` — the shape, not just the value.
2. **`Other agreed work` rendered `? Unknown`.** That group legitimately carries no status, and
   `statusChip(null)` correctly falls through to the unknown treatment. The fix was at the call
   site: the view guards on `group.client_status` rather than weakening the chip's honest default.
3. **`Held back because it no readiness reading is available in this scope.`** The server's reasons
   were a mix of clause shapes and the view supplied a linking `it`. Both halves were wrong. The
   reasons are now normalized on the server so each completes `held back because …` on its own, the
   view's sentence frame moved into `sharedPlan.withheldSentence` where a test can hold it, and a
   backend test asserts every reason is lower-case, unpunctuated, and at least four words.
4. **A test that asserted nothing.** The original shape test ended
   `assert f"Held back because {reason}."` — an f-string is always truthy, so it passed on any
   input. Replacing it with a real assertion immediately failed on `it is pinned to a retired
   requirement definition`, which turned out to be *correct* prose that my replacement rule
   mis-forbade. The rule, not the data, was wrong.

Three legacy tests also needed updating: §16.5 replaced the flat MAP `items` list with a grouped
artifact, so `test_stage75_growth_renewal.py` (×2) and `test_phase3_stage8_connections_demo.py` now
read `["artifact"]["markdown"]` and `["artifact"]["growth_lines"]`. The assertions' intent is
unchanged — both still check that internal reasoning stays out of the shared text.

## Not covered here

Component-level DOM tests, for the same reason as Slices 2–5: the harness is
`node --test src/*.test.js` over plain modules, with no React renderer or jsdom in the repo. Defects
1 and 2 above are exactly the class a renderer test would catch and a pure-module test cannot —
which is now the fourth consecutive slice to say so. Defect 3's fix is the partial mitigation
available without one: move the string into a module the harness *can* reach.

---

# Account Path Slice 7 — rendered verification (2026-08-05)

Captured live against the seeded mock accounts, served from `frontend/dist` by the backend with
migrations 0001–0050 applied. Slice 7 has two surfaces in different places: the measurement and
rule-comparison cards live in **Operations**, and the only Account Path change is the coverage
notice, so the path captures here are the narrow breakpoint where that notice sits under the header.
Both themes are first-class, so each surface is captured in both.

| File | Surface |
| --- | --- |
| `slice7-measurement-light.png` | Operations at 1440px — local diagnostics, funnel, per-reason table, rule registry with a live comparison, light |
| `slice7-measurement-dark.png` | Same, dark |
| `slice7-narrow-light.png` | Account Path at 620px on Terravance — the coverage notice and the stacked groups, light |
| `slice7-narrow-dark.png` | Same, dark |

## What was verified in the running app

The unit tests can only show that a counter increments when told to. What matters is that the
sixteen §17.3 events fire from the places the spec names, so this was driven by clicking and read
back from `/api/telemetry/funnel` between clicks rather than asserted in a fixture.

- **Views are counted, and views *with a next move* are counted separately.** After opening the
  Operate lens across the seeded accounts the funnel read `views 19`, `views_with_next_move 14`.
  The gap is the honest one — Harborline and Summit have no candidate at all — and it is the reason
  the two are distinct counters rather than one: a completion rate over all views would be diluted
  by accounts that were never offered anything.
- **Opens and snoozes carry the reason code they were ranked by.** Opening the promoted move on one
  account and snoozing it on another produced `by_reason_code` rows of exactly
  `overdue_operator_task` opened 1 and `operator_blocker` snoozed 1. The code travels from the
  server's ranking to the event, so the per-reason table is reporting the band that actually fired,
  not a client's guess at one.
- **`views_with_incomplete_coverage` is a first-class counter and read 0.** Zero here is a real
  reading, not a missing one — see the honest gap below.
- **Every event carries the ranking rule version.** `rule_versions` reported all 21 events under
  `v1-2026-08-04`. Without it the funnel would silently mix two orderings' numbers.
- **The kill switch says what it does.** The button reads `Disable and delete collected events`
  rather than a bare toggle, because §17.4 discards what was collected when measurement is turned
  off, and a user should not have to discover that afterwards.
- **The §17.5 caveat is on screen, not only in the payload.** It sits under the funnel where the
  numbers are: counts describe use, not recommendation quality, and a click-through rate cannot
  answer whether the recommendation was correct.

## The rule comparison, and an honest gap

`v2-candidate-notice-first` lifts `contract_decision_window` from band 4 to 3 and drops overdue
operator work from 3 to 4, on the argument that a notice date cannot be recovered once missed. The
comparison builds each account's path twice and diffs the ordering; it never selects a ruleset,
which is the `VALENCE_OS_RANKING_RULES` flag, deliberately outside the app so an ordering change is
a deployment decision rather than a click.

**Against the seed as it ships today, the comparison correctly reports `0 of 5 accounts reorder`,
and the reason is elapsed time, not a defect.** Terravance is the only account with a contract, its
renewal is 2026-11-15, and its earliest lead window opens at `renewal − procurement_lead_days` =
2026-09-06. Today is 2026-08-05, so no seeded account currently carries a
`contract_decision_window` candidate, and a band change that only affects that reason code has
nothing to move. From 2026-09-06 the same comparison starts reporting differences with no code
change.

The captured screenshots show the populated table instead, produced by recording an operator
overlay through the app's own route — `POST /api/contracts/ct-tv-current/overlay` with an expected
decision date of today — which is the §10 operational reading an operator would record for exactly
this situation and leaves the canonical `renewal_date` untouched. That produced a real 3-row
reorder on Terravance: `contract_version:ct-tv-current` 5 → 3, and the two overdue commitments 3 → 4
and 4 → 5. **The overlay was reverted afterwards** to the seeded values (`2026-10-01`, the
procurement-lead rationale), so the database matches `stage-0/seed-data/terravance.yaml` again and
these captures are one month ahead of what a fresh seed reproduces. No seed file was changed to
manufacture the scene.

## Audits run

- **Contrast, both themes, measured live** over every visible leaf text node in the two new
  Operations cards (54 nodes each pass), each against its own painted ancestor background.
  **Nothing below 4.5:1 in either theme.** Light floor 5.44, dark floor 5.53.
- **Themes were loaded, not toggled**, per the trap recorded in the Slice 4 section: write
  `valence-theme` to `localStorage` and reload. Setting `data-theme` on the root does not work.
- **No new CSS.** Both cards are built from `card`, `grid2`, `chiprow`, `badge`, `num`, `actions`
  and `rowmeta`, so token compliance, `prefers-reduced-motion` and the global focus ring are
  inherited rather than re-implemented. Nothing to audit for raw hex because nothing was added.
- **Semantic tables.** The per-reason funnel and the comparison both use `<table>` with a real
  `<thead>`; counts sit in `.num` cells.
- **Suites.** 660 backend tests green, 138 frontend tests green, `npx vite build` clean.

## The defect this pass found, and the fix

Invisible to 660 backend and 137 frontend tests, and found by rendering the page.

**A snoozed row disappeared with no statement that anything had been hidden.** The server withholds
a snoozed candidate from a response it still calls `coverage.status: "complete"` — correctly, since
a suppression is not a failure to read a source — and says so in `coverage.warnings`.
`coverageNotice()` returned `null` on any complete read, so that warning was dropped and the list
silently got shorter. That is the Slice 3 suppression rule read backwards: a suppression is
subtractive and is **always** reported.

The fix keeps the two claims separate rather than merging them. A complete-but-subtractive read now
returns `{status: "complete", message: null, warnings}` and renders as a quiet `rowmeta` line —
no status hue, because colour carries meaning only and a withheld row is not a failure. An
unreadable source keeps the callout it earned and now lists its warnings underneath instead of
dropping them for having arrived beside worse news.

A second, quieter finding: the test that should have caught this asserted the wrong thing. "readiness
coverage is not merged into execution coverage" passed a `warnings` entry to make a point about
`coverage.readiness` — a different field. It has been rewritten to pass a real `readiness` block,
and a new test pins the subtractive case in both the complete and partial forms.

The warning's wording was also fixed on the way through. `"1 item(s) are currently snoozed"` was
acceptable while the string was only a payload field; now that it is rendered copy it reads
`"1 item is snoozed and is not shown here"` / `"2 items are snoozed and are not shown here"`, with
a backend test asserting both forms. The same `(s)` construction in the client-facing MAP export
(`shared_plan.render_markdown`) was fixed with it.

## The one duplication in the contract, pinned

`frontend/src/telemetry.js` holds its own copy of the sixteen event names because it drops an
unknown one before sending — a call site with a typo should be a no-op a developer can see, not a
request the server silently discards. That is only safe while the two lists agree, so a backend test
reads the `EVENT_NAMES` block out of the JavaScript source and asserts set equality with
`app.telemetry.EVENTS`.

## The §17.7 walkthrough, and the half of it I cannot do

§17.7 asks for structured walkthroughs across eight scenarios, recording **time and navigation
needed** to answer the eight §2 Product outcomes and **any misinterpretation** of owner, phase,
status, or evidence. The second half is a human usability review. I can drive the app and read what
it says; I cannot time an operator or observe them misreading something, and a walkthrough record
that invented those numbers would be worse than no record. So this is the mechanical half, honestly
labelled, and the review itself is owed to a person.

The payload half is a test file, not prose: `tests/test_account_path_slice7_walkthroughs.py`
(7 tests) builds each of the six data-level states and asks the eight §2 outcomes of **exactly one**
Execution Path response. That is the part of "ten seconds" a test can hold — if an outcome needed a
second endpoint, the operator needed another tab, and the assertion fails. It records `unanswered`
rather than demanding eight answers, because a brand-new account genuinely has no interaction to
summarise and inventing one would be precisely the misinterpretation §17.7 is hunting for.

What was additionally driven in the browser, against the seed rather than a fixture:

| §17.7 scenario | In the running app | Payload test |
| --- | --- | --- |
| New account after onboarding | Bluepeak Health Systems — next move `task:tk-bp-scope` | Yes |
| Mature multi-program account | Terravance — two lanes, no averaged phase | Yes |
| Blocked launch | Terravance — `operator_blocker` is the promoted move and names its reason | Yes |
| Waiting on multiple customer owners | Harborline — the `waiting_on_customer` empty state, not a blank panel | Yes |
| Renewal inside the notice window | **No seeded account qualifies before 2026-09-06** | Yes — the test builds its own contract |
| Incomplete/partial data | **No — every seeded adapter reads successfully** | Yes — the test breaks a source deliberately |
| Narrow split-screen | Terravance at 620px, both themes | By construction, no — presentation, not payload |
| Keyboard-only and reduced-motion | Terravance — partly, see below | By construction, no |

Keyboard-only: the lens tabs, the promoted move's primary button, the snooze control and the group
disclosures are all reachable by `Tab` and take a visible focus ring in both themes, and the
Slice-3 fix for `.card { overflow: hidden }` clipping the ring still holds on the new rows.
Reduced-motion: the two Operations cards add no CSS and therefore no transition, so there is nothing
new for `prefers-reduced-motion` to suppress. What I have **not** established is whether the
keyboard path is *efficient* — how many stops it takes to reach the thing an operator wants — which
is exactly the "navigation needed" §17.7 asks to record and is again a question for a person.

Two scenarios are unreachable **in the seed** today, and both were left that way rather than
manufactured — the renewal one is elapsed time and resolves itself on 2026-09-06, and the
partial-data one would require breaking a table. Both are covered at the payload level by tests that
build their own fixtures, so what is missing is the rendering of those two states, not their logic.

## Not covered here

- **Component-level DOM tests**, for the same reason as Slices 2–6: the harness is
  `node --test src/*.test.js` over plain modules, with no React renderer or jsdom. This slice's
  defect is again exactly the class a renderer test would catch and a pure-module test cannot —
  the fifth consecutive slice to say so, and now with a worked example of the second-order cost: a
  pure-module test existed for this function and was aimed at the wrong field.
- **`measure.js` is untested by construction.** It imports `api.js`, which reads
  `import.meta.env.VITE_API_BASE` and throws under bare `node --test`. The rules live in
  `telemetry.js`, which is pure and tested; `measure.js` is the browser wiring around it.
- **A `partial`-coverage account in the UI.** Every seeded adapter reads successfully, so
  `views_with_incomplete_coverage` is 0 and the `warn` branch of the coverage notice was exercised
  by unit test rather than on screen. Forcing it would mean breaking a table.
