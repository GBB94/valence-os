# Design audit — hard-coded values inventory

*Phase A deliverable (produced late, 2026-07-30). Companion to `DESIGN-GUIDE.md` §12.*

## Note on timing

This artifact was the fourth Phase-A deliverable and was not produced during Phase A — the token mapping was reported inline at the Phase-A checkpoint instead of committed as a file. It is committed now. Because Phases B–H have since landed on `main`, much of what an up-front audit would have flagged as "to convert" is **already converted**; this document records both the original inventory and the current state, so it doubles as the record of what the redesign changed.

Reconciliation with the corrective brief's headline numbers (which were measured against the pre-conversion tree):

| Metric | Brief (pre-conversion) | Now (on `main`) |
|---|---|---|
| Old-token references in `.jsx` | ~108 across 19 files | **0** — all renamed to new tokens in Phase H; alias shim deleted |
| Raw hex literals in `.jsx` | 15 in 2 files | **0** — the chart `cssVar()` fallbacks were removed in the corrective pass (D-68) |
| Inline `style={{}}` blocks carrying px | ~245 across 24 files | ~300 across the views (higher — new screens: Ledger, primitives) — see §5 |
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
| `views/StakeholderGraph.jsx:9` | `STANCE_VAR` | stakeholder stance | **Resolved (D-67):** categorical → `--data-*` + node shape; `StanceLabel` primitive moved to match (D-70); DESIGN-GUIDE §8 updated. Stance is no longer a status hue anywhere. |

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

## 6. Contrast audit — both themes (RUN, evidence below)

WCAG 2.x contrast ratios, sRGB relative-luminance formula, computed (not estimated) for every text/icon pairing. Body/heading ink and status-risk already cleared 4.5:1 in both themes; the failures were concentrated in the smallest meta text, the low-saturation status hues used as *text* (not fills), and one dark accent-on-tint pairing. Six tokens were corrected. Threshold is **4.5:1** (normal text); the `11px` meta line is the tightest case and is held to the same bar rather than the 3:1 large-text allowance.

**Corrected pairings — all cross from failing to passing:**

| Pairing | Theme | Before | After |
|---|---|---|---|
| `--ink-tertiary` (11px meta) on surface | Light | 3.33 ✗ | **4.91 ✓** |
| `--ink-tertiary` (11px meta) on app | Light | 3.11 ✗ | **4.58 ✓** |
| `--status-ok` as text on surface | Light | 4.36 ✗ | **5.73 ✓** |
| `--status-ok` as text on its tint | Light | 3.84 ✗ | **5.06 ✓** |
| `--status-warn` as text on surface | Light | 4.20 ✗ | **6.21 ✓** |
| `--status-warn` as text on its tint | Light | 3.73 ✗ | **5.51 ✓** |
| `--ink-tertiary` (11px meta) on surface | Dark | 3.90 ✗ | **5.08 ✓** |
| `--ink-tertiary` (11px meta) on app | Dark | 4.22 ✗ | **5.49 ✓** |
| `--accent` text on `--accent-tint` | Dark | 4.26 ✗ | **4.54 ✓** |
| `--accent` text on `--bg-selected` (active nav) | Dark | 4.26 ✗ | **4.54 ✓** |

The dark accent fix was made by darkening `--accent-tint` and `--bg-selected` to the same value (`#191A33`) rather than lightening the accent, so the active-nav row and the accent-on-tint case pass with one change and the two backgrounds stay visually unified.

**Two non-token corrections in the same pass** (a light data hue as *text* can't clear 4.5:1, so the color moved to a mark and the text stayed ink):
- `StanceLabel` (`index.css`): stance text → `--ink-primary`; the data hue now rides only on the shaped mark (D-70).
- QBR evidence-type badge (`QBR.jsx`): category → a colored left border; label text stays ink.

**Spot-check of pairings left unchanged** (already passing, both themes): ink-primary 18.08 / 14.63, ink-secondary 6.62 / 7.46, status-risk-on-surface 5.43 / 5.29, status-risk-on-tint 4.66, accent-on-surface 8.51 / 4.71, dark status-ok/warn-on-surface 6.68 / 6.79.

**Keyboard + semantics:** reviewed statically — tables use `<table>/<th scope>`, the tablist carries `role="tablist"`/`aria-selected`, focus rings are a tokenized `--accent-ring` (not `outline:none`), and `prefers-reduced-motion` / `color-scheme` are honored. Not marked complete: a live tab-through of every screen in both themes, and **before/after screenshots** (Today, account Overview, Ledger, graph) — both pending a connected browser, tracked as the only open item from the punchlist's Section 5.

## Summary

- **Done:** all color tokenization (0 old-token refs), alias shim removed, self-hosted fonts, both themes, **0 raw hex in `.jsx`** (chart fallbacks removed), 0 synthetic bold, all categorical color misuses resolved (stance ruled to the data family, D-67/D-70), **contrast audited in both themes with six tokens corrected (§6)**.
- **Deferred:** inline spacing px → `--sp` (§5) — cosmetic-only, tracked below.
- **No new tokens needed;** no schema changes; backend and trust boundaries untouched.
- **Audits (§6 of this file):** contrast computed for both themes; keyboard/semantics reviewed. Screenshots pending a connected browser.
