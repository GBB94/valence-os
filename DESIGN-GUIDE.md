# Valence OS — Design Guide
### Visual system, screen architecture, and redesign brief for the frontend
*v2 · July 2026 · Companion to `Valence-OS-Scoping-Doc.md` §6 and `CLAUDE.md`*

---

## 0. What this document is, and what it is not

**This guide supersedes §6 of the scoping doc and the navigation the current build inherited from the §5 module list.** Where the two disagree, this document wins. The scoping doc's design section was written before anything existed; this one is written against a working app, so it replaces rather than supplements. The one-color-mode line and the one-destination-per-module structure are both explicitly retired here.

Treat the presentation layer as open. Information architecture, navigation, screen composition, layout, tokens, typography, components, iconography, empty and error states, interface copy, and the presentation of the visualizations are all yours to redesign. Do not preserve an existing arrangement because it is what got built. Layout restructuring is the primary motivation for this work, not a side effect of it.

**What still holds, and why.**

- **The trust boundaries in §2 of the scoping doc.** No field, column, or view anywhere for a named individual's product usage. Client-facing outputs include only affirmatively promoted records, enforced in code. Stakeholder assessments keep their date and evidence note. Stale metric-derived indicators never render as carried-forward good state. These are not scope ceremony. They are the reason the tool does not conflict with what Valence sells, and a redesign is exactly the moment they get broken by accident.
- **Behavior stays put unless the redesign requires otherwise.** Queue ranking logic, closure rules, and generator output are not visual concerns. If a layout change genuinely needs one to move, propose it.
- **Schema changes are proposals, not blockers.** If a screen would be materially better with a new field, batch the proposals with a one-line rationale each and surface them at the end of the phase rather than stopping the work or adding them silently.
- **Tests stay green,** and no new runtime dependencies beyond self-hosted font files.

---

## 1. Design thesis

**The subject.** One operator running a small number of very large, very consequential accounts. The work is remembering, noticing, and deciding. The tool's job is to make the state of an account legible in seconds and to make capture so fast it never gets skipped.

**The thesis: an instrument, not a dashboard.** Consumer dashboards persuade. This one reports. It should feel like a well-made measuring device: quiet housing, precise readouts, nothing decorative competing with the data. Confidence comes from typographic discipline and exact alignment, not from cards, gradients, and shadows.

**The signature.** Two things carry the identity, and nothing else is allowed to shout.

1. **The freshness language** (Section 7). Every record shows its age in the same monospaced form, and everything derived from stale inputs renders as an explicit unknown rather than a carried-forward green. This is the scoping doc's principle 7 made visible, and it is the motif that runs through every screen.
2. **The stakeholder graph** stays the one full-bleed visual moment. It is the only screen permitted to be visually expressive.

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

One screen per account. A persistent context header, then a tab strip. Tabs are destinations within the URL so they are linkable and back-button-able, but they never reload the header.

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

### 2.3 The Ledger merge (the most consequential change)

Interactions, tasks, commitments, decisions, risks, and issues are currently separate surfaces. They are all the same shape: a dated thing, with an owner, a state, and a link back to the interaction that produced it. Splitting them means the answer to "what is going on with this account" requires visiting five screens.

Build the Ledger as one chronological, filterable table with a type filter chip row across the top (All, Interactions, Commitments, Tasks, Decisions, Risks, Issues, Inbox) and a count on each chip. Default view is All, newest first. Untriaged capture-inbox items pin to the top of the list with the unknown treatment until they are converted, which makes triage a thing you do in passing rather than a chore on its own screen.

Use master-detail here rather than a slide-over: list on the left at roughly 60 percent, detail pane on the right. This is the screen you dwell in, and a panel that covers the list makes comparing records impossible.

### 2.4 Capture is global, not a destination

The 30-second rule should be structural, not aspirational. Capture is available from anywhere by keyboard (a dedicated shortcut, and via the palette) and from a persistent affordance in the top bar. It opens as a slide-over, prefills the account and program from wherever you were standing, and never requires navigating away from what you were doing. Closing it returns you exactly where you were.

### 2.5 Today

A single ranked list, grouped by urgency band rather than by account, with the account name as a column. No cards, no charts, no summary tiles. Every row carries the trigger reason in plain text, its age, its due date, and one primary action inline. Snooze and resolve are row actions. This screen exists to be emptied.

### 2.6 Progressive disclosure

The default state of every screen shows the answer, not the raw material. Depth is one interaction away, never zero and never three. Concretely: Overview shows statuses and the top three risks, with a link into the full register; Evidence shows five to nine metric cards with sparklines, with the observation history behind a click; Commercial shows the pipeline and the waterfall, with contract versions in a panel.

---

## 3. Space, grid, and shell

