# Valence OS — Design Guide
### Visual system and screen architecture — the standing design authority for the shipped frontend
*v6 · August 2026 · Companion to `Valence-OS-Scoping-Doc.md` §6, `UX-FOUNDATION-SPEC.md`, and `CLAUDE.md` · revised after the full-app adversarial design review, UX foundation pass, and cinematic-hybrid polish (D-113/D-114/D-116/D-124/D-125)*

---

## 0. What this document is, and what it is not

**This guide supersedes §6 of the scoping doc and the navigation the current build inherited from the §5 module list.** Where the two disagree, this document wins. The scoping doc's design section was written before anything existed; this one is written against a working app, so it replaces rather than supplements. The one-color-mode line and the one-destination-per-module structure are both explicitly retired here.

**Status (v6).** The redesign this guide originally briefed is shipped: the §12 phases are complete and the system below describes the app as built. This document is now the standing authority a session consults *before* changing the frontend, not a brief inviting restructure. v3 corrected the guide against the audited implementation; v4 closed the URL-addressability debt; v5 added restrained depth. v6 accepts a cinematic hybrid: a slow ambient shell, fine noise and grid texture, glass feature surfaces, gradient feature headings, layered shadows, selective cursor spotlights, and one-time panel reveals. Dense tables and repeated operational rows stay quiet, and parallax remains excluded.

**What still holds, and why.**

- **The trust boundaries in §2 of the scoping doc.** No field, column, or view anywhere for a named individual's product usage. Client-facing outputs include only affirmatively promoted records, enforced in code. Stakeholder assessments keep their date and evidence note. Stale metric-derived indicators never render as carried-forward good state. These are not scope ceremony. They are the reason the tool does not conflict with what Valence sells, and a redesign is exactly the moment they get broken by accident.
- **Behavior stays put unless the redesign requires otherwise.** Queue ranking logic, closure rules, and generator output are not visual concerns. If a layout change genuinely needs one to move, propose it.
- **Schema changes are proposals, not blockers.** If a screen would be materially better with a new field, batch the proposals with a one-line rationale each and surface them at the end of the phase rather than stopping the work or adding them silently.
- **Tests stay green,** and no new runtime dependencies beyond self-hosted font files.

---

## 1. Design thesis

**The subject.** One operator running a small number of very large, very consequential accounts. The work is remembering, noticing, and deciding. The tool's job is to make the state of an account legible in seconds and to make capture so fast it never gets skipped.

**The thesis: a cinematic instrument, not a dashboard.** Consumer dashboards persuade. This one reports. It should feel like a premium desktop tool: atmospheric housing around precise readouts, with the light and depth strongest at navigation, page identity, and decision summaries. Dense evidence stays optically quiet. Confidence still comes first from typographic discipline and exact alignment; atmosphere frames the work and never obscures it.

**The signature.** Two things carry the identity, and nothing else is allowed to shout.

1. **The freshness language** (Section 7). Every record shows its age in the same monospaced form, and everything derived from stale inputs renders as an explicit unknown rather than a carried-forward green. This is the scoping doc's principle 7 made visible, and it is the motif that runs through every screen.
2. **Selective atmospheric depth.** The shell and one feature surface per major workspace may be expressive. The stakeholder graph remains the richest analytical canvas; tables, rows, citations, and evidence surfaces do not inherit its glow.

**What to avoid.** Do not produce the current default AI-app looks: cream with a warm-clay accent and a high-contrast serif; near-black with one acid accent; or a broadsheet of hairlines and zero-radius columns. Also avoid the generic admin template: rounded white cards floating on gray with drop shadows and a stock blue primary button. If a screen could be dropped into any SaaS product without anyone noticing, it is wrong.

This tool is not Valence-branded and should not borrow their palette. It is an internal instrument with its own identity.

---

## 2. Screen architecture

The current build has roughly sixteen modules, most with their own navigation entry. Sixteen destinations is a menu, not an instrument, and it forces the operator to know which screen holds which fact before they can look anything up. The restructure below collapses navigation to three top-level destinations, moves everything account-scoped into one workspace with tabs, and makes capture globally available rather than a place you travel to.

### 2.1 Top-level navigation

```
Today            cross-account attention queue, the default screen
Accounts →       expands to accounts, each opening its workspace
Library          source references, files, search across everything
Operations       jobs, imports, backups, index health (bottom of rail, quiet)
```

### 2.2 The account workspace

One screen per account. A persistent context header, then a tab strip that never reloads the header.

