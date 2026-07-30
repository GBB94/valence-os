# Design audit — hard-coded values inventory

*Phase A deliverable (produced late, 2026-07-30). Companion to `DESIGN-GUIDE.md` §12.*

## Note on timing

This artifact was the fourth Phase-A deliverable and was not produced during Phase A — the token mapping was reported inline at the Phase-A checkpoint instead of committed as a file. It is committed now. Because Phases B–H have since landed on `main`, much of what an up-front audit would have flagged as "to convert" is **already converted**; this document records both the original inventory and the current state, so it doubles as the record of what the redesign changed.

Reconciliation with the corrective brief's headline numbers (which were measured against the pre-conversion tree):

| Metric | Brief (pre-conversion) | Now (on `main`) |
|---|---|---|
| Old-token references in `.jsx` | ~108 across 19 files | **0** — all renamed to new tokens in Phase H; alias shim deleted |
| Raw hex literals in `.jsx` | 15 in 2 files | **11 in 2 files** — all are chart `cssVar()` fallbacks (see §3) |
| Inline `style={{}}` blocks carrying px | ~245 across 24 files | 305 across 25 files (higher — new screens added: Ledger, primitives) |
| Legacy alias entries in `tokens.css` | present, 19 files depend | **removed** |

## 1. Color / token status — COMPLETE

Every `var(--old)` reference in `.jsx` and `index.css` was renamed to the new token. Mapping applied:

| Old | New |
|---|---|
| `--bg` | `--bg-app` |
| `--surface` | `--bg-surface` |
| `--surface-2` | `--bg-sunken` |
| `--border` | `--line-hairline` |
| `--border-strong` | `--line-strong` |
| `--text` | `--ink-primary` |
| `--text-2` | `--ink-secondary` |
| `--text-3` | `--ink-tertiary` |
| `--accent-weak` | `--accent-tint` |
| `--ok / --warn / --risk` | `--status-ok / -warn / -risk` |
| `--ok-bg / --warn-bg / --risk-bg` | `--status-*-tint` |
| `--radius` | `--r-md` |
| `--sans / --mono` | `--font-ui / --font-mono` |

`--toast-bg`, `--toast-fg`, `--scrim` were kept as real surface-role tokens (not aliases).

> **Update (corrective pass, same day):** §2, §3, and §4 below are now **FIXED** — see decisions D-67/D-68. Only §5 (inline spacing → `--sp`) remains deferred.

## 2. Raw hex still in `.jsx` — 11, all chart fallbacks (FIXED)

Canvas (Cytoscape) and SVG (Recharts) can't take `var()` in attributes, so charts resolve tokens via `getComputedStyle` with a literal fallback string. Those fallbacks are the only raw hex left:

| File | Lines | Values | Disposition |
|---|---|---|---|
| `views/StakeholderGraph.jsx` | 49–55 | `#14161C #fff #CDD2DA #868D9B #6A63D9` | Drop the fallbacks — tokens.css is imported before render, so `getComputedStyle` always resolves; the fallbacks never fire and several are light-theme values that would mispaint if they did. |
| `views/Waterfall.jsx` | 15–16 | `#5A6070 #1F8A54 #C0392F` | Same — drop the fallbacks. |

## 3. Categorical use of status color — FIXED (stance ruled to data family)

Green/amber/red must encode state only. Categorical encodings to move onto `--data-1…4`:

| File | Symbol | Encodes | Fix |
|---|---|---|---|
| `views/QBR.jsx:6` | `TYPE_COLOR` | evidence type (fact / interpretation / hypothesis / action) | `--data-*`; badges already carry a text label |
| `views/ValueLibrary.jsx:47` | visibility badge | visibility class (external/qbr-exec highlighted green) | `--data-1`; keep the label |
| `views/Timeline.jsx:113` | comms marker | event type | `--data-2` (milestone complete/incomplete stays status — that's a real state) |
| `views/StakeholderGraph.jsx:9` | `STANCE_VAR` | stakeholder stance | **CONFLICT**: corrective brief §3.2 says categorical → `--data-*`; `DESIGN-GUIDE.md` §8 says "fill encoding stance from the status family." Needs a ruling before change. |

Legitimate status uses that stay: freshness/staleness, pass/fail gates, on/off-target metric deltas, milestone complete-vs-pending.

## 4. Synthetic bold — FIXED

Only weights 400/500/600 are self-hosted; 700 is faked and banned by the guide.

| File | Line | Fix |
|---|---|---|
| `views/Operations.jsx` | 22 | `fontWeight: 700` → `600` |
| `views/Metrics.jsx` | (was 47) | already fixed in Phase F (moved to `.metric-value`, weight 500) |

## 5. Inline spacing px — DEFERRED (visually on-scale)

305 inline `style={{}}` blocks carry hard-coded px. Per-file counts (desc): StakeholderGraph 26, App 21, Metrics 20, Timeline 18, AccountDetail 17, ProgramDetail/Extraction 16, Operations/Commercial 15, QBR 13, Queue/Library/DeliveryPanel 11, Ledger 9, others ≤7.

Distinct values include off-ramp numbers **10 (21×) and 14 (18×)** plus structural widths (110, 120, 150, 200, 240, 320, 420, 460…). These are **visually identical to the `--sp` scale** where they land on it, and structural widths are one-off layout constants. Converting the on-scale ones to `--sp-*` and snapping 10/14 is **cosmetic-only polish** with no theming or contrast impact — deferred, not blocking. It is the remaining gap against the guide's "no arbitrary pixel values" line.

## Summary

- **Done:** all color tokenization (0 old-token refs), alias shim removed, self-hosted fonts, both themes.
- **To fix now (small, independent):** 11 chart hex fallbacks (§2), 3 categorical color misuses (§3), 1 weight-700 (§4), plus the stance ruling.
- **Deferred:** inline spacing px → `--sp` (§5) — cosmetic.
- **No new tokens needed;** no schema changes; backend and trust boundaries untouched.
