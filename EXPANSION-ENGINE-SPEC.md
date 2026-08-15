# Valence OS — Expansion Engine Spec
### Whitespace, value realization, and funding intelligence for the expansion-stage account
*Zach McCall · July 2026 · **v3** · Interleaved with PHASE-3-SPEC.md as Stages 5.5 and 7.5 · Extends the Commercial and Evidence tabs*

The People module answers who. This module answers where the money is, what evidence earns it, and when it gets funded. It is built for the actual shape of the job: roughly five very large accounts, mostly past onboarding, where the work is growing something like 1,000 paid seats toward 3,000 inside a 20,000-person company, again and again. The prior against a new prospect is 5 to 20 percent; against an existing customer it is 60 to 70 percent, which is why this module, not new-logo anything, is the revenue system.

Trust boundaries hold throughout: all usage data is aggregate cohort data from the Data team; cells and cohorts, never individuals; no field anywhere for a named person's product usage. §1.2 adds a minimum-cohort-size rule, because "aggregate" is not by itself sufficient when cohorts get small.

**What changed in v2.** The product thesis is unchanged. v1 was reviewed adversarially against the built codebase and was found to be directionally right but not implementation-ready: the seat math could double-count, the cell state conflated four independent facts, the signals engine assumed re-firing the current plays engine cannot do, "value commitment" collided with an existing entity, NRR had no revenue semantics to stand on, and the build order collided with Phase 3 Stages 6–8. v2 closed those contracts: the counting rule in §1.1, the restructured state model in §1.3, and a schema requirement named in every section.

**What changed in v3 (2026-07-31).** v2 was written under the old gating reflex and hedged in four places that were caution wearing an engineering costume. Zach removed the gate; the honest calls are now in the document. **The sequencing recommendation reversed** — this module interleaves with Phase 3 rather than following it (§0). **NRR is no longer deferred** — contract revenue semantics are in scope, because renewal needs them regardless (§10). **The heatmap no longer waits on a design decision** — the DESIGN-GUIDE.md amendment is drafted in §1.3 and lands with the work. **Headcount gets a real adapter** with a mock implementation, like every other external touchpoint, instead of being defined as manual-entry-only to dodge a registry row (§12). Schema changes in §13 are a migration list, not a request for permission — CLAUDE.md already says schema changes are proposals, not blockers, and the only genuine remaining gate in this repo is connecting real data, which nothing here does.

---

## 0. Sequencing and prerequisites

**This module interleaves with Phase 3; it does not follow it.** v2 called this Phase 4 and put it after Stage 8, on the argument that building expansion first would force Stage 6 generators to be retrofitted. That argument was backwards, and it was reached by protecting the Phase 3 spec's authority rather than by looking at the dependency graph.

Look at what Stage 6 actually builds. The **expansion business case builder** assembles "scorecard vs. the agreed bar, value stories by evidence tier, funding waterfall, named expansion lines, the ask." Every one of those nouns is defined in *this* document — the agreed bar is §2's value targets, the funding waterfall is §4's pools, the named expansion lines are §9's growth plan. The QBR's forward-looking half (§8) is the §2 ledger. Building Stage 6 first doesn't build it against "the pre-expansion model"; it builds it against **data that does not exist**, and the "leave a typed empty slot" mitigation in v2 was a way of admitting that without acting on it. A generator whose primary inputs are stubbed is a generator written twice.

So the order that builds each thing once:

| Stage | Content | Why here |
|---|---|---|
| ~~**5.5**~~ **done** | §1 whitespace map · §2 value ledger · §4 funding intelligence | The nouns Stage 6 needs. Pure schema + screens, no adapter dependencies. *Built: migrations 0017-0019; hardened in 0021, D-84/D-86/D-88.* |
| ~~**6**~~ **done** | Generators — business case, value review (§8), champion kit, pre-call brief, kickoff/QBR decks, weekly update | Consumed real cells, value targets, and pools — written once, as intended. *Built: migrations 0020-0021, D-87/D-88.* |
| ~~**7**~~ **done** (absorbs §3) | Triggers, calendar, org-change — §6.1 **already lists** "expansion signal (unit crossing the agreed bar; pull signals logged)" | *Built in migration 0022: recurring episodes, pacing, pull/usage/calendar/org/headcount signals, mock adapters, and succession handling (D-89).* |
| ~~**7.5**~~ **done** (new) | §5 five slots · §6 pre-agreed triggers · §7 renewal center · §9 growth plan + mutual view | *Built in migration 0023: linked qualification, sourced agreements and firing events, derived renewal case, overlap-safe growth bridge, and client-safe mutual view (D-90).* |
| ~~**8**~~ **done** (unchanged) | CONNECTIONS.md + end-to-end demo | *Built: eleven-boundary registry, fail-closed runtime approval gate, Operations surface, and executable new-account demo; migration 0024 hardens succession soft-delete (D-91).* |
| **9** (new) | §10 analytics · §11 playbook library | Needs history to be worth anything; genuinely last |

