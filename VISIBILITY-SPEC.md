# VISIBILITY-SPEC.md

**Status:** proposed, additive. **Slice 1 is built** (2026-08-06, D-251…D-258); slices 2–6 are not
started. `CLAUDE.md`'s authority chain does **not** name this file, and nothing here may be built on
the strength of this file alone — Slice 1 proceeded on Zach's instruction "continue building with
what's specc'ed out", given after everything in the named chain was finished. That is an instruction,
not a naming, and D-251 records the difference rather than papering over it. Slices 2–5 wait on
Zach's confirmation; Slice 6 waits on the schema conversation in any case.

**Origin:** the competitive review of a Vitally demo call (2026-08-06, session "Vitally call review").
That review produced nine candidate borrowings. Six survived verification against the repo, two were
already built, and one was factually wrong about what the records can support. §2 records what
changed and why, because a spec that quietly drops a recommendation is indistinguishable from one
that forgot it.

---

## 1. The governing rule

**No item in this spec may create a fact. Every one renders a fact the records already entail.**

That is the whole reason this is a small spec rather than a stage. Slices 1–5 need **no migration**
and store nothing: each is a query-time read over records that exist, or a presentation of a value
already on the wire. Slice 6 is the single exception, is separated for exactly that reason, and is
the only part that needs the schema-change conversation.

The rule has teeth in two directions:

- A count of what is **missing** is a fact about our own record-keeping, not about the customer. It
  stays inside the trust boundary precisely because it never reads the customer's behaviour.
- A count of what is **complete** is a planning fact if it comes from `recorded_complete`, and a
  readiness state if it comes from an evaluator. Those are different claims and this spec never
  merges them. §5 is the item where that distinction does the most work.

---

## 2. What the review got wrong, and the corrections

Recorded here rather than in a changelog, because two of these are the difference between a
buildable item and a fabricated one.

### 2.1 "Rules rendered as sentences" — already built

The review said `due_rule_json` is "rendered nowhere." It is rendered:
`frontend/src/requirementDetail.js:119-125` exports `dueRuleText`, producing "14 days after the
kickoff date" / "90 days before the renewal date" / "On the kickoff date"; it is called at
`frontend/src/views/RequirementDetail.jsx:47` and covered by `requirementDetail.test.js:83-89`.

The item does not disappear — it shrinks. What is genuinely unrendered is (a) the same rule on
`AccountPlan.jsx`, which shows a date input and a prose hint but not the rule that produced the
date, and (b) the **evaluator configuration** on a requirement definition. Both are reuse, not new
capability. See §7.2.

### 2.2 "Variance from plan" — only half of it is honest

The review proposed rendering "Started Jun 09, 2026 — 13 days after target" from
`readiness_plan_instances.due_date`. The planned side exists. The **actual** side mostly does not.

A readiness component carries `assessed_through` — the date the evidence was assessed through
(`backend/app/readiness.py:120-126`, and every `_component(...)` call site). That is not the date the
requirement became true. Rendering it as a completion date would put a fabricated date in front of
an operator, which is the failure `readiness_playbook_entries.offset_days` has a comment about
avoiding.

Corrected shape in §6: a completion delta is rendered **only** for rows with
`recorded_complete_on` — two planning facts differenced, both legal. For everything else the two
facts are stated separately and never subtracted.

### 2.3 "Decay on generated prose" — narrower than stated

The review generalised from Vitally's six-month-old brief to "briefs" in Valence. `MeetingPrepare`
is computed on demand (`backend/app/account_prepare.py:426 build_meeting_prep`); nothing persists
it, so it cannot go stale. The gap is real but it is specifically **`copilot_runs`**, which are
persisted (migration `0034`) and re-openable from the saved-runs list
(`CopilotPanel.jsx:277-285`). See §3.

### 2.4 "Per-node execution counts" — instantiation, not completion

Verified: `playbooks.preview_upgrade` (`backend/app/playbooks.py:341`) carries no applied counts.
But the Vitally screenshot's counter is *"Runs Completed 0 (0%)"*, and the completion half is the
problem. Deriving "how many of these are satisfied" per entry means running the readiness projection
for every account holding a live plan — expensive, and worse, it would place a **readiness state
inside a planning preview**, which is the conflation the plan/readiness split exists to prevent.