> **Addressability (v4):** global destinations, account tabs, and program scope are canonical URL destinations. Refresh and direct loading restore the same context; Back/Forward traverse prior Valence destinations. `/` normalizes to `/today`, invalid routes fail closed, and FastAPI serves the SPA entry point only for extensionless non-API navigation paths. Saved Today and Accounts views use the `view` query parameter.

| Tab | Merges today's modules | The question it answers |
|---|---|---|
| **Overview** | account/program overview | Where does this account stand right now |
| **Ledger** | interaction history + execution board + capture inbox | What happened, what was promised, what is open |
| **People** | stakeholder map + coverage sidebar | Who matters, who is exposed, who has not been touched |
| **Plan** | timeline + deployment moments + phase gates + compliance lanes | What is scheduled, what is gating, what is ready |
| **Commercial** | expansion opportunities + contracts + waterfall | Where the money is and what has to be true to get it |
| **Evidence** | metrics scoreboard + benchmarks + value story library | What we can prove, and how fresh the proof is |
| **Outputs** | QBR generator + team update + MAP + pre-call briefing | What we hand to someone else |

Program scoping is a filter inside the workspace, not a separate branch of the navigation tree. A program selector sits in the context header; choosing one filters every tab. This matters because an F100 account is genuinely multi-program, and the old model forced you to choose between account-level and program-level views before you knew which one you needed.

The seven tabs above are the recommended arrangement, not a ceiling. If building them surfaces a better grouping, take it and say why. The test is whether a question the operator actually asks can be answered without visiting two tabs.

As built, the workspace carries an eighth tab — **Internal** (Stage 10 forecasting, asks, reviews) — and the busiest tabs subdivide with a `SegTabs` strip (Commercial: Whitespace, Value ledger, Funding, Signals, Company, Growth & renewal, Pipeline & contracts). A new surface almost always becomes a sub-tab of an existing tab, not a ninth tab; a ninth tab requires the same justification as a new top-level destination.

### 2.3 The Ledger merge (the most consequential change)

Interactions, tasks, commitments, decisions, risks, and issues are currently separate surfaces. They are all the same shape: a dated thing, with an owner, a state, and a link back to the interaction that produced it. Splitting them means the answer to "what is going on with this account" requires visiting five screens.

Build the Ledger as one chronological, filterable table with a type filter chip row across the top (All, Interactions, Commitments, Tasks, Decisions, Risks, Issues, Inbox) and a count on each chip. Default view is All, newest first. Untriaged capture-inbox items pin to the top of the list with the unknown treatment until they are converted, which makes triage a thing you do in passing rather than a chore on its own screen.

Use master-detail here rather than a slide-over: list on the left at roughly 60 percent, detail pane on the right. This is the screen you dwell in, and a panel that covers the list makes comparing records impossible.

### 2.4 Capture is global, not a destination

The 30-second rule should be structural, not aspirational. Capture is available from anywhere by keyboard (a dedicated shortcut, and via the palette) and from a persistent affordance in the top bar. It opens as a slide-over, prefills the account and program from wherever you were standing, and never requires navigating away from what you were doing. Closing it returns you exactly where you were.

### 2.5 Today

A single ranked list, grouped by urgency band rather than by account, with the account name as a column. A compact three-band summary names the volume in each urgency band; it is navigation context, not a KPI dashboard, and introduces no score or trend chart. Every row carries the trigger reason in plain text, its age, its due date, and one primary action inline. Snooze and resolve are row actions. This screen exists to be emptied.

Today and the Accounts Book also carry built-in and operator-saved views. Saved views are presentation preferences, not copied account data: they store filters and sort state locally for the current single-editor product, show when the active arrangement has been modified, and fail closed to the built-in default if a referenced custom view is unavailable or corrupt. The reusable contract and team-era migration path are in `UX-FOUNDATION-SPEC.md` §5.2.

### 2.6 Progressive disclosure

The default state of every screen shows the answer, not the raw material. Depth is one interaction away, never zero and never three. Concretely: Overview shows statuses and the top three risks, with a link into the full register; Evidence shows five to nine metric cards with sparklines, with the observation history behind a click; Commercial shows the pipeline and the waterfall, with contract versions in a panel.

---

## 3. Space, grid, and shell

**Spacing scale.** 4px base. Use only 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, exposed as `--sp-1` through `--sp-11`. The scale governs **space** — padding, margins, gaps. It does not govern fixed component dimensions (rail, top bar, control heights, panel widths), which are named once below and in `tokens.css`/`index.css`, nor the derived table paddings computed to hit the 32px/40px row heights. Off-scale spacing in a view is a violation; a new fixed dimension requires naming it here.