Two things this order gets for free: the `dedupe_key` fix (item 5 below) lands inside Stage 7's trigger work where it's a one-line index change rather than a migration against accumulated play history, and §3's calendar and org-change signals arrive in the same stage as the adapters that feed them.

**Stage 0 — prerequisites.** These are pre-existing gaps, not expansion work, and each one compounds if expansion lands on top of it.

| # | Item | Status |
|---|---|---|
| 1 | QBR metric selection is not account-scoped — one account's client-facing QBR can render another account's numbers | **Done** (D-82). Observations are now scoped to the account's programs; an observation with no program is unattributable and never reaches a client artifact |
| 2 | QBR includes open commitments without the `client_visible` promotion filter the mutual action plan enforces | **Done** (D-82). Regression tests added for both, each verified to fail against the pre-fix code |
| 3 | `portfolio_io._INSERT_ORDER` enumerates only tables through migration 0005 — MAP promotion, people layers, cadence, ingestion, and relationship intelligence are already silently dropped from "full" account export | **Done** (D-84). Covers everything through 0019, guarded by a test that introspects `sqlite_master` and fails when a new account-scoped table goes unregistered |
| 4 | Global search, source-citation lookup, and the Operations status screen have not been brought up to the current schema | **Done** (D-84/D-91) — search and citations cover the expansion objects; Operations now renders the complete connection registry and its gate state |
| 5 | `play_runs.dedupe_key` was `play_id:object_id` under a global UNIQUE index — a play could never fire twice for the same object | **Closed in migration 0022:** dedupe is play·episode; terminal actions require an observed clear/re-arm before recurrence |
| 6 | `play_definitions.trigger_kind` was a DB `CHECK` over four values | **Closed in migration 0022:** widened once for the Phase 3 + expansion trigger set |

Items 3 and 4 are hygiene that expansion will otherwise make worse; close them in Stage 5.5 alongside the first migration, since both are export/read-path work that touches the same registry the new tables must join.

---

## 1. The whitespace map (the core artifact)

The canonical expansion tool: a matrix of what the account has bought against everything it could buy.

### 1.1 The counting rule (read this before the axes)

v1 allowed composable rows ("DACH frontline managers") while also requiring row headcounts to reconcile against total FTE. Both cannot hold: a composite row overlaps the "DACH" row and the "frontline managers" row, so the column sums past 100% of the company. The column axis has the same problem in a worse form — the same manager belongs in performance reviews, change management, *and* conflict and feedback, so summing estimated seats across a row triple-counts them.

The map is only trustworthy if the counting rule is explicit, so it is stated first and everything else obeys it.

- **A seat is one person-license.** It is owned by the **row** axis. A person occupies exactly one seat no matter how many use cases they touch.
- **The base partition is the only additive dimension.** Each account has exactly one base population partition: a set of mutually exclusive, collectively exhaustive segments covering total FTE, with an explicit `unallocated` remainder that is visible, not hidden. Only base segments carry headcount, and only base-segment headcounts sum. The partition is chosen per account (usually business unit × region, sometimes just business unit) and changing it is a versioned event, because it re-bases every historical number.
- **Composite rows are views, not rows.** "DACH frontline managers" is a filter expression — base segments intersected with audience tags — and is marked **non-additive** wherever it renders. It is a lens for planning a motion, never an addend.
- **Columns are entitlements, not inventories.** A use case is something a seat is *lit for*, not a separate thing to sell a separate seat for. Cell-level seat estimates are therefore non-additive across a row, and the UI says so rather than letting the eye add them.
- **Rollups.** Additive down a column across base segments. Never additive across columns. Every total on the screen is labeled with which kind it is.

**"Where the next 2,000 seats live" is answered from the row axis** — unpenetrated and partially penetrated base segments, ranked by headcount. The columns tell you the *motion* that wins those seats, not the count. This is the honest version of v1's headline promise and it survives contact with a 20,000-person company.

### 1.2 The axes