Corrected shape in §5: instantiation counts and `recorded_complete` counts only. Both are planning
facts. A dead entry is still visible — an entry instantiated 40 times and never once recorded
complete is exactly as loud as Vitally's `0 (0%)`, without asserting a state.

### 2.5 The composition-layer argument — real tension, not a recommendation

The review counted 54 view components against 4 destinations (verified: 54 `.jsx` files in
`frontend/src/views/`) and proposed a widget-composition layer, triggered by the next redundant
surface. Two paragraphs earlier the same review said to refuse custom traits because a
user-configurable key/value bag makes the integrity tests unwritable.

Those pull against each other. A composition layer general enough to replace bespoke views needs a
registry of widgets bound to arbitrary field selections — which is a custom-trait system with a
different name, and it would put the "no stored readiness state" assertions back out of reach. The
54 surfaces are also not 54 arrangements of one vocabulary; most are account-tab surfaces over
genuinely different records.

**This spec takes no position and proposes no work here.** It is recorded so the next person who
reads the review does not treat it as an agreed direction.

### 2.6 `INVARIANTS.md` — deferred, and here is the objection

Consolidating the per-stage "non-obvious rules" out of `CLAUDE.md` would create a second document
stating the same rules, which is a second source of truth about the constraints — the failure mode
the entire data architecture is built to prevent, applied to the governance layer. If it is ever
written it must be **derived and explicitly non-authoritative**: an index from rule to the test that
enforces it, with `CLAUDE.md` remaining the only place a rule is stated. Not proposed here.

---

## 3. Slice 1 — decay and withholding on persisted copilot runs

**No migration.**

### 3.1 The gap

`CopilotPanel.jsx:277-285` re-opens a saved run by id and renders `run.answer_markdown` through
`CopilotAnswer` at full weight. The only age signal is `CopilotPanel.jsx:195`, a bare
`Current through <date>` in `rowmeta` type — no age chip, no decay ramp, no cross-hatch. A run
answered in February and re-opened in August is visually identical to one answered a minute ago.
That is the carried-forward-good-state failure the `DESIGN-GUIDE` freshness language exists to
prevent, inside the one surface that persists generated prose.

### 3.2 Rules

1. A re-opened run renders `run.generated_at` through the existing `AgeChip` (`ui.jsx:413`) and the
   existing decay ramp. A run generated in the current session and a run re-opened from history use
   the **same** treatment — the freshness signal comes from the date, never from how the run
   arrived on screen.
2. Past the threshold the prose body is **collapsed behind an explicit action**, not dimmed. Dimming
   is still a rendering of the claim; collapsing withholds it.
3. The withheld state is authored on the server as a clause completing "held back because …", and
   the sentence frame lives beside `sharedPlan.withheldSentence`. **A view that composes any part of
   a refusal can soften one** (D-153). The client renders the clause and never builds it.
4. The threshold is a property of the run's scope, not a constant chosen in a component. It is
   returned on the payload so the sentence can name it ("… the evidence window closed 41 days ago").
5. **The claims and sources block is never collapsed.** The evidence is what makes the staleness
   legible; hiding it with the prose would leave an operator with a refusal and no way to check it.
6. Nothing is regenerated automatically. A stale run is a record of what was said in February; a
   regeneration is a new run with a new id.

### 3.3 Tests

- A run past the threshold returns a withheld sentence and no answer body; a run inside it returns
  the body and no sentence.
- The sentence is byte-identical between the API response and what the view renders (identity, not
  substring).
- Two runs with the same `generated_at`, one freshly asked and one loaded from history, produce the
  same freshness treatment.
- The claims block is present in both states.

---

## 4. Slice 2 — portfolio absence counters

**No migration.**

### 4.1 The gap

Nothing counts what is missing at portfolio level. `internal_roster.coverage_data`
(`backend/app/internal_roster.py:42`) is account-scoped with a 14-day default;
`internal_reporting.portfolio_analytics:369` covers asks, escalations, and feedback; `Queue` ranks
what exists. There is no read that answers *where am I not looking.*

### 4.2 Rules