```
┌──────────┬──────────────────────────────────────────────────────┐
│          │  top bar 48px: breadcrumb · search · capture · ⌘K ·   │
│  rail    │                          density · theme              │
│  240px   ├──────────────────────────────────────────────────────┤
│          │  context header (sticky): account · program selector  │
│ Today    │  delivery status · commercial status · renewal · phase│
│ Accounts ├──────────────────────────────────────────────────────┤
│  ├ acct  │  tab strip: Overview Ledger People Plan Commercial …  │
│  └ acct  ├──────────────────────────────────────────────────────┤
│ Library  │                                                       │
│ ───────  │  content, 24px gutters, full width                    │
│ Ops      │                          ┌────────────────────────┐   │
│          │                          │ slide-over 480px       │   │
└──────────┴──────────────────────────┴────────────────────────┴───┘
```

- **Left rail, 240px**, collapsible to 56px icons, state persisted, and auto-collapsing below 1000px viewport width (the §11 split-screen case); the operator can re-expand explicitly. Active item uses `--bg-selected` with a 2px accent bar on the leading edge, never a filled pill.
- **Top bar, 48px**, does not scroll away. Holds breadcrumb, global search, the capture affordance, the density toggle, and the theme toggle.
- **Context header**, sticky beneath the top bar, present on every account tab. Account name, program selector, both statuses with their assessed dates, renewal countdown, phase. This is the ten-second read and it must never require scrolling to find.
- **Content**, full width, 24px gutters, no centered max-width container. This is a data tool on a large screen. Prose blocks inside panels cap their own measure at roughly 70 characters.
- **Slide-over, 480px** (as built; v2 said 520 — the narrower panel won on split-screen widths), right side, `--shadow-panel`, scrim from `--scrim`. Used for detail views everywhere except the Ledger, which uses master-detail. Keyboard contract is non-negotiable: Escape closes, Tab cycles inside, focus returns to the opener (`SlideOver` in `ui.jsx` implements it — never hand-roll a panel). Blocking modals are reserved for destructive confirmation only; `window.prompt()` is never acceptable.

---

## 4. Color tokens

Cool graphite neutrals with a single ink-indigo accent. The accent deliberately avoids the green, amber, and red families, because those are reserved for status and an interactive control must never be confusable with a state.

Define these once in `tokens.css` — **it is the canonical source**. The blocks below mirror it for reference and carry the post-audit corrections (several v2 values failed the §11 floor this guide itself imposes). Nothing in the app may use a raw hex value outside that file. If this guide and `tokens.css` ever disagree, `tokens.css` plus the audit win, and this guide gets corrected in the same change.

### 4.1 Light (default)

```css
:root {
  /* Surfaces */
  --bg-app:        #F4F5F8;
  --bg-surface:    #FFFFFF;
  --bg-elevated:   #FFFFFF;
  --bg-translucent: rgba(255,255,255,.88);
  --bg-glass:      rgba(255,255,255,.72);
  --bg-sunken:     #EFF1F4;
  --bg-hover:      #F2F4F7;
  --bg-selected:   #EEEEFC;
  --surface-highlight: rgba(255,255,255,.72);
  --surface-highlight-subtle: rgba(255,255,255,.34);
  --ambient-page: rgba(58,52,196,.035);
  --ambient-primary: rgba(58,52,196,.13);
  --ambient-secondary: rgba(90,79,196,.075);
  --ambient-tertiary: rgba(63,93,180,.055);
  --ambient-graph: rgba(58,52,196,.10);
  --ambient-surface: rgba(58,52,196,.095);

  /* Lines */
  --line-hairline: #E3E6EB;
  --line-strong:   #CDD2DA;
  --line-hover:    #B8BEC8;

  /* Ink */
  --ink-primary:   #14161C;
  --ink-secondary: #565D6B;
  --ink-tertiary:  #646A75;  /* v2's #868D9B was 3.33:1 — under the floor as meta text */
  --ink-inverse:   #FFFFFF;

  /* Accent (interaction only, never state) */
  --accent:        #3A34C4;
  --accent-hover:  #2F2AA6;
  --accent-tint:   #ECEBFA;
  --accent-ring:   rgba(58, 52, 196, 0.35);

  /* Status (state only, never decoration) */
  --status-ok:           #167544;  /* darkened from v2's #1F8A54 to clear 4.5:1 on tint */
  --status-ok-tint:      #E6F4EC;
  --status-warn:         #8A5500;  /* darkened from v2's #B26B00 for the same reason */
  --status-warn-tint:    #FBF0DF;
  --status-risk:         #C0392F;
  --status-risk-tint:    #FBEAE8;
  --status-unknown:      #868D9B;
  --status-unknown-tint: #F0F1F4;

  /* Financial direction (the documented exception) */
  --fin-positive:  #1F8A54;
  --fin-negative:  #C0392F;
  --fin-total:     #5A6070;

  /* Categorical data (charts, graph, non-status encodings) */
  --data-1: #3A34C4;
  --data-2: #6A63D9;
  --data-3: #9A95E8;
  --data-4: #C6C3F2;
  --data-muted: #C3C8D1;

  /* Radii and elevation */
  --r-sm: 4px;
  --r-md: 8px;
  --r-lg: 12px;
  --r-xl: 16px;
  --r-pill: 999px;
  --shadow-inset: inset 0 1px 0 rgba(255,255,255,.80);
  --shadow-control: 0 1px 2px rgba(20,22,28,.06), inset 0 1px 0 rgba(255,255,255,.72);
  --shadow-primary: 0 0 0 1px rgba(58,52,196,.12), 0 4px 12px rgba(58,52,196,.16), inset 0 1px 0 rgba(255,255,255,.20);
  --shadow-panel: 0 1px 2px rgba(20,22,28,.05), 0 12px 32px rgba(20,22,28,.10);
}
```

