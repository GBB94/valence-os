# Redesign corrections
### Gap review of Phase A and in-flight Phase B, and what to fix before Phase C
*July 2026 · Companion to `DESIGN-GUIDE.md` · Branch `redesign-a-foundation`*

---

## 0. What this is

A corrective brief, not a new plan. `DESIGN-GUIDE.md` remains the design authority and its Section 12 work order still stands. This document lists what Phase A left undone, what the in-flight Phase B work needs to hold onto, and four defects worth fixing before the shell work starts.

Written against a working tree that was being edited at the time, so line numbers may have moved. Symbol names are given alongside them and are the reliable reference. Two items found during review (`fontWeight: 700` and the raw `rgba()` shadows in `App.jsx`) were already fixed while this was being written and are recorded here only so they do not get reintroduced.

Everything here fits inside the existing phase structure. Nothing below is a new feature, a new object, or a schema change.

---

## 1. The Phase A deliverable that is still missing

Phase A has four deliverables. Three landed: `tokens.css` with both themes, the five self-hosted Plex faces, and the standing-rules block in `CLAUDE.md`. The fourth did not.

> **Inventory every hard-coded color, size, and spacing value in the existing stylesheets into a mapping table, and report it before proceeding.**

No such artifact exists in the repo. Phase B began without it.

**Do this first.** Produce `design-audit.md` in the repo root and commit it. It is not paperwork, it is the work plan for Phases D and E, and right now nobody can size those phases without it.

Contents:

| Column | What goes in it |
|---|---|
| File and line | Where the hard-coded value lives |
| Current value | The raw hex, px, or rgba as written |
| Replacement | The token it maps to, or `NEW TOKEN NEEDED` |
| Phase | Which phase retires it |

Cover every `.jsx` file in `frontend/src/`, including inline `style={{}}` attributes, not just the stylesheets. Group by file, order by count descending, and put a summary table at the top with per-file totals. Where a value has no token, say so plainly rather than inventing one; batch those as proposals per the guide's Section 0 rule.

The known headline numbers to reconcile against, as of this review: roughly 245 inline style attributes carrying hardcoded pixels across 24 files, 15 raw hex literals in 2 files, and around 108 old-token references in `.jsx`. Off-scale values such as 10 and 14 appear throughout and are not on the 4px ramp.

**Report the table and stop.** That was the original instruction and it is the one gate in the whole work order placed before anything moves.

---

## 2. Rules for the legacy alias shim

Phase B added a temporary alias block in `tokens.css` mapping old token names onto new ones. This is the right call and it should stay. It also carries a risk worth naming: **19 of 25 view files depend on it, and no `.jsx` file uses a single new token.** The CSS layer is nearly converted while the JSX layer has not started, so the app will look finished long before it is.

Three rules while the shim exists.

1. **No new usages of aliased names.** Any file touched in Phases C through G moves to the new tokens in that same pass. The shim covers files nobody has opened yet, not files being actively edited.
2. **The shim shrinks monotonically.** Every phase from C onward removes alias entries it has made unnecessary. If a phase ends without the block getting shorter, that phase did not convert anything.
3. **Phase H does not inherit the bulk of it.** "Remove the shim" must not quietly become Phases D and E arriving at once on the last pull request. Track the remaining alias count in each phase's summary.

---

## 3. Defects to fix

### 3.1 Dark-mode fallbacks in the stakeholder graph (fix before Phase C)

`frontend/src/views/StakeholderGraph.jsx`, lines 49 to 54. The `v()` helper reads a computed CSS variable with a hardcoded fallback, and every fallback is a light-theme value:

```js
const labelColor  = v("--text", "#1a1d23");
const nodeBorder  = v("--surface", "#fff");
const edgeColor   = v("--border-strong", "#ccd1d9");
const edgeLabel   = v("--text-3", "#8a909c");
const reportsColor = v("--text-2", "#5b616e");
const accentColor = v("--accent", "#3b5bdb");
```

If a variable fails to resolve during canvas initialisation, the graph paints light-theme colors onto a dark surface. This is a live rendering bug rather than debt, and it lands on the one screen the guide calls the signature visual.

Fix by reading the new tokens and removing the hex fallbacks entirely. If a fallback is genuinely needed for initialisation ordering, resolve it from the token file rather than restating a color. Also fix line 174, `border: "1px solid #fff"`, which is `--bg-surface`.

Do not defer this to Phase G. The graph is currently wrong in dark mode.

### 3.2 Status colors used for categorical encoding

