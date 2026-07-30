# Redesign punch list
### Closing the gap between built and applied
*July 2026 · Companion to `DESIGN-GUIDE.md` · Supersedes `REDESIGN-CORRECTIONS.md`*

---

## 0. What this is, and what it replaces

An independent verification pass against `main` after Phases A through H and the corrective pass landed. `DESIGN-GUIDE.md` remains the design authority and nothing here changes it.

**This document supersedes `REDESIGN-CORRECTIONS.md`.** Almost everything in that file is now closed. Its few remaining open items are carried forward below. **Delete `REDESIGN-CORRECTIONS.md` in the first pull request off this list.** Two overlapping correction docs is the exact failure mode that cost a reconciliation pass last time.

Written against a tree with an inline-spacing sweep in flight, so line numbers may have moved. Symbol names are the reliable reference.

Nothing here is a new feature, a new object, or a schema change. Backend, generator logic, and the Section 2 trust boundaries are untouched by all of it.

---

## 1. Verified closed. Do not redo.

Confirmed against the working tree, not taken from a summary. Listed so no future session spends effort re-verifying.

| Item | Evidence |
|---|---|
| Legacy alias shim removed | No alias block in `tokens.css`; 0 legacy token references across `frontend/src/` |
| Old token references renamed | 0 remaining. The one `--toast-bg` hit is a live role token, not a shim |
| No raw hex or rgba in `.jsx` | 0 matches across every view. Chart `cssVar()` fallbacks correctly dropped |
| No synthetic bold | 0 occurrences of weight 700, 800, or 900 anywhere in `frontend/src/` |
| `design-audit.md` committed | Present at repo root, with the value-to-token mapping table |
| Four-destination navigation | Today, Accounts (with account children nested), Library, Operations |
| Rail, top bar, capture | 240px collapsing to 56px with persistence, 48px top bar, global capture on `c` with context prefill |
| Seven-tab account workspace | All seven tabs present with real content and correct tablist semantics |
| Ledger merge | Eight chips with live counts, master-detail at roughly 60/40, inbox pinned with the hatch treatment |
| Today | Single ranked list, three urgency bands, account as a column, no cards or tiles |
| Waterfall and charts on tokens | `--fin-*` on the waterfall, `--data-*` on sparklines and bullets |
| DESIGN-GUIDE §8 reconciled | Stance now documented as categorical, matching the code and D-67 |

The structural work is sound. Do not rebuild any of it.

---

## 2. The actual problem: built, then not adopted

Every remaining issue of consequence is the same shape. A component was built correctly to spec and then wired into a fraction of the places that need it. Treat Sections 3 and 4 as one problem, not two.

### 2.1 The freshness language is the priority

This is the guide's named signature and its own definition of done says the freshness language appears on **every** dated record. It currently appears on roughly four of fifteen dated surfaces.

`AgeChip` has two call sites in the entire application. `Unknown` has one. The decay ramp and the 45-degree hatch are implemented exactly to spec and then largely unused.

Wire `AgeChip` into every surface where a date is rendered. At minimum, the five the guide names explicitly:

| Surface | Current state |
|---|---|
| **Today** (`views/Queue.jsx`) | Renders `{it.age_days}d` by hand. No decay ramp, no tooltip. This is the screen where freshness matters most and it is the worst offender. |
| **Stakeholder last-touch** (`views/StakeholderGraph.jsx`) | No age chip |
| **Value stories** (`views/ValueLibrary.jsx`) | Raw dates via `fmtDate` |
| **Metric observations** (`views/Metrics.jsx`) | Raw dates via `fmtDate` |
| **Status assessments** (`App.jsx`) | Done already, leave it |

Then the rest: `Timeline`, `Commercial`, `Library`, `MutualActionPlan`, `Plays`, `Operations`, `AccountDetail`. The rule is simple and mechanical. **If a view imports `fmtDate` to render a record's own date, it should be rendering an `AgeChip` instead or alongside.** Use that as the sweep criterion.

Two fixes to the primitive itself while you are in there.

- **`ageDays` floors to whole days.** It slices the date string to `YYYY-MM-DD` and discards time, so anything under a day renders `today` and the guide's `4h` form can never appear. Fix it to compute from the full timestamp. Post-call capture is the core workflow and "logged 4h ago" is exactly the read the operator needs.
- **The attention rail is 3px, and the guide says 2px.** It is also colored by urgency band rather than by trigger class. Band is defensible if trigger class is too granular to read; if you keep it, say so in `decisions.md` and correct the guide so the two agree. Do not leave them contradicting each other.

### 2.2 Primitive adoption

`Btn`, `Card`, and `Badge` are defined in `ui.jsx` and imported by **zero** files. Every view still hand-writes `className="btn small"` and `className="card"`. Phase E's instruction was to replace ad hoc styling everywhere with the primitives.

The visual result is currently fine because the CSS classes are tokenized, so this is lower urgency than the freshness gap. It is still worth closing, because the point of the primitive is that the next change happens in one place.

- Adopt `Btn`, `Card`, and `Badge` across the views.
- **Build `Table` and `Input`.** Neither exists. Every view hand-rolls `<table>` against global rules and hand-rolls `<div className="field"><label><input>`. These are the two most repeated patterns in the app and the two the guide named first.
- Move `CommandPalette` out of `App.jsx` into `ui.jsx` and export it.
- `Chip` exists only as a `SegTabs` variant. Either promote it or note in `decisions.md` that the variant is the intended form.

---

## 3. Correctness defects