1. The counters count **our** record-keeping only: accounts with no recorded interaction in N days,
   no dated stakeholder assessment in N days, no readiness evidence of any kind in N days, no
   recorded touch on a program in an active phase. Every one is derived from our own records. None
   reads customer behaviour, and none may be added that does.
2. **State the count, never score it.** No composite "coverage score", no ring, no percentage-of-
   portfolio grade, no colour ramp across the strip. Slice 7 §17.5 and `index.css:967` both already
   say this; it applies here without amendment.
3. The window is a **parameter with a stated default**, rendered inside the sentence
   ("62 accounts with no recorded note in 30 days"), never a silent constant. This is a coverage
   threshold, not a benchmark: it makes no claim that 30 days is good or bad, and the copy must not
   imply one. The no-hard-coded-benchmarks rule bans the claim, not the window — say so in the code
   comment so the next reader does not have to re-derive it.
4. Each counter links to the list it counted. A number an operator cannot open is an accusation.
5. Placement is a strip on Today, above the queue. It is **not** a new top-level destination and no
   new destination is proposed.
6. Zero is rendered as zero, plainly. It is the only counter value that is good news and it still
   gets no status hue.

### 4.3 Tests

- Counts equal the length of the list each one links to, on the same query.
- Changing the window changes both the number and the rendered sentence.
- Schema introspection: this slice adds no table and no column.
- An account archived mid-window is excluded from both the count and the list, consistently.

---

## 5. Slice 3 — playbook entry instantiation counts in the upgrade preview

**No migration.**

### 5.1 Rules

1. `preview_upgrade` gains, per entry, two derived counts over `readiness_plan_instances`: how many
   live plans instantiated this entry, and how many of those carry `recorded_complete = 1`. Both are
   planning facts (`0042` comments at `readiness_plan_instances.recorded_complete`).
2. **No readiness state is read, computed, or reported here.** Per §2.4 that is both a cost problem
   and a category error. The preview is about the plan; readiness has its own surface and its own
   vocabulary.
3. The counts are scoped and the scope is stated. A count over "live plans on this account" and a
   count over "live plans everywhere" are different numbers and the label must say which.
4. An entry with zero instantiations renders as zero, not as absent. The whole value of the borrowing
   is that a step which has never fired is visible at the moment of deciding whether to keep it.
5. `recorded_complete = 0` across every instantiation is **never** rendered as "not working",
   "broken", or a failure rate. It is a count. The operator draws the inference.

### 5.2 Tests

- An entry instantiated on three plans, one recorded complete, reports 3 and 1.
- The counts move when a plan is archived and do not move when a readiness evaluator changes.
- `preview_upgrade` issues no call into `readiness` — asserted structurally, not by timing.

---

## 6. Slice 4 — plan variance, stated honestly

**No migration.**

### 6.1 Rules

1. For a plan instance with `recorded_complete_on` and a `due_date`, render the delta:
   "recorded complete 13 days after the planned date." Both operands are planning facts; the
   difference is a planning fact.
2. For every other instance, **the two facts are stated separately and never subtracted.** The
   planned date and its age ("planned for Jun 09, 41 days ago") is one statement; the requirement's
   readiness state, in readiness's own vocabulary, is another. They may sit side by side. They may
   not be composed into "13 days late."
3. `assessed_through` is never rendered as a completion date, in any surface, under any label. §2.2.
4. No colour on the delta. A late plan item and an early one are the same kind of fact; late is not
   a status.
5. A dependency-relative phrasing ("2 days after blockers complete") is **only** permitted when the
   blocker is resolved and the date is therefore known. An unresolved dependency renders the date as
   **unknown**, with the existing cross-hatched treatment — never as a soothing relative phrase.
   This is the one place the Vitally screenshots showed the cost directly: an onboarding project
   eight weeks past its target end date, every task reading "Tomorrow / Saturday / Wednesday."

### 6.2 Tests

- A row with no `recorded_complete_on` produces no delta, under any combination of readiness state.
- `assessed_through` never appears in a field whose name or label implies completion — asserted over
  the response shape.
- An unresolved dependency yields the unknown treatment, not a relative phrase.

---

## 7. Slice 5 — presentation