- **Rows: populations.** Base segments per the partition above, plus **audience tags** (people managers, HRBPs, frontline leaders, early-career, new hires, executives) drawn from a **portfolio-global** vocabulary — not a per-account one, because §11's cross-account shape matching is impossible if every account names its audiences differently. Audience tags reference the People module taxonomy from migration 0013 rather than inventing a parallel vocabulary. Each base segment carries a headcount estimate with a source and a date, because addressable size is a claim, not a decoration.
- **Columns: use cases / deployment moments.** Performance reviews, engagement-survey action planning, change and transformation, new-manager transitions, onboarding, conflict and feedback. Also **portfolio-global**, with account-specific additions permitted but flagged as non-comparable in §11 queries.

**Cohort privacy floor.** Aggregate is not automatically anonymous: a composite view can narrow to a handful of people and become identifying by linkage even with no named-usage field anywhere. Every cohort-derived number — cell metrics, coverage, penetration — is subject to a **minimum cohort size**, a per-installation setting rather than a hard-coded constant. Below the floor the value renders *suppressed* (the existing cross-hatched unknown treatment, labeled "cohort too small"), never zero and never rounded. Suppression is applied at ingest and at display, and the composite-view builder refuses to construct a view whose headcount is below the floor.

### 1.3 Cell state: four stored facts, one derived display state

v1's six states mixed four independent things. `Penetrated` bundles paid, active, and evidenced. `Blocked` describes a gate. `Declined` describes a pursuit outcome. A cell can genuinely be paid, evidenced, *and* blocked from extending into a new region, and v1 has nowhere to put that. More importantly, v1 cannot express **paid but unevidenced** — which is the exact dangerous state §2 exists to catch.

So the cell stores four facts and *derives* the single state the heatmap shows. The single state stays, because a scannable heatmap is the whole point; it just stops being hand-set.

**Stored per cell:**

| Fact | Values |
|---|---|
| `penetration` | none · pilot · paid |
| `evidence_state` | none · anecdotal · measured |
| `blocker_state` | clear · gated *(with lane: works council / IT / legal / localization, plus owner)* |
| `pursuit_outcome` | none · declined *(reason, date)* · won · deferred *(until date)* |

**Derived display state**, first match wins:

| # | Condition | State | The move |
|---|---|---|---|
| 1 | `blocker_state = gated` | **Blocked** | Work the compliance lane, not the sales lane |
| 2 | `pursuit_outcome = declined`, not reopened | **Declined** | Leave it alone until the reason changes |
| 3 | `penetration = paid` and `evidence_state = measured` | **Penetrated** | Protect and harvest stories |
| 4 | `penetration = paid` and `evidence_state < measured` | **Penetrated, unevidenced** | Close the evidence gap — this is the churn-risk state, and it is the one v1 could not represent |
| 5 | `evidence_state ≥ anecdotal`, not paid at scale | **Proven** | Package the case, name the budget owner |
| 6 | sponsor linked, no evidence | **Target** | Run a programmatic wedge to create evidence |
| 7 | otherwise | **White** | Prospect the cell: identify the buyer, build the relationship |

Precedence puts Blocked and Declined first because they change *what the operator does next*, which is what the color is for. The cell card always shows all four facts, so nothing is hidden by the precedence.

**Transitions and reopening.** Each stored fact changes independently, always with a reason and a date, appended to cell history — the composite state is never written directly. A Declined cell reopens by an explicit **reopen event** carrying the changed reason (new sponsor, gate cleared, org change), which clears `pursuit_outcome` and leaves both the original decline and the reopen in history. This is what makes the demo's "Declined cell whose reason later changes" a defined transition rather than an edit.

**The rollup is the account thesis in one number:** total addressable seats vs. paid seats, by state, computed down columns over base segments only, per §1.1.

**The map renders as the signature visual of the Commercial tab** — a heatmap grid with paid density as fill intensity. This is a design-authority change, so the DESIGN-GUIDE.md amendment is written here and lands with the work rather than blocking it. The guide reserves green/amber/red for status and names the budget waterfall as the single documented exception for non-status color; the resolution is not to add a second exception but to **build the heatmap out of the status palette it already has**, because the cell states *are* statuses:

- **Hue is reused, not invented.** Penetrated is the existing positive status hue, Penetrated-unevidenced and Proven the caution hue, Blocked and Declined the negative hue, Target and White the neutral/unknown ramp. No new color enters the system, so the "single exception" rule stands unamended.
- **Hue never distinguishes two states on its own.** Seven states over four hues means every cell carries a **glyph and a short label** in addition to color — required by the standing no-color-alone rule anyway, and it is what lets Penetrated and Penetrated-unevidenced sit adjacent without being confused.
- **Fill intensity encodes paid density only**, on a lightness ramp within the cell's own hue, verified to hold 4.5:1 against the cell's text at every step in both themes. Intensity is never the difference between two states.
- **The D-70 adjacency rule extends to the grid.** The heatmap is a status surface, so the budget waterfall does not share a card or panel with it — which is the same constraint already applied everywhere else on this tab.
- **The grid is a semantic table** with `scope`-associated row and column headers, arrow-key cell navigation, and a per-cell accessible name reading population, use case, state, and paid density — so the map is usable without seeing it.

