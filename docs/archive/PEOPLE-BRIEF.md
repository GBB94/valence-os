# People tab enrichment brief
### Making the relationship surface as rich as the model beneath it
*July 2026 · Companion to `DESIGN-GUIDE.md` · Presentation-layer work plus batched schema proposals*

> **Historical / mostly executed (2026-07).** This brief was folded into `PHASE-3-SPEC.md` Part 3 (the People module) and built across Phase 3 Stages 2, 3, and 5. Its "the schema is not [open]" framing predates the Phase 3 regime change (D-73), under which the People-module objects/fields it proposed are in-scope and now built. Kept for history; the live spec and `HANDOFF.md` are authoritative.

---

## 0. Ground rules

The presentation layer is open per `DESIGN-GUIDE.md` §0. The schema is not. This brief is split accordingly: Sections 2 through 4 need no schema change and can build now. Section 5 is a batch of schema proposals with rationale, presented per the standing rule, each independently acceptable or declinable.

Trust boundaries apply with extra force here, because every record on this tab describes an identifiable person. Restating the three that this work could accidentally break:

- No field, view, or derived indicator anywhere for a named individual's product usage. Engagement on this tab means deployment engagement, derived from logged interactions only. No comms sync, no calendar sync; both are standing out-of-scope and would drift this surface toward surveillance.
- Stance, influence, and relationship strength always carry an assessed-on date and an evidence note. The enrichment below surfaces those rather than adding assessments without them.
- Stakeholder judgments are internal-only by default and never appear in client-facing generators. Nothing in this brief changes that.

**Reference class** (what best-in-class looks like, and what we take from each): Altify anchors on the org chart with influence as a distinct overlay, which we already do. DemandFarm's core insight is white-space analysis, showing the gaps rather than the filled seats. ARPEDIO scores coverage per opportunity. Gainsight flags multithreading depth and champion departure. We take the patterns, not the ceremony: everything below respects the 30-second rule and adds zero required fields at capture time.

---

## 1. The gap in one paragraph

The model holds roughly ten meaningful facts per stakeholder. The tab renders four. The evidence note behind every stance, the assessed-on date, what the person cares about, what the product does for them, their roles across multiple programs, and their derived last touch are all captured today and all invisible on the People tab. There is no roster, so the graph is the only index of people, and a graph is a poor list. There is no gap view, so a program missing a budget owner looks identical to one that is fully covered. The fix is not more capture. It is rendering what capture already paid for.

---

## 2. The roster (new, no schema change)

The tab becomes two views under a toggle, matching the graph/power-interest pattern already there: **Roster** and **Map**. Roster is the default. The graph stays the expressive surface; the roster is where work happens.

One row per person per account, built from existing data:

| Column | Source | Notes |
|---|---|---|
| Name, title | Person | Name is the link that opens the detail panel |
| Roles | StakeholderRole per program | Badges, one per program role. Multi-program people finally legible |
| Stance | StakeholderRole | Shape + color pair from the graph (● supporter, ◆ skeptic, ▮ unconverted), `--data-*` family, never status hues |
| Stance age | stance_assessed_on | `AgeChip` with the decay ramp. A stance assessed 90 days ago should look old |
| Influence | StakeholderRole | Small filled-bar glyph, not a number |
| Last touch | derived days_since_touch | `AgeChip`. No touch ever renders as the unknown treatment, not a blank |
| Open items | commitments where responsible or internal owner | Count, links into the Ledger filtered to that person |

Sortable by last touch and stance age, because "who am I neglecting" is the question the roster exists to answer. Compact rows, hairlines, no zebra, per the table spec in `DESIGN-GUIDE.md` §6. This should be the first consumer of the shared `Table` primitive from the punch list's PR 3, not another hand-rolled table.

---

## 3. The person detail panel (rebuilt, no schema change)

Currently a four-row card. Becomes the standard 520px slide-over (per the guide: slide-over everywhere except the Ledger), opened from a roster row or a graph node, with everything the model already knows:

**Header.** Name, title, affiliation, email. Stance shape+color chip with its `AgeChip`.