### 4.2 Dark

Not pure black. Dense text on true black causes halation and makes hairlines impossible to place. The dark surface is a deep cool graphite, the accent lightens to hold contrast, and the status hues desaturate so they do not glow.

```css
[data-theme="dark"] {
  --bg-app:        #050609;
  --bg-surface:    #0D0F14;
  --bg-elevated:   #12151C;
  --bg-translucent: rgba(8,10,14,.80);
  --bg-glass:      rgba(14,16,22,.68);
  --bg-sunken:     #080A0F;
  --bg-hover:      #151923;
  --bg-selected:   #191A33;
  --surface-highlight: rgba(255,255,255,.065);
  --surface-highlight-subtle: rgba(255,255,255,.032);
  --ambient-page: rgba(124,116,240,.11);
  --ambient-primary: rgba(94,106,210,.26);
  --ambient-secondary: rgba(110,76,198,.14);
  --ambient-tertiary: rgba(66,99,190,.11);
  --ambient-graph: rgba(124,116,240,.22);
  --ambient-surface: rgba(124,116,240,.16);

  --line-hairline: #20242C;
  --line-strong:   #303640;
  --line-hover:    #454D5A;

  --ink-primary:   #E8EAEE;
  --ink-secondary: #A2A9B6;
  --ink-tertiary:  #838A98;  /* v2's #6F7784 was 3.90:1 — under the floor as meta text */
  --ink-inverse:   #08090C;

  --accent:        #7C74F0;
  --accent-hover:  #948DF5;
  --accent-tint:   #191A33;  /* darkened so accent text on it clears 4.5:1 (v2: #1E1F3D, 4.26) */
  --accent-ring:   rgba(124, 116, 240, 0.40);

  --status-ok:           #3FB37F;
  --status-ok-tint:      #12291F;
  --status-warn:         #D9922B;
  --status-warn-tint:    #2B2113;
  --status-risk:         #E5645A;
  --status-risk-tint:    #2E1A18;
  --status-unknown:      #6F7784;
  --status-unknown-tint: #1A1D22;

  --fin-positive:  #3FB37F;
  --fin-negative:  #E5645A;
  --fin-total:     #A2A9B6;

  --data-1: #7C74F0;
  --data-2: #948DF5;
  --data-3: #ADA8F8;
  --data-4: #C9C5FB;
  --data-muted: #454B55;

  --shadow-inset: inset 0 1px 0 rgba(255,255,255,.055);
  --shadow-control: 0 1px 2px rgba(0,0,0,.30), inset 0 1px 0 rgba(255,255,255,.060);
  --shadow-primary: 0 0 0 1px rgba(124,116,240,.22), 0 4px 12px rgba(124,116,240,.18), inset 0 1px 0 rgba(255,255,255,.16);
  --shadow-panel: 0 1px 2px rgba(0,0,0,.40), 0 12px 32px rgba(0,0,0,.50);
}
```

**Theme mechanics.** Three states in the top-bar toggle: System, Light, Dark. System reads `prefers-color-scheme` and updates live. The choice persists to localStorage and applies via `data-theme` on the root element before first paint, using a tiny inline script in the HTML head so there is no flash of the wrong theme. Set `color-scheme` on the root so native form controls and scrollbars follow. Both themes are audited for contrast independently; passing in light does not mean passing in dark, and the tints are where it usually fails.

**Rules of use.**