**Spacing scale.** 4px base. Use only 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 48, exposed as `--sp-1` through `--sp-10`. No arbitrary values anywhere.

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
│          │                          │ slide-over 520px       │   │
└──────────┴──────────────────────────┴────────────────────────┴───┘
```

- **Left rail, 240px**, collapsible to 56px icons, state persisted. Active item uses `--bg-selected` with a 2px accent bar on the leading edge, never a filled pill.
- **Top bar, 48px**, does not scroll away. Holds breadcrumb, global search, the capture affordance, the density toggle, and the theme toggle.
- **Context header**, sticky beneath the top bar, present on every account tab. Account name, program selector, both statuses with their assessed dates, renewal countdown, phase. This is the ten-second read and it must never require scrolling to find.
- **Content**, full width, 24px gutters, no centered max-width container. This is a data tool on a large screen. Prose blocks inside panels cap their own measure at roughly 70 characters.
- **Slide-over, 520px**, right side, `--shadow-panel`, scrim at 12 percent ink. Used for detail views everywhere except the Ledger, which uses master-detail. Blocking modals are reserved for destructive confirmation only.

---

## 4. Color tokens

Cool graphite neutrals with a single ink-indigo accent. The accent deliberately avoids the green, amber, and red families, because those are reserved for status and an interactive control must never be confusable with a state.

Define these once in `tokens.css`. After this work, nothing in the app may use a raw hex value.

### 4.1 Light (default)

```css
:root {
  /* Surfaces */
  --bg-app:        #F6F7F9;
  --bg-surface:    #FFFFFF;
  --bg-sunken:     #EFF1F4;
  --bg-hover:      #F2F4F7;
  --bg-selected:   #EEEEFC;

  /* Lines */
  --line-hairline: #E3E6EB;
  --line-strong:   #CDD2DA;

  /* Ink */
  --ink-primary:   #14161C;
  --ink-secondary: #565D6B;
  --ink-tertiary:  #868D9B;
  --ink-inverse:   #FFFFFF;

  /* Accent (interaction only, never state) */
  --accent:        #3A34C4;
  --accent-hover:  #2F2AA6;
  --accent-tint:   #ECEBFA;
  --accent-ring:   rgba(58, 52, 196, 0.35);

  /* Status (state only, never decoration) */
  --status-ok:           #1F8A54;
  --status-ok-tint:      #E6F4EC;
  --status-warn:         #B26B00;
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
  --r-md: 6px;
  --r-lg: 10px;
  --shadow-panel: 0 1px 2px rgba(20,22,28,.05), 0 12px 32px rgba(20,22,28,.10);
}
```

### 4.2 Dark

Not pure black. Dense text on true black causes halation and makes hairlines impossible to place. The dark surface is a deep cool graphite, the accent lightens to hold contrast, and the status hues desaturate so they do not glow.

```css
[data-theme="dark"] {
  --bg-app:        #0E1013;
  --bg-surface:    #16191E;
  --bg-sunken:     #101317;
  --bg-hover:      #1D2127;
  --bg-selected:   #1E1F3D;

  --line-hairline: #262B33;
  --line-strong:   #363C46;

  --ink-primary:   #E8EAEE;
  --ink-secondary: #A2A9B6;
  --ink-tertiary:  #6F7784;
  --ink-inverse:   #0E1013;

  --accent:        #7C74F0;
  --accent-hover:  #948DF5;
  --accent-tint:   #1E1F3D;
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

  --shadow-panel: 0 1px 2px rgba(0,0,0,.40), 0 12px 32px rgba(0,0,0,.50);
}
```

**Theme mechanics.** Three states in the top-bar toggle: System, Light, Dark. System reads `prefers-color-scheme` and updates live. The choice persists to localStorage and applies via `data-theme` on the root element before first paint, using a tiny inline script in the HTML head so there is no flash of the wrong theme. Set `color-scheme` on the root so native form controls and scrollbars follow. Both themes are audited for contrast independently; passing in light does not mean passing in dark, and the tints are where it usually fails.

**Rules of use.**

- Green, amber, and red appear only to encode state. Never for emphasis, never for branding, never on a chart other than the budget waterfall.
- The waterfall is the single documented exception. Because the app is a tabbed workspace with a sticky status header, strict screen-level separation is impossible; the enforceable rule is that **no status indicator appears inside the same card or panel as a financial chart**. Enforce this in the layout, not in a comment. (Narrowed from "same screen" — D-70.)
- Elevation is rare. Tables, cards, and panels separate with hairlines. Only the slide-over, the command palette, and toasts get a shadow.
- Tints back badges and selected rows only. Never tint a large surface.

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

**Non-negotiables.** `font-variant-numeric: tabular-nums` globally, and mono for anything in a column of numbers, a date, a duration, a seat count, a currency figure, or an ID. Weight 700 is never used; hierarchy comes from size, color, and space. Sentence case everywhere except the 11px eyebrow. One number format per column, decimals included.

---

## 6. Components

### Tables (the primary surface)

- Two densities, **compact 32px** and **default 40px** rows, driven by the top-bar toggle and persisted. Default is compact.
- Header row: 11px uppercase eyebrow, `--ink-secondary`, sticky on scroll, 1px `--line-strong` beneath. Header alignment always matches its column's content.
- Rows separated by 1px `--line-hairline`. No vertical rules, no zebra striping.
- Text left, numbers and dates right, nothing centered. Right-aligned columns use mono so decimals stack.
- Hover: `--bg-hover` across the full row; row actions appear on hover at the right edge instead of occupying a permanent column.
- Selected: `--bg-selected` plus a 2px accent leading edge, surviving scroll.
- Focus: 2px `--accent-ring` outline on the focused row or cell, always visible, never color-only.
- Truncate with ellipsis and a title attribute; never wrap in compact mode. Repeated qualifiers move into the column header.

### Cards and panels

Hairline border, `--r-md`, `--bg-surface`, 16px padding, no shadow. A card groups; it does not decorate. More than four cards on a screen usually means it wanted a table.

### Buttons

| Variant | Use | Style |
|---|---|---|
| Primary | The one action the screen exists for | `--accent` fill, `--ink-inverse`, `--r-sm`, 13px/500, 28px compact |
| Secondary | Everything else | `--bg-surface`, `--line-strong` border, `--ink-primary` |
| Ghost | In-row and toolbar actions | transparent, `--ink-secondary`, hover `--bg-hover` |
| Danger | Destructive only | `--status-risk` on `--status-risk-tint`; filled only inside a confirm dialog |

One primary per screen maximum. Labels are verbs naming the outcome: "Log interaction," "Convert to commitment," "Promote to plan." Never "Submit," never "OK."

### Inputs

32px compact, `--line-strong` border, `--r-sm`, 13px. Focus swaps border to `--accent` and adds a 3px ring. Labels above in 11px eyebrow style. Errors beneath in `--status-risk`, stating the next move rather than the failure.

### Badges and chips

11px, 500, `--r-sm`, 2px/6px padding, tint background with matching solid ink. Status badges pair color with shape: filled dot for on track, hollow for at risk, cross-hatched for unknown. State never depends on color alone.

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

**The attention rail.** On Today, each row carries a 2px leading edge colored by **urgency band** (the queue's ranking band, which is what the operator scans by — trigger class proved too granular to read as a color). Beside it, the reason renders as 11px plain text, because the doc requires every item to explain itself and a colored bar explains nothing.

---

## 8. Visualizations

All inherit the tokens; none introduce a palette.

**Stakeholder graph.** The one expressive surface. Full-bleed canvas on `--bg-app`, nodes on `--bg-surface` with hairline strokes, size encoding influence, fill **and node shape** encoding stance from the **categorical data family** (`--data-*`) — stance is a position, not account health, so it is not a status hue, and the shape lets it read without color — edge thickness encoding relationship strength, arrowheads encoding direction. Reporting edges solid in `--line-strong`; influence and sponsorship edges dashed in `--data-2`. Labels at 11px, on hover or above a zoom threshold. Clicking opens the standard slide-over. The power-interest grid is a toggle, not a second screen, sharing node styling.

**Budget waterfall.** `--fin-positive`, `--fin-negative`, `--fin-total`, direct value labels in mono on every bar, no legend, no truncated axis, minor sources grouped with subtotals. No status indicator may appear in the same card or panel as this chart (D-70).

**Sparklines and bullet charts.** `--data-1` for the measure, `--data-muted` for qualitative bands, a 1px `--ink-primary` target marker. One baseline, no gridlines, no axis labels on sparklines.

---

## 9. Motion

```css
--dur-fast: 120ms;
--dur-med:  180ms;
--ease: cubic-bezier(0.2, 0, 0, 1);
```

Slide-overs translate from the right. The palette fades and scales from 0.98. Theme changes are instant, with no crossfade. Nothing else animates: no page transitions, no staggered reveals, no skeleton shimmer beyond a single quiet pulse. `prefers-reduced-motion` drops everything to opacity-only.

---

## 10. Interface copy

Copy is design material and moves with this work. Buttons name the outcome, and the verb persists into the confirmation. Labels use the operator's vocabulary rather than the schema's: "Last touch," not `last_interaction_at`; "Who's driving it," not `internal_owner_id`. Errors say what happened and the next move. Empty states invite the first action. Sentence case throughout, no exclamation marks, no apologies.

---

## 11. Quality floor

Ship none of this without all of it.

- 4.5:1 contrast minimum on every text and icon pairing, audited separately in light and dark, including every tint-on-surface combination.
- Visible keyboard focus on every interactive element, verified by tabbing through each screen in both themes.
- No state conveyed by color alone; every status pairs color with a shape or a label.
- Real semantic tables (`table`, `thead`, `th` with `scope`) so assistive tech gets the relationships. Full keyboard operation of Today, the Ledger, and the palette.
- No flash of incorrect theme on load.
- `prefers-reduced-motion` and `color-scheme` both honored.
- Readable at 1280px and usable split-screen beside a video call at roughly 900px, where the rail collapses to icons. This is not a phone app.

---

## 12. Work order

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