### 3.1 Stance still reads as health in the stakeholder table

D-67 ruled stance off the status family. The ruling was applied to the graph canvas and missed the shared primitive.

`StanceLabel` in `ui.jsx` emits `className={"stance-" + stance}` plus a status dot, and `index.css` maps `.stance-supporter` to `--status-ok` and `.stance-skeptic` to `--status-risk`. It renders in the stakeholders table on `ProgramDetail`. So the same categorical concept the ruling moved to `--data-*` is still painted green and red one screen over.

Move `StanceLabel` and its CSS to the data family and carry over the shape encoding already used on the graph, so the two representations of stance match. Also fix the power-interest grid fallback in `StakeholderGraph.jsx`, which falls back to `--status-unknown` where the canvas path correctly falls back to `--data-muted`.

This is the highest-value single fix on the list. It is the shared component, so it is the one place the rule most needed to hold.

### 3.2 The waterfall separation fails at screen level

The `Waterfall` component is clean. But it is not a screen, it is the third card on the Commercial tab, and that tab renders a status column with green dots above it. The sticky context header puts both account statuses over every tab including this one.

So `--fin-positive` green and `--status-ok` green are visible on one scroll surface, which is the confusion the rule exists to prevent. The guide says to enforce this in the layout rather than in a comment.

Pick one and record it in `decisions.md`:

- Move the waterfall to its own route or a full-height panel with the context header suppressed, or
- Accept that a tabbed workspace makes strict screen-level separation impossible, and narrow the guide's rule to "no status indicator inside the same card or panel as a financial chart."

The second is the honest answer if the tab architecture is staying. Either way the two documents must agree at the end.

### 3.3 Renewal countdown missing from the context header

The guide lists it as required in the sticky header, and it is absent. The comment in `AccountDetail.jsx` justifying the omission says renewal needs contracts from v1, but `Commercial.jsx` is already rendering `renewal_date` today. The justification is stale.

Add it, and delete the comment.

### 3.4 Density toggle does not produce the specified rows

The toggle works and persists. The CSS is padding-only with no row height and no line-height, so compact resolves to roughly 27px and default to roughly 37px rather than the specified 32 and 40. The code comment asserts the spec that the code does not implement.

Set the row heights properly. If a row-height token is wanted, propose it rather than hardcoding.

---

## 4. Cleanup

- **Delete the orphaned views.** `views/ExecutionBoard.jsx`, `views/History.jsx`, and `views/Inbox.jsx` are no longer imported by anything after the Phase D consolidation. They are dead code that will mislead the next session into thinking there are still separate execution and history screens.
- **Delete `REDESIGN-CORRECTIONS.md`.** Fully absorbed into this document.
- **Reconcile `design-audit.md`.** Its summary table still reports 11 raw hex literals when the actual count is zero, and the §3 row still reads as needing a ruling that D-67 already gave. The body was patched, the table was not. A stale audit is worse than no audit.
- **Finish or formally defer the inline spacing sweep.** In flight at the time of writing. If it completes, say so in `design-audit.md` §5 and close the item. If it is deferred again, record why.

---

## 5. Unverified claims worth closing out

These could not be verified from the repository, because they produce judgments rather than artifacts. Phase H asks for them and the guide's quality floor is non-negotiable.

- **Contrast audit in both themes,** 4.5:1 on every text and icon pairing, including every tint-on-surface combination. The guide warns that tints are where it usually fails and that passing in light says nothing about dark.
- **Keyboard audit,** tabbing through every screen in both themes with visible focus throughout, and full keyboard operation of Today, the Ledger, and the palette.
- **Before-and-after screenshots** of Today, an account Overview, the Ledger, and the graph, in both themes, which the work order asks for from Phase B onward.

If these were run, commit the evidence. If they were not, run them. Do not mark Phase H complete on the strength of an assertion.

---

## 6. Work order

Four pull requests, each independently revertible, tests green throughout.

**PR 1 — Freshness adoption.** Fix `ageDays` to use the full timestamp. Resolve the attention rail to 2px or correct the guide. Wire `AgeChip` into every view that currently imports `fmtDate` for a record's own date, starting with Today. This is the largest and most valuable of the four.

**PR 2 — Correctness.** `StanceLabel` to the data family with shape encoding, the `--status-unknown` fallback, the renewal countdown, the density row heights, and the waterfall separation ruling.

**PR 3 — Primitives.** Build `Table` and `Input`, adopt `Btn`, `Card`, and `Badge` across the views, move `CommandPalette` into `ui.jsx`.

**PR 4 — Cleanup and close.** Delete the three orphaned views and `REDESIGN-CORRECTIONS.md`, reconcile `design-audit.md`, close out the spacing sweep, then run the Section 5 audits and commit the evidence.

Log decisions in `decisions.md` continuing from D-68 as you go, not at the end.

---

## 7. Done when

- The freshness language appears on every dated record, not four of fifteen. No view renders a record's own date without it.
- `AgeChip` produces the hours form.
- Stance never renders in a status hue anywhere in the application.
- `Table` and `Input` exist and `Btn`, `Card`, and `Badge` have non-zero adoption.
- No orphaned view files, one correction document, and an audit whose numbers match the code.
- The contrast and keyboard audits have been run in both themes with evidence committed.
- Where the code and `DESIGN-GUIDE.md` disagree, one of them has been changed. No open contradictions between the two.
- Backend tests still pass and the Section 2 trust boundaries re-verified after the structural work, per the standing rule in `CLAUDE.md`.