Amend DESIGN-GUIDE.md's Commercial section with the above when the heatmap lands; it is an extension of the existing color rules, not a carve-out from them.

## 2. The value realization ledger

Expansion and renewal both rest on one question: did the value we promised actually arrive? This ledger makes promised-vs-realized a first-class record instead of a memory.

**Naming.** v1 called these "value commitments." `commitments` already exists as an execution promise with a responsible party, an internal owner, and acknowledgement-based closure — a different record with a different lifecycle. Reusing the word would create ambiguity in the API, the UI, and every rollup. They are called **value targets** here.

- **Value targets.** Every business case, renewal, and expansion carries explicit value targets: the metric, the target value, the timeframe, the population, and who accepted it, with an acceptance date. Sourced from the agreed scorecard (the weeks-1-2 bar) and from generated business cases at acceptance. Targets are **versioned** — a renegotiated bar supersedes rather than overwrites, because "we hit the target" is only meaningful against the target that was actually agreed at the time.
- **Population identity.** A value target names a **base segment or composite view**, not a string. This requires metric observations to carry a stable population reference: today `metric_observations.cohort_label` is free text, which cannot be joined to a target reliably. Adding `population_segment_id` (§13 #6) is what makes the ledger computable at all.
- **Realization tracking.** Each target links to the metric observations and value stories bearing on it, and shows a status — realized, on track, at risk, not demonstrated — with freshness. Past its freshness threshold it renders unknown, never carried-forward good state. The value review (§8) pulls this directly: progress against the customer's own bar, not cherry-picked stats.
- **The value gap alert.** The dangerous account state is high usage with undemonstrated outcomes, because it looks healthy and churns anyway. A cohort with strong activity but no realized targets past their timeframe fires an attention item: close the evidence gap before the renewal window opens. This is the same condition as display state 4 in §1.3, computed once and surfaced in both places.
- **Negative evidence stays in.** Targets the client did not accept, and value claims that failed, are recorded per the existing library rules, because a business case that ignores them gets dismantled in procurement. They remain internal-only by default and never reach a client artifact except by affirmative promotion.

## 3. The expansion signals engine

Trigger-based expansion detection extending the Stage 7 plays engine, so opportunity identification is systematic rather than remembered.

### 3.1 Event semantics (the part v1 left implicit)

v1 named the signals but not their firing contract, and the current engine cannot honor an implicit one: `dedupe_key` is `play_id:object_id` under a global UNIQUE index, so a condition that resolves and recurs can never fire again. Every signal therefore needs the following, and Stage 0 item 5 must land first.

- **Signals are episodes.** A signal is `(cell, kind, opened_at, closed_at)`. Deduplication is against the *open* episode, not against the pair forever. `dedupe_key` gains an episode discriminator and the UNIQUE index moves with it.
- **Thresholds have direction and hysteresis.** A threshold signal fires on crossing the bar and closes only on crossing back by a stated margin, so a metric oscillating at the boundary produces one episode, not twelve.
- **Windows are explicit.** "Two pull signals in one cell" means two within a per-account window (proposed default: 90 days). No window, no signal.
- **Freshness gates firing.** A signal computed from data past its staleness threshold does not fire; it renders as unknown.
- **Dismissal has a cooldown.** A dismissed episode suppresses re-firing for a stated period; recurrence after the cooldown opens a *new* episode with the dismissal visible in its history.

### 3.2 The signals

- **Usage threshold:** a cohort crossing the agreed bar (the expansion threshold from the scorecard) proposes advancing its cell's `evidence_state` and drafts an opportunity.
- **Pull signals:** unprompted client demand — a BU asking for access, a leader requesting onboarding for their team. `pull_signals` already exists but is account- and program-scoped; a `cell_id` link is required for "two pull signals in one cell" to mean anything.
- **Business events:** acquisitions, restructures, new leadership, headcount growth in a population, from the Stage 7 org-change adapter and interaction capture; each maps to the affected base segments (a restructure makes the change-management column hot account-wide).
- **Calendar moments:** an approaching deployment moment (review season, engagement survey) in a population with an adjacent proven cell, from the Stage 7 calendar adapter.
- **Champion asks:** a validated champion requesting materials for an internal audience is the strongest signal and routes straight to opportunity drafting.
- **The land-and-leave detector [deferred on data, not on permission].** The shadow failure mode of every expansion motion: the account grows and the contract doesn't. This needs a **headcount time series** — per-segment headcount observed across quarters — and no scope decision manufactures elapsed time. The observation table and its adapter (§12) ship in Stage 5.5 so the series starts accruing immediately; the detector switches on once there are two comparable periods. Until then the growth plan (§9) carries an explicit "has the account grown since last renewal?" prompt at renewal prep, so the question is asked by a human while the data accumulates to ask it automatically.

### 3.3 Pacing guardrail (corrected)

Signals propose, they never push. Expansion that outruns realized value reads as desperate and burns sponsor trust, so the engine **will not propose vendor-initiated advancement** — cell promotion or opportunity drafting — for a cell whose underlying value targets are unrealized, and drafted opportunities inherit the evidence state of their cell.

**The guardrail does not apply to contractual events or to client pull.** v1 would have suppressed a pre-agreed contract trigger (§6) whose conditions were met because value elsewhere was unrealized. That hides a contract fact from the operator, which is worse than the pacing problem it was trying to solve. A met contractual trigger always fires; an unrealized value target attaches to the fired event as **visible risk** on the action, not as suppression. Customer pull likewise always surfaces, and outranks vendor push in queue ordering.

Every signal explains itself, links to its cell, and either becomes an opportunity, attaches to an existing one, or is dismissed with a reason.

## 4. Funding intelligence

Deals are won in the value case and lost in the funding mechanics, so the mechanics get their own record per account.

- **The fiscal map:** fiscal year end, annual planning window, budget-request deadlines, procurement lead time, works-council consultation lead time where applicable. Entered once, confirmed annually, visible on every commercial timeline. Procurement lead time already exists on `contract_versions` as canonical CRM data; the fiscal map **references it rather than restating it**, per the source-authority rule.
- **Funding pools:** named sources with owners and status — recovered vendor spend (incumbent displacement, with contract end dates), central L&D budget, CHRO discretionary, BU cross-charge, transformation program budget. Each pool links to the stakeholder who controls it. This **supersedes** the free-text `expansion_opportunities.funding_source`, which becomes a foreign key with a one-time backfill; two places to record who pays is one place too many. The existing `recovered_spend` model becomes a *pool type* rather than a parallel record.
- **The ask calendar (work backwards).** For any target close date, the tool back-schedules the dependency chain: business case delivered → budget owner sponsorship → budget window → procurement → works council where applicable → signature. Each step gets a date and an owner, missed steps escalate, and the whole chain renders on the Plan timeline. Steps are **typed links to existing objects** — tasks, milestones, compliance items — not a fourth parallel to-do system. An ask that misses the planning window slips a full cycle; the tool's job is to make that impossible to discover late.
- **Staged budget state** (existing: conceptually supported → in planning → formally allocated → requisition → approved → executed) now displays against the fiscal map, so "in planning" in March and "in planning" in November read as differently as they should.

## 5. Opportunity qualification (the five slots)

Each expansion opportunity carries a five-point qualification block, visible as filled/unfilled on the pipeline view: the **metric** (which value target funds this), the **budget owner** (named person, from the People module), the **decision process** (mapped steps and dates on the ask calendar), the **champion** (validated, per the champion pipeline), and the **compliance path** (clear, in progress, or blocked). No score, no weighting: five slots, and empty slots are the risk list for that deal.

v1 called this "MEDDIC-lite," which overclaims — it omits decision criteria, pain, paper process, and competition, and it collapses budget owner into the economic-buyer idea. It is not a lightweight MEDDIC; it is five slots chosen because they are the five things that actually stall these deals. Named plainly, it makes no promise it doesn't keep.

Two mismatches to resolve in schema: opportunities have `budget_state`, not a sales stage, so "advance stages" means advancing budget state unless a stage field is added — and it should not be, because budget state *is* the stage for this motion. And compliance items are program-scoped while opportunities are account-scoped, so the compliance-path slot links through the program, not directly.

An opportunity can advance with empty slots, but the empties render in the risk treatment and feed the account's commercial status rationale.

## 6. Pre-agreed expansion triggers (the no-renegotiation path)

The strongest expansion mechanic in the research, and the one that matches how this operator already works: agree the expansion conditions at signature, then track them in the open. When triggers are pre-agreed and written down, the expansion decision has already been made on paper, and hitting the threshold unlocks the next tranche without a fresh sales cycle.

- **Triggers live on an operational-agreement record, not on the contract.** `contract_versions` is a canonical read-only copy (`editable_locally` defaults to 0) and the codebase enforces that boundary. A trigger agreed in a scorecard conversation is not a contract term, and letting it write into the canonical copy would silently promote a conversation to paper. Each trigger is an **operational agreement** linked to a contract version, carrying: its source (signed paper vs. agreed in conversation, with the interaction link), effective and expiry dates, the metric threshold and named cohort, the pre-priced seat band it unlocks, and the agreed process when it fires. Triggers imported from signed paper are marked as such and are the only ones the tool describes as contractual.
- **Progress in the open.** Every trigger renders as a bullet chart on the Commercial tab and in the value review: current value against the agreed bar, with freshness. The client sees the same number we do, which is the point.
- **Firing.** A met trigger fires a play: notify the budget owner per the agreed process, draft the expansion paper from the pre-agreed band, log the event. Per §3.3 this fires regardless of value-realization state, with any gap attached as visible risk. A trigger met but not acted on within its window escalates, because an earned expansion left sitting is how earned expansions die.
- **Where triggers don't exist yet,** the tool prompts for them at the natural moments: business case generation, renewal prep, and QBR planning each surface "no pre-agreed triggers on this contract" as a gap.

## 7. The renewal command center

Renewal is the expansion engine's defensive half, one screen per contract:

- **T-minus timeline** from today to notice date and decision date, overlaid on the fiscal map, with the existing 120-day renewal-prep play firing as it does now — this trigger already exists and is not re-implemented.
- **The renewal case**, assembled continuously: value targets realized vs. promised, penetration growth on the whitespace map, story highlights, open risks with mitigation status, and the incumbent/alternative landscape.
- **Renewal and expansion as one motion:** the renewal screen shows qualified expansion opportunities eligible to ride the same paper, because the strongest renewal position is an expansion proposal.

## 8. The value review (the QBR, reframed)

The QBR generator gains a forward-looking structure, because backward-looking status reports are where QBRs go to die: progress against the client's own bar (from the §2 ledger), value gaps and the plan to close them, recommendations grounded in what worked elsewhere in their account, and the expansion frame — value achieved here, projected value there. The generator pulls the "there" from Proven and Target cells adjacent to the strongest realized targets.

The generator's account-scoping and promotion-filter defects are fixed as of Stage 0; this section extends a correct generator rather than a leaky one. Everything it adds obeys the same rule: only affirmatively promoted records reach the client artifact, enforced in the query, not by review.

Exec attendance by layer (from the People module) is tracked per review, and a value review without Economic-layer attendance flags the next one.

## 9. The account growth plan

The per-account thesis that ties it together: a seat target and date (1,000 → 3,000 by month six), decomposed into named lines, each line being a base segment or composite view with its opportunity, budget owner, funding pool, and ask date. Because lines can reference composite views, **lines are checked for overlap against each other** per §1.1 and an overlapping pair is flagged rather than summed — the fastest way to a fictional pipeline is two lines quietly selling the same people twice.

The gap between committed lines and the target renders as a bridge chart: current seats → named lines by stage → target, with the unfunded gap explicit. This is the screen to open before any internal pipeline review, and the honest unfunded-gap number is what makes it trustworthy.

**Scenario levers.** The plan carries the sensitivity model from the business-case work: seat price band, seats per line, and probability-weighted vs. committed views, so "what does the quarter look like if the DACH line slips a cycle" is a toggle, not a spreadsheet. Probability weights are **operator judgments with an author and a date**, rendered as assumptions per the standing credibility rules — not a governed stage-to-probability table, which five accounts cannot populate honestly.

**The client-facing twin.** A mutual growth plan view built on the existing MAP machinery and visibility rules: the shared version showing agreed triggers, joint milestones, and the value narrative, with internal lines (probability weights, funding-pool tactics, competitive notes) excluded by construction. Migration 0009 added `client_visible` to commitments, tasks, and milestones only, so **growth plan lines need their own promotion flag** using the same mechanism and the same generator-side enforcement. The strongest expansions are co-owned, and the client-facing artifact is how the growth plan stops being a vendor document.

## 10. Portfolio commercial analytics

Across five accounts, the honest presentation is counts and denominators — "3 of 11 cells converted this quarter," never "27%." A rate computed on five accounts implies a precision that isn't there, and percentages invite comparison the sample cannot support. Every figure is drillable to its records, states its time window, and renders an explicit insufficient-data state rather than a zero. No composite scores.

Shipping in the first slice: whitespace conversion counts by state transition, and where conversions stall; **time-to-expansion velocity** (days from a cell reaching Proven to funded — the single best health measure of the motion); ask cycle time from case-delivered to funded; value-target realization counts; and the portfolio bridge (all accounts' growth plans stacked).

**NRR is in scope, and contract revenue semantics come with it.** v2 deferred NRR on the grounds that `contract_versions.price` — a bare `REAL` with no currency, no period, and no recurring/one-off distinction — couldn't support it, and that modeling revenue "to compute one metric" was a bad trade. That was the wrong framing: it is not one metric. The renewal case (§7), the growth plan's committed-vs-weighted views (§9), the pre-priced seat bands on triggers (§6), and the funding waterfall (§4) all currently rest on a number whose units are undefined. A contract object that can't say whether its price is annual recurring, total contract value, or a one-time fee is under-modeled for its own sake, independent of NRR.

So `contract_versions` gains **currency, billing period, and a recurring/one-off type**, with an explicit ARR derivation rather than an inferred one, and contraction and churn become dated events rather than states inferred from a missing row. NRR is then a computation over records that exist, and it is reported per §10's counting rule — absolute movement with the account count stated, never a blended portfolio percentage that five accounts cannot support. Seat-based penetration growth ships alongside it, because it is closer to how this motion is actually managed day to day. External NRR benchmarks remain versioned sourced claims per the standing benchmark rule, never hard-coded.

**Land-and-leave incidents** landed with the §3.2 detector in Stage 7. The mock account carries two dated headcount periods so the behavior is demonstrable now; real accounts remain honestly inactive until their own elapsed history exists.

## 11. The expansion playbook library

The learning loop that makes five accounts compound instead of repeating: when a cell completes a state transition (to Proven, to Penetrated, or to Declined), the closure prompts a short structured entry — the population and use-case shape, what motion was run, what evidence carried it, which message landed with which layer, how long it took, and what would be done differently.

**Cell shape is the join key, and it only works because the vocabulary is global.** A shape is `(audience tags, use case)` — both portfolio-level per §1.2 — deliberately *not* the base segment, which is account-specific and would make every shape unique. Opening a Target cell for "European frontline managers, change management" surfaces how that shape was won or lost across the whole portfolio. Account-specific use-case columns are excluded from cross-account results and labeled as such rather than silently omitted.

Matching is **deterministic and explainable**: exact shape first, then use-case match with overlapping audience tags, then use-case match alone, each result showing why it matched. No similarity model, no embedding, no unexplainable ranking — with a handful of accounts, an operator can read the list, and a list they can read beats a score they can't.

Feeds the plays engine (a repeatedly successful motion becomes a play definition) and the messaging library (a message that carried a transition gets promoted). This is the difference between running five accounts and running the same account five times.

---

## 12. Build notes

**Slice order.** Per the §0 table: Stage 5.5 (whitespace schema and counting rule → cell facts and derived state → heatmap with the §1.3 design amendment → value ledger → funding intelligence and the ask calendar, plus Stage 0 items 3 and 4) → Stage 6 generators consuming it → Stage 7 absorbing §3's signals and the `dedupe_key` fix → Stage 7.5 (five slots, pre-agreed triggers, renewal center, growth plan) → Stage 8 → Stage 9 (analytics, playbook library). Stages 5.5–9 are complete.

Each slice lands with tests, both-theme screenshots, and a HANDOFF.md update before the next begins.

**Design.** The whitespace heatmap is the Commercial tab's signature surface and deserves the same care as the stakeholder graph — behind the design-authority amendment in §1.3, which is a gate, not a note. Trigger progress uses the existing bullet-chart convention. The bridge chart follows the waterfall conventions and inherits the D-70 rule: no status indicator in the same card or panel. The fiscal map renders as a band on the existing Plan timeline rather than a new visualization. Everything else is tables and the freshness language.

**Integrations inside the tool.** Cells link to People (sponsors, budget owners, audience taxonomy), Evidence (stories, observations), Plan (moments, compliance lanes), and the generators. Business case consumes cells, value targets, and triggers; the value review consumes the ledger and trigger progress; the MAP machinery carries the mutual growth plan.

**Adapters.** Population headcount by segment is HRIS-shaped data, and v2 defined it as manual-entry-only — which was a way of avoiding a CONNECTIONS.md row rather than a design position. Stage 7 built **a real adapter interface with a mock implementation**, exactly like transcription, email, and calendar, including CSV fixtures and job-backed sync. That is what "build everything, connect nothing real" means, and it is also the only way the §3.2 detector gets a time series without hand-keying one. Manual entry remains a first-class path, since headcount will often arrive as a number someone says in a meeting. Stage 8 registered the boundary formally in `CONNECTIONS.md`; no real source is connected.

**Files the module will touch beyond its own migrations and service.** `schemas.py`, `output_gen.py`, `portfolio_io.py` (export registry, per Stage 0 item 3), `search.py`, `routers/library.py`, `Commercial.jsx`, `App.jsx`, and the QBR, MAP, timeline, metrics, plays, operations, and waterfall views. Also: seed generation, account export/restore, global search, source-citation lookup, attention rules, output security tests, and the full acceptance script.

**Definition of done.** On a mock account, the operator can answer without leaving the tool: where the next 2,000 seats live and what state each source is in; which value targets are realized, at risk, or undemonstrated, and which cohorts have a value gap; which pre-agreed triggers exist, how close each is to firing, and whether any fired trigger is sitting unactioned; every step and date between today and a funded ask, and which steps are late; what the renewal case says today if the renewal were tomorrow; how far the named growth plan is from target, with the unfunded gap explicit, in both committed and probability-weighted views; and, for any new target cell, how the nearest-shaped cells were won elsewhere in the portfolio. Every answer carries dated evidence and freshness, every total states whether it is additive, and every cohort below the privacy floor renders suppressed.

The demo script includes one trigger firing and escalating unactioned, one Declined cell reopened by a changed reason, one cell in the paid-but-unevidenced state driving a value-gap alert, one composite view refused for falling below the cohort floor, and two growth-plan lines flagged for overlapping populations.

---

## 13. Schema changes

The migration list, batched per the standing rule — which says schema changes are proposals, not blockers, so this is what gets built unless something here is wrong. Each is a numbered migration; none is a manual change.

| # | Change | Rationale |
|---|---|---|
| 1 | `population_segments` (per account: base partition members, headcount, source, date, versioned partition id, `unallocated` remainder) | §1.1 — the only additive dimension |
| 2 | `audience_tags` and `use_cases` as **portfolio-global** vocabularies; audience tags reference the 0013 People taxonomy | §1.2, §11 — cross-account shape matching |
| 3 | `population_views` (composite: filter expression over segments + tags, marked non-additive) | §1.1 — composites as views, not rows |
| 4 | `whitespace_cells` with the four stored facts, derived state computed not stored, plus `cell_history` (fact, before, after, reason, date, actor) | §1.3 |
| 5 | `value_targets` (metric, target, timeframe, population reference, accepted-by, acceptance date, version, supersedes) | §2 — named to avoid the `commitments` collision |
| 6 | `metric_observations.population_segment_id` (nullable FK), superseding free-text `cohort_label` for ledger joins | §2 — makes realization computable |
| 7 | `funding_pools` + `expansion_opportunities.funding_pool_id`, deprecating free-text `funding_source` with a backfill | §4 — one place for who pays |
| 8 | `fiscal_maps` per account (references, does not restate, canonical procurement lead time) | §4 |
| 9 | `operational_agreements` linked to `contract_versions`, carrying pre-agreed triggers with source, effective/expiry dates, seat band, and firing process | §6 — keeps the canonical contract copy read-only |
| 10 | Qualification block on `expansion_opportunities` (five nullable slots); no new stage field — `budget_state` is the stage | §5 |
| 11 | `growth_plan_lines` referencing cells/views, with scenario fields and a `client_visible` promotion flag matching migration 0009 | §9 |
| 12 | `playbook_entries` keyed by cell shape and transition | §11 |
| 13 | `pull_signals.cell_id` | §3.2 |
| 14 | `play_runs.dedupe_key` episode discriminator; UNIQUE index moves with it | §3.1 — **Stage 0 blocker** |
| 15 | Per-account settings: minimum cohort size, pull-signal window, dismissal cooldown, hysteresis margin | §1.2, §3.1 — thresholds are data, not constants |
| 16 | `population_headcount_observations` (segment, period, headcount, source, date, adapter provenance) | §3.2, §12 — ships early so the time series starts accruing |
| 17 | `contract_versions` gains currency, billing period, and recurring/one-off type, with an explicit ARR derivation; contraction and churn become dated events | §10 — the price field is under-modeled for renewal and the waterfall regardless of NRR |

Not built, deliberately — these are judgment, not caution: a sales-stage field on opportunities (§5 — `budget_state` *is* the stage for this motion), a governed stage-to-probability table (§9 — five accounts cannot populate one honestly, so weights stay dated operator judgments), and any similarity or embedding model for shape matching (§11 — an operator can read a list of five accounts' worth of cells, and a readable list beats an unexplainable score).