**No migration.** Four items, none of which changes what is claimed — only how it is read.

### 7.1 Inline citation chips

Verified block-level today: `.proposal-span` (`index.css:1003`) is a dashed-border quote *under* the
claim, and `CopilotPanel.jsx:209-225` renders claim text with a chip row beneath it.

- Keep both. The block form is right for `ProposalReview`, where an operator adjudicates one
  proposal at a time and the quote is the object of the decision.
- Add a **third** presentation for prose-heavy output — copilot answers, the artifact side of
  `shared_plan` — where a small neutral numbered chip sits inline after the clause it supports and
  opens the existing frozen-snapshot drawer (`.copilot-source-drawer`).
- The chip spends **no colour**. Shape plus a number, per the no-state-by-colour-alone rule.
- The chip is generated from the same claim→source links already on the payload. It introduces no
  new mapping and cannot cite something the claims block does not.
- An uncited clause is still a validation failure, unchanged. The chip changes presentation, never
  what passes.

### 7.2 Reuse `dueRuleText`, and render evaluator configuration

- Call the existing `dueRuleText` on `AccountPlan.jsx` beside the date, so the rule that produced
  the date is visible with it.
- Render the requirement definition's evaluator configuration as a sentence with `.mono` operand
  tokens. This matters most where an **unknown evaluator key fails closed into `coverage: partial`**
  and today nothing on screen says what was configured — the operator sees a degraded pillar with
  no way to see the cause.
- No new formatter where one exists. §2.1.

### 7.3 A hueless view-level scope strip

`.coverage-callout` (`index.css:895-903`) carries `is-warning` / `is-healthy` hues — correct for a
per-card coverage claim, wrong for "this whole view is filtered."

- A separate, full-width, **hueless** strip stating a view-level narrowing before the numbers.
- Verified gap: `Queue` states its snoozed remainder (`Queue.jsx:126-129`) and explains an empty
  result (`Queue.jsx:111`), but a **non-empty saved view narrows silently**. That is the case this
  strip is for.
- Wording is authored on the server wherever the narrowing is a server-side one, per D-153. A purely
  client-side filter may author its own sentence, because withholding nothing.
- This completes D-160 in the other direction: a `complete` response can be subtractive, and the
  subtraction is stated quietly, without a status hue, because a withheld row is not a failure.

### 7.4 Short reference ids

A muted `.mono` short id on config objects — playbook entries, requirement definitions — derived
from the existing id (no new column), so a definition can be named out loud in a call.

### 7.5 Explicitly not taken

Recorded so they are not re-proposed:

- **The % complete ring on milestone groups.** Defensible in isolation — it counts planning facts,
  not readiness states — but it would sit one card from a surface that bans rings *specifically* so
  nothing reads as a composite grade (`index.css:967`), and a viewer will not make that distinction.
  Render "3 of 9 scheduled" as text.
- **Donuts.** Colour-only encoding with a legend; arcs compare badly. A bar is strictly better.
- **Emoji navigation icons.** Colour and imagery doing categorical work.
- **Categorical colour squares on group headers.** Same collision the review found live in Vitally,
  where red meant `Not Started` in one table and `G2 Review` in another.
- **A uniform-grey generation stamp.** Take the *placement* in the card header; never the treatment.
  Rendering "6mo ago" and "37m ago" identically is how a brief ends up saying "due tomorrow" six
  months later.

---

## 8. Slice 6 — advocacy tags on people (the one migration)

**Needs a migration, and is separated for that reason. It is the only part of this spec that needs
a schema conversation.**

- Kinds: reference, review, quote, beta participant, speaking. This is **deployment engagement** —
  the trust boundary permits "meetings, comms, advocacy" explicitly.
- Each tag carries a **date and an evidence note**, structurally required, like every other
  stakeholder assessment. A tag without them is not a lighter version of the record; it is a
  different and worse one.
- No sentiment, no inferred willingness, no score, no "advocacy level."
- Nothing here reads or implies individual product usage.

---

## 9. Refused outright

Not deferred — refused, with the rule each one breaks. These are the parts of the Vitally product
that its data model permits and ours does not.