- Green, amber, and red appear only to encode state. Never for emphasis, never for branding, never on a chart other than the budget waterfall.
- The waterfall is the single documented exception. Because the app is a tabbed workspace with a sticky status header, strict screen-level separation is impossible; the enforceable rule is that **no status indicator appears inside the same card or panel as a financial chart**. Enforce this in the layout, not in a comment. (Narrowed from "same screen" — D-70.)
- Outer elevation is rare. Tables, cards, and panels separate with hairlines and may share the single tokenized inset top-edge highlight. Secondary controls use the shared compact control shadow; the one primary action may use the restrained accent shadow. Only the slide-over, command palette, and toasts receive panel-scale outer elevation.
- Tints back badges and selected rows only. Never tint a large surface.
- **`--status-unknown` is a fill-and-hatch hue, never ink.** It fails 4.5:1 as text or as a glyph on every surface in both themes. Neutral and no-signal states draw their glyphs, counts, and labels in `--ink-secondary`; the unknown hue appears only in tints, hatches, and marks paired with a label. (This was buried in §8's whitespace notes in v2, and exactly the surfaces that hadn't read §8 violated it.)
- **`--accent` and `--data-1` share a value by design, and the distinction is semantic.** Data encodings (chart series, timeline markers, reference lines) must reference `--data-*`; interactive affordances must reference `--accent`. The pixels match today; the tokens must not be swapped, or a future palette change silently recolors one as the other.

---

## 5. Typography

**Faces.** IBM Plex Sans for the interface, IBM Plex Mono for numerics, identifiers, timestamps, and freshness chips. Plex has real tabular figures, an engineered rather than fashionable personality, and it is not the face every AI-generated app currently ships with. Self-host woff2 at 400, 500, 600 for Sans and 400, 500 for Mono. No CDN, no additional families, no serif. The one permitted alternative if Plex ever reads as dated is Geist Sans with Geist Mono, same weights, same rules. Do not mix them.

**Scale.** Compact, built for density. Base UI text is 13px, because this tool is read the way a terminal is read.

```css
:root {
  --font-ui:   "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, monospace;

  --t-micro:   11px;
  --t-small:   12px;
  --t-body:    13px;
  --t-body-lg: 15px;
  --t-h3:      16px;
  --t-h2:      20px;
  --t-h1:      26px;
  --t-metric:  32px;
}
```

| Role | Size | Weight | Line height | Tracking | Case |
|---|---|---|---|---|---|
| Eyebrow / table header | 11px | 500 | 16px | +0.04em | UPPERCASE |
| Metadata / timestamp | 12px mono | 400 | 16px | 0 | as written |
| Body / cell | 13px | 400 | 20px | 0 | sentence |
| Emphasised cell | 13px | 500 | 20px | 0 | sentence |
| Panel prose, empty state | 15px | 400 | 24px | 0 | sentence |
| Section heading | 16px | 600 | 22px | -0.01em | sentence |
| Screen heading | 20px | 600 | 26px | -0.015em | sentence |
| Account name | 26px | 600 | 32px | -0.02em | sentence |
| Scoreboard metric | 32px mono | 500 | 36px | -0.02em | numerals |

**Non-negotiables.** `font-variant-numeric: tabular-nums` globally, and mono for anything in a column of numbers, a date, a duration, a seat count, a currency figure, or an ID. Weight 700 is never used; hierarchy comes from size, color, and space. Because no 700 face is even loaded, headings must set their weight explicitly in CSS (`h1`–`h4` at 600) — a bare heading element left to the browser's `bold` is a bug, not a style. Sentence case everywhere except the 11px eyebrow. One number format per column, decimals included.

---

## 6. Components

### Tables (the primary surface)

- Two densities, **compact 32px** and **comfortable 40px** rows (`data-density` `compact|default`), driven by the top-bar toggle and persisted. Compact is the default.
- Header row: 11px uppercase eyebrow, `--ink-secondary`, sticky on scroll, 1px `--line-strong` beneath. Header alignment always matches its column's content.
- Rows separated by 1px `--line-hairline`. No vertical rules, no zebra striping.
- Text left, numbers and dates right, nothing centered. Right-aligned columns use mono so decimals stack.
- Hover: `--bg-hover` across the full row; row actions appear on hover at the right edge instead of occupying a permanent column.
- Selected: `--bg-selected` plus a 2px accent leading edge, surviving scroll.
- Focus: 2px `--accent-ring` outline on the focused row or cell, always visible, never color-only.
- Truncate with ellipsis and a title attribute; never wrap in compact mode. Repeated qualifiers move into the column header.