**Why they matter.** `cares_about` and `value_for_them`, rendered as two labeled prose blocks. These are the two fields you fill at capture specifically to reread before a call, and today the only place they exist is the edit form. This is the single highest-value fix in this entire brief.

**The evidence.** The stance evidence note, quoted, with assessed-on date. The trust framework requires this note to exist; the interface should honor that by showing it. A stance whose evidence is stale invites reassessment, and seeing "assessed 2026-03-02: pushed back on rollout pace in steering" is what makes the judgment trustworthy.

**Roles across programs.** One line per program: program name, role, stance in that program. The Person × Program model finally gets a surface.

**Recent interactions.** Last five interactions this person attended, dated, from the existing participants join, each linking to its Ledger record. This is the pre-call prep scenario from the scoping doc, per person.

**Open items.** Commitments where they are the responsible party, with due dates and internal owner. What did we promise them, what did they promise us.

---

## 4. Coverage becomes a gap view (rebuilt, no schema change)

The coverage card currently reports two numbers and a list. It becomes the white-space panel, the DemandFarm insight, computable entirely from existing enums:

**Role coverage grid.** Rows are the seven role types, columns are the account's programs. Each cell: filled (someone holds it, with stance shape), or empty. An empty champion or budget_owner cell renders in the unknown treatment, because an unfilled seat is not "fine," it is unknown. This makes "we have no budget owner on the expansion program" visible at a glance, which is the single most commercially important fact this tab can surface.

**Multithreading.** Keep the existing single/multi-threaded line and VP+ active count.

**Neglect list.** Keep the senior-stakeholder touch list, but use `AgeChip` uniformly (it currently does, keep it) and sort by staleness descending.

**Graph polish, minor.** Hover tooltip with name, title, role. Selecting a node highlights its edges and dims the rest. A fit-to-view button. Program filter as chips above the canvas instead of a dropdown, consistent with the Ledger's chip row. Nothing else; the graph is already the strongest part of this tab.

---

## 5. Schema proposals (batched, each needs a yes)

Per the standing rule: proposals with one-line rationales, not blockers. None are required for Sections 2 through 4.

1. **`departed` boolean + `departed_on` date on Person.** Champion departure is the highest-signal churn event in every reference platform, and today the model cannot even record it. A departed champion should fire an attention-queue item and render struck-through in roster and graph. Smallest possible version: one flag, one date.
2. **`internal_owner_id` on StakeholderRole.** Who on the Valence side owns this relationship. Enables "relationships with no owner" in the gap view. Defensible to skip while the tool is single-operator, since the answer is always you; becomes necessary the moment question 5 of §12 resolves toward team use.
3. **`touch_cadence_days` on StakeholderRole (nullable).** Role-graduated touch expectations, the ARPEDIO/Gainsight pattern: 7 for champions, 30 for budget owners, 90 for legal. Flat 21-day coverage treats a works-council contact like a champion. Null falls back to the current 21.
4. **`seniority` enum on Person (c_level, vp_plus, director, manager, ic).** The VP+ coverage stat currently rests on a title-string heuristic. One enum makes coverage math honest. Cheap, and title parsing is already lying-adjacent.

Recommended order if approved: 1 and 4 now (small, high-signal), 2 and 3 deferred until real use demands them, consistent with "evidence from real use" as the bar.

---

## 6. Order of work

1. Roster view with the shared `Table` primitive (Section 2). Depends on punch-list PR 3; build them together.
2. Person detail slide-over (Section 3). Highest value per hour in this brief.
3. Coverage gap grid and graph polish (Section 4).
4. Present Section 5 proposals for ruling; implement approved ones with migrations.

Each step is one PR, tests green, freshness language on every dated element from day one rather than as a later adoption pass. We know how that goes otherwise.

**Done when:** every fact the model holds about a person is reachable within one click of the People tab; an unfilled critical role is visually louder than a filled one; no dated element on the tab lacks an `AgeChip`; stance never renders in a status hue; and the tab answers "who am I neglecting and what seat is empty" in under five seconds, in both themes, without a schema change beyond whatever Section 5 items get approved.