The guide's sharpest rule is that green, amber, and red encode state and nothing else. Four places break it, and each one is encoding a category rather than a health state:

| File | Symbol | What is actually being encoded |
|---|---|---|
| `views/QBR.jsx:6` | `TYPE_COLOR` | Evidence type. Green for confirmed fact, amber for internal interpretation. Reads as good and bad when it means fact and opinion. |
| `views/StakeholderGraph.jsx:9` | `STANCE_COLOR` | Stakeholder stance. Supporter and skeptic are political positions, not account health. |
| `views/ValueLibrary.jsx` | visibility class badge | Visibility classification. A record being externally referenceable is not a good outcome, it is a category. |
| `views/Timeline.jsx` | comms event marker | Event type. A comms event rendered in the warning hue is not a warning. |

All four move to `--data-1` through `--data-4`, which exist and are currently unused. Where the distinction still needs to survive without color, pair it with a shape or a label per the guide's Section 6 badge rule.

Two nearby cases are legitimate and stay: freshness and staleness indicators, and pass or fail states.

### 3.3 Tokens that exist for code that hardcodes around them

`views/Waterfall.jsx:9` hardcodes the exact colors the financial tokens were created for:

```js
const COLOR = { start: "#5b616e", add: "#2b8a3e", subtract: "#c92a2a", total: "#3b5bdb" };
```

Replace with `--fin-total`, `--fin-positive`, `--fin-negative`. The delta indicators in `views/Metrics.jsx` belong to the same family.

Currently unused across the whole codebase: the entire `--sp-1` through `--sp-11` spacing scale, `--data-1` through `--data-4` and `--data-muted`, all three `--fin-*` tokens, `--dur-fast`, `--dur-med`, `--ease`, `--accent-ring`, and `--status-unknown` with its tint. Several are scheduled for later phases and that is fine. The financial and categorical ones are not, because working code is hardcoding around them today.

### 3.4 Synthetic bold

`views/Metrics.jsx:47` and `views/Operations.jsx:22` still use `fontWeight: 700`. Only 400, 500, and 600 are self-hosted, so the browser fakes the weight and it renders worse than the 600 the guide permits. The guide bans 700 outright. `App.jsx` has already been cleaned; do not reintroduce it.

---

## 4. Documentation conflict

`README.md` and `HANDOFF.md` both still describe the project as being at its intended stopping point, and `HANDOFF.md` instructs a future session not to resume building. Neither mentions the redesign or `DESIGN-GUIDE.md` at all. `CLAUDE.md` says `DESIGN-GUIDE.md` is the standing design authority.

A fresh session reading `HANDOFF.md` first, as `HANDOFF.md` itself instructs, gets told to stop.

Fix both:

- **`HANDOFF.md`**: add a short paragraph near the top saying the redesign is live on branch `redesign-a-foundation`, that `DESIGN-GUIDE.md` governs it, and which phase is current. The existing "do not resume building features on your own initiative" line stays, because it is about product features and the redesign is not one. Say that explicitly so the two do not read as contradictory.
- **`README.md`**: the frontend is still described as "dense Linear-class UI, one neutral surface + one accent," which is the retired language. Update it, and note the redesign in the build-status section.

Also worth correcting: `App.jsx` still renders `Valence OS v0.1` in the brand block while the build is well past that.

---

## 5. Order of work

1. Produce and commit `design-audit.md`. Report the table and stop. (Section 1)
2. Fix the graph's dark-mode fallbacks. (Section 3.1)
3. Finish Phase B: complete the token conversion, retire whatever alias entries that makes redundant, and report the remaining alias count.
4. Fix the categorical color misuse, the waterfall and metric financial colors, and the two weight-700 sites, since all three are small and independent of the shell work. (Sections 3.2 to 3.4)
5. Update `HANDOFF.md` and `README.md`. (Section 4)
6. Log these as decisions in `decisions.md`, continuing from D-59, rather than waiting for Phase H.
7. Then Phase C.

Items 2, 4, and 5 can share one pull request. Item 1 gets its own and stops for review.

**Done when:** `design-audit.md` is committed and reviewed, the graph renders correctly in dark mode, no `.jsx` file contains a raw hex value or a `fontWeight: 700`, status hues appear only on state, the alias block is shorter than it is today, and `HANDOFF.md` tells a fresh session the truth about what is happening on this branch.

Tests stay green throughout. Nothing here touches backend code, generator logic, or the Section 2 trust boundaries, and nothing here is a schema change.