### Cards and panels

Hairline border, `--r-lg`, layered `--shadow-card`, and a top-edge highlight. Ordinary cards use `--bg-surface`; feature surfaces may use `--bg-glass`, backdrop blur, and a cursor-following radial highlight. Feature use is selective: page identity, lens control, decision summary, learned-motion cards, and relationship analysis. Tables remain opaque and do not lift. View code consumes the shared tokens and `Card spotlight`; it never invents a glow. A card groups; it does not decorate.

### Buttons

| Variant | Use | Style |
|---|---|---|
| Primary | The one action the screen exists for | `--accent` fill, `--ink-inverse`, `--r-md`, 13px/500, 30px (26px in `.small`) |
| Secondary | Everything else | `--bg-surface`, `--line-strong` border, `--ink-primary` |
| Ghost | In-row and toolbar actions | transparent, `--ink-secondary`, hover `--bg-hover` |
| Danger | Destructive only | `--status-risk` on `--status-risk-tint`; filled only inside a confirm dialog |

One primary per screen maximum; row-level and repeated actions are secondary or ghost, never primary, and `.primary` is never a selected-state for toggle groups — that is what `SegTabs` is for. The shared button primitive owns the inset highlight, restrained primary-action shadow, hover border, and `0.98` pressed scale; view code does not reproduce them. Labels are verbs naming the outcome: "Log interaction," "Convert to commitment," "Promote to plan." Never "Submit," never "OK." Inline navigation rendered as a link uses the `.linklike` button class — a bare `<a onClick>` is not keyboard-reachable and is a violation, not a shorthand.

### Inputs

32px compact, `--line-strong` border, `--r-md`, 13px. Focus swaps border to `--accent` and adds a 3px ring. Labels above in 11px eyebrow style. Errors beneath in `--status-risk`, stating the next move rather than the failure.

### Badges and chips

11px, 500, pill radius, 2px/6px padding, tint background with matching solid ink. Status badges pair color with shape: filled dot for on track, hollow for at risk, cross-hatched for unknown. State never depends on color alone.

### Empty states

Left-aligned in the panel, not centered hero blocks. One line of 15px prose saying what belongs here, and one secondary button that creates the first one. "No commitments yet. The first ones usually come out of the kickoff call." No illustrations.

### Toasts

Bottom-left, three seconds, `--shadow-panel`. The verb matches the button that caused it: "Publish" produces "Published."

### Command palette

Centered overlay at 640px, `--shadow-panel`, mono shortcut hints, results grouped under 11px eyebrow headers. Fastest path to any account, person, or record, plus capture. Opens instantly, searches as you type.

---

## 7. The freshness language (the signature)

Build this once as a small set of components and use it everywhere.

**Age chip.** Mono, 11px, `--ink-tertiary`, relative age in the shortest honest form: `4h`, `6d`, `3w`, `14mo`. Appears on interactions, stakeholder last-touch, metric observations, status assessments, and value stories. Absolute timestamps live in the tooltip, never in the row.

**The decay ramp.** Age is encoded consistently, so a screen full of aging records looks aging.

| Bucket | Treatment |
|---|---|
| Fresh, 0 to 7 days | `--ink-secondary`, normal |
| Aging, 8 to 21 days | `--ink-tertiary`, normal |
| Stale, 22 days or more | `--ink-tertiary` with a 1px dotted underline |
| Past threshold | Renders as unknown, below |

**The unknown treatment.** When a metric-derived indicator's inputs pass their freshness threshold, it does not show its last value in green. It shows a cross-hatched tint (`--status-unknown-tint` with a 45-degree 1px hatch), the label "Unknown," and the age chip explaining why. Manually assessed delivery and commercial statuses behave differently, per the doc: they keep their color but gain a dotted outline and an age chip once past the 30-day reassessment interval.

**The cross-hatch carries a second meaning: withheld.** Suppressed cohorts under the privacy floor, attendance the system refuses to guess (Stage 13), and coverage the sources cannot support (Stage 14) render with the same hatch (`.unknown-chip`, `.unknown-fill`) and always with the reason in text. Stale and withheld are deliberately the same weight — both mean "do not read a value here" — and the reason text is what distinguishes them. A withheld value rendered as plain prose is a defect, not a simplification.