| Pattern | Rule it breaks |
|---|---|
| A users table with `LAST SEEN` / `SESSIONS` per named individual | *"No table, column, or field may exist anywhere for a named individual's usage of the Nadia product."* Hard no. Account-level aggregate usage is fine; the row is not. |
| A "vibe check" with *Levels of Enthusiasm* / *Who is most resistant* | Model-inferred sentiment about named people. Relationship-health signals are counts and distributions from our own correspondence, **never** sentiment inference. Keep the shape of a pre-call brief; refuse the inference. Valence's legal equivalent already exists: dated stakeholder assessments with stance, influence, and an evidence note, authored by a person. |
| A free-standing `CSM Sentiment` account property | Undated, unevidenced, and — as seen — capable of reading "Concerning" beside "Healthy" on the same card. The no-composite-score rule proving itself. |
| Transactional email with open/click/bounce tracking | Two violations at once: no-auto-send, and `ADOPTION-COMMS-SPEC.md` excludes open/click tracking. |
| Custom traits / user-defined key-value fields | The escape hatch is the vulnerability: "no readiness state is stored anywhere" is unassertable if an operator can create a trait named `readiness_state`. The cost of refusing — every field is a migration — is real and worth paying. |

---

## 10. Build order and gates

1. ~~Slice 1 (decay on persisted runs) — the one with a live example of what its absence costs.~~
   **Built 2026-08-06** (D-251…D-258). No migration; 12 backend and 7 frontend tests; six captures in
   `design-screenshots/visibility-slice-1/`.
2. ~~Slice 2 (absence counters).~~ **Built 2026-08-06** (D-259…D-261). No migration; 13 backend and
   7 frontend tests.
3. ~~Slice 5 (presentation), which can interleave freely; nothing depends on it.~~
   **Built 2026-08-06** (D-262…D-266). No migration; 18 backend and 18 frontend tests.
4. ~~Slice 3 (playbook counts), Slice 4 (plan variance).~~ **Both built 2026-08-06**
   (D-267…D-268, D-269…D-270). No migration; 13 backend and 8 frontend tests.
5. ~~Slice 6 last, and only after the schema change is agreed.~~ **Built 2026-08-06**
   (D-271…D-274). Migration `0054_advocacy_tags.sql`; 9 backend and 6 frontend tests.

**The whole spec is built.** 860 backend tests (was 807 after Slice 1), 308 frontend (was 263),
lint exit 0, clean build.

**Screenshots for Slices 2–6 are outstanding.** `browser_screenshot` returned "Current display
surface not available for capture" on every attempt across two fresh headless sessions on
2026-08-06, several hours after Slice 1's six captures succeeded the same way — the headless page
reported `visibilityState: "hidden"`, so the surface was not being composited. This is an
environment state, not a code problem, and it is the one gate on this spec still open. What was
verified in its place, in a live headless session against the running app: both themes apply at the
root (`--bg-app` `#f4f5f8` light / `#050609` dark), Slice 2's strip renders all four sentences and
its independence caveat in both, and Slice 5's scope strip renders "Narrowed to the Needs you now
band. 6 of 34 shown · 28 not listed here." Slice 6's write path and card shape were exercised
end-to-end over the API. **Capture the pair for each slice when the capture layer is back.**

Each slice lands with tests, both-theme screenshots, a decision entry, and a `HANDOFF.md` update.

**Correction to item 5 (2026-08-06):** "only after the schema change is agreed" re-gates work that
D-83 explicitly un-gated — "downgrading a schema change to a request for permission … reintroduce[s]
a gate that was deliberately removed". Slice 6 was built on Zach's instruction to build the spec,
with the table decision argued in the migration header where the standing rule puts it.

**Correction (2026-08-06):** an earlier draft of this section recorded that screenshots were
"blocked at this environment's capture layer". That was wrong, and D-248 records the same correction
where it was first made. `browser_open_local_preview` cannot be screenshotted, but
`browser_open_session` with `headless: true` can. Slice 1's six captures were taken that way.

**Nothing in slices 1–6 flips an adapter, adds a network boundary, or changes `CONNECTIONS.md`.**
Slice 6's `advocacy_tags` is a local table recording facts an operator types in; it has no adapter
and no external touchpoint.