**The attention rail.** On Today, each row carries a 2px leading edge colored by **urgency band** (the queue's ranking band, which is what the operator scans by — trigger class proved too granular to read as a color). Beside it, the reason renders as 11px plain text, because the doc requires every item to explain itself and a colored bar explains nothing.

---

## 8. Visualizations

All inherit the tokens; none introduce a palette.

**Stakeholder graph.** The one expressive surface. Full-bleed canvas on `--bg-app`, nodes on `--bg-surface` with hairline strokes, size encoding influence, fill **and node shape** encoding stance from the **categorical data family** (`--data-*`) — stance is a position, not account health, so it is not a status hue, and the shape lets it read without color — edge thickness encoding relationship strength, arrowheads encoding direction. Reporting edges solid in `--line-strong`; influence and sponsorship edges dashed in `--data-2`. Labels at 11px, on hover or above a zoom threshold. Clicking opens the standard slide-over. The power-interest grid is a toggle, not a second screen, sharing node styling.

**Budget waterfall.** `--fin-positive`, `--fin-negative`, `--fin-total`, direct value labels in mono on every bar, no legend, no truncated axis, minor sources grouped with subtotals. No status indicator may appear in the same card or panel as this chart (D-70).

**Sparklines and bullet charts.** `--data-1` for the measure, `--data-muted` for qualitative bands, a 1px `--ink-primary` target marker. One baseline, no gridlines, no axis labels on sparklines.

**Whitespace heatmap** (Commercial tab's signature surface, Stage 5.5). The obvious way to build this would introduce a second non-status color system alongside the waterfall exception. It doesn't: **the cell states are statuses**, so the grid is drawn from the existing status palette and the "waterfall is the single documented exception" rule above stands unamended.

- **Hue reuses the status family.** Penetrated → `--status-ok`; Penetrated-unevidenced and Proven → `--status-warn`; Blocked and Declined → `--status-risk`; Target and White → `--status-unknown`. No new color enters the system.
- **Seven states over four hues, so hue never distinguishes a state on its own.** Every cell carries a **glyph and a text label** (`● ◐ ◑ ○ · ▲ ✕`). This is the standing no-color-alone rule doing real work: it is what keeps Penetrated and Penetrated-unevidenced legible side by side.
- **The two neutral states draw their glyph in `--ink-secondary`, not `--status-unknown`.** Measured on the unknown tint, `--status-unknown` gives 3.74:1 — under the floor. "No status" has no hue to carry anyway, so neutral ink is both more legible and more honest.
- **Fill intensity encodes paid density only**, as a `color-mix` ramp of the state's own hue into its tint. Intensity is never the difference between two states. Audited: worst contrast 4.66:1 (light) and 4.93:1 (dark) across every state's label, glyph, and meta text.
- **Suppressed cells** (cohort below the account's minimum size) use the standard cross-hatched unknown treatment with the reason, never a zero.
- **Semantic table**, `scope`-associated row and column headers, arrow-key cell navigation, and a per-cell accessible name reading population, use case, state, paid seats, and density — the map is usable without seeing it.
- **D-70 extends here:** the heatmap is a status surface, so the budget waterfall never shares its card or panel.

**Evidence and grounding surfaces (Stages 12–14).** The copilot, campaign measurement, and company-intelligence work introduced a shared visual vocabulary; it is authority now, not convention:

- **Evidence coverage is a word, never a number.** `supported / partial / conflicted / insufficient` render as badges (color + label). A numeric confidence badge, score, or percentage of certainty is prohibited anywhere in the app — the Stage 12 rule generalized.
- **Citations** are mono chips (`[p001]`) attached to the bullet they support; a factual line without one does not ship. Source rows expose the snapshot fields behind the claim.
- **Span quotes** — an exact public-source excerpt — render as a bordered blockquote carrying publisher, date (with age chip), and locator. The quote is evidence; it never restyles as decoration.
- **Proposal lifecycle glyphs**: `◇ proposed · ● confirmed · × dismissed · ! invalidated`, always glyph *and* label. Proposed records are visually review material and never blend into confirmed content.
- **The outside-in marker** (`⚑ n` on whitespace headers) is annotation, never state: it must not alter cell hue, glyph, or derived state, must be focusable, and must carry its summaries in the accessible name — hover-only tooltips cannot be the sole path to content.

---

## 9. Motion

```css
--dur-fast: 120ms;
--dur-med:  180ms;
--dur-standard: 240ms;
--ease: cubic-bezier(0.2, 0, 0, 1);
--ease-expo: cubic-bezier(0.16, 1, 0.3, 1);
```

Slide-overs translate from the right. The palette fades and scales from 0.98. Buttons and filter controls transition color, border, shadow, a restrained shine, and a `0.98` pressed scale using expo-out timing. The shell carries three large, blurred ambient light pools on a slow ten-second loop; feature headers and top-level panels reveal once over 600ms; spotlight surfaces track the pointer; selected feature cards may lift by 2px or less. Dense rows never translate, and there is no scroll parallax, spring motion, continuous text shimmer, or skeleton animation beyond a single quiet pulse. `prefers-reduced-motion` disables ambient movement, cursor tracking, and reveal motion.

---

## 10. Interface copy

Copy is design material and moves with this work. Buttons name the outcome, and the verb persists into the confirmation. Labels use the operator's vocabulary rather than the schema's: "Last touch," not `last_interaction_at`; "Who's driving it," not `internal_owner_id`. Errors say what happened and the next move. Empty states invite the first action. Sentence case throughout, no exclamation marks, no apologies.

---

## 11. Quality floor

Ship none of this without all of it.

- 4.5:1 contrast minimum on every text and icon pairing, audited separately in light and dark, including every tint-on-surface combination.
- Visible keyboard focus on every interactive element, verified by tabbing through each screen in both themes. The mechanism is global and lives in `index.css`: `:focus-visible` gets a 2px `--accent` outline, and text inputs swap it for the accent border + 3px `--accent-ring`. A component that suppresses it must replace it with something at least as visible.
- No state conveyed by color alone; every status pairs color with a shape or a label.
- Real semantic tables (`table`, `thead`, `th` with `scope`) so assistive tech gets the relationships. Full keyboard operation of Today, the Ledger, and the palette.
- No flash of incorrect theme on load.
- `prefers-reduced-motion` and `color-scheme` both honored — the reduce block in `index.css` collapses every transition and animation to effectively instant; `color-scheme` is set per theme in `tokens.css`.
- Readable at 1280px and usable split-screen beside a video call at roughly 900px, where the rail auto-collapses to icons (below 1000px; the operator can re-expand). Containers scroll horizontally when content is genuinely wider — `overflow: hidden` that clips table columns is a defect. This is not a phone app.

---

## 12. Work order

**Historical — Phases A–H shipped.** Retained because the discipline it encodes (independently revertible steps, tests green throughout, before/after both-theme screenshots) is the template for any future visual work. The §11 audit is now executable rather than aspirational: the D-113 review walked every screen's computed styles in both themes programmatically — contrast ratios, overflow, focus — and that is the standing verification method for any change that touches tokens or shared components.

One phase per pull request, each independently revertible, tests green at every step. Capture before-and-after screenshots of Today, an account Overview, the Ledger, and the graph, in both themes from Phase B onward.

**Phase A — Foundation and audit.** Create `tokens.css` with both themes and a typographic reset. Self-host the fonts. Inventory every hard-coded color, size, and spacing value in the existing stylesheets into a mapping table, and report it before proceeding. No structural changes yet.

**Phase B — Theming.** Wire the three-state theme toggle, the pre-paint script, `color-scheme`, and persistence. Convert existing styles to tokens so both themes render correctly before any layout work begins.

**Phase C — Shell and navigation.** The 240px rail with the new three-destination structure, the 48px top bar, the sticky context header with the program selector, the tab strip, the slide-over pattern, the density toggle, and global capture.

**Phase D — Screen architecture.** The consolidation in Section 2: build the account workspace tabs, merge the Ledger with its filter chips and master-detail layout, rebuild Today as a single ranked list, and fold the remaining modules into their tabs. This is the largest phase; if it needs splitting, do the Ledger first and the rest second.

**Phase E — Primitives.** Table, card, button, input, badge, chip, empty state, toast, tooltip, palette. Replace ad hoc styling everywhere with these.

**Phase F — Freshness language.** Age chip, decay ramp, unknown treatment, attention rail, applied wherever a date or derived status appears.

**Phase G — Visualizations.** Graph, waterfall, sparklines and bullets retokenized in both themes. Confirm the waterfall screen carries no status indicators.

**Phase H — Copy, audit, and close.** Screen-by-screen pass against Sections 10 and 11, contrast and keyboard audits in both themes, a re-verification that the §2 trust boundaries still hold after the restructure, then update `HANDOFF.md`, log the design decisions in `decisions.md`, and present any batched schema proposals.

**Definition of done.** No raw hex or arbitrary pixel values outside `tokens.css`. Every screen uses the shared primitives. Navigation is three top-level destinations plus the account workspace. The freshness language appears on every dated record. Both themes pass contrast and keyboard audits. The backend tests still pass. And the honest test: a screenshot of Today could not be mistaken for a generic admin template.

---

## 13. Standing rules (in `CLAUDE.md`)

The `## Design` section of `CLAUDE.md` carries the condensed standing rules derived from this guide, so every future session inherits the visual system without being handed this document again. This guide remains the full authority.
