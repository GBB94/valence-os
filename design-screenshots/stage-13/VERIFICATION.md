# Stage 13 rendered verification

**Status: rendered (2026-08-05).** This file supersedes the 2026-08-02 version, which correctly
reported that no in-app browser session was available and listed the rendering claims as explicitly
unverified rather than asserting them. A session is available now, so those items are captured or
exercised below — or still named as outstanding, with the reason.

The rendered pass found **one real defect**, in a shared component, and fixed it. That is the
argument for the pass: 670 backend and 165 frontend tests were green through it, because the failure
mode has no symptom.

## Captures

| File | What it shows |
|---|---|
| `comms-sequence-light.png` / `comms-sequence-dark.png` | the Adoption communications card on `acc-terravance` / `prog-tv-global` — a running sequence, a sent and a planned wave with derived expected dates, and **all four** attendance treatments in one view |
| `attendee-slideover-dark.png` | the `Record attendee` slide-over over the account workspace, with the session-role and attendance selects and the trust-boundary line |

## The four attendance treatments, rendered

`adoption_comms.attendance()` can return four states, and the rule that matters is what the panel
does when it *cannot* honestly compute a rate. Before this pass the seed contained one clean
session, so three of the four states were test-covered but had never been drawn. Three mock sessions
were added to `_seed_stage13_demo` so each state is reachable in the running app:

| Session | State | What the panel says |
|---|---|---|
| DACH manager clinic | `known` | `19 of 25 attended` · `6 no-show · 0 unknown` |
| Enablement drop-in | `unknown` | `no invitation wave is linked` |
| Reinforcement huddle | `incomplete` | `one or more attendees are not classified as audience, facilitator, or observer` |
| Manager office hours | `suppressed` | `invited audience 8 is below the account minimum of 25` |

Each withheld case is a different *reason*, not a different severity, and the panel states which
fact is missing rather than falling back to counting the room:

- **`unknown`** — the session happened, but attendance is deployment engagement against an invited
  cohort, and without a linked invitation wave there is no denominator. Counting attendees would
  produce a number with no meaning.
- **`incomplete`** — one attendee's role was never classified. An unclassified row is not quietly
  treated as audience to keep the number alive; the whole readout is withheld.
- **`suppressed`** — nothing is missing here at all. The cohort clears the floor and every attendee
  is classified; the *invited audience* is 8 against an account minimum of 25, and publishing a rate
  over 8 people is how a small group becomes identifiable. This case exercises the audience floor
  specifically rather than the cohort floor.

**Not conveyed by color alone.** All three withheld rows render inside `.unknown-fill` — the
DESIGN-GUIDE cross-hatched unknown treatment,
`repeating-linear-gradient(45deg, rgba(0,0,0,0), …)` — carrying a text label *and* the stated
reason. Measured in the rendered card: `hatchCount: 3`, labels `["unknown", "incomplete",
"suppressed"]`, identical in both themes. No status hue is used for any of them, because a withheld
readout is not a bad one.

## Defect found by rendering, and fixed

### The shared `SlideOver` never restored focus to the control that opened it

`ui.jsx`'s own comment states the contract — *"focus returns to wherever the operator was standing
when the panel opened"* — and the component did not meet it. Opening `Record attendee` and pressing
Escape left focus on `<body>`.

This was measured, not inferred. Wrapping `HTMLElement.prototype.focus` for the duration of the
close showed exactly one restore call, and it named its target:

```
{ on: "INPUT:", connected: false }
```

The restore was firing at a node **inside the panel** that was already detached. Two independent
causes, both from reading `document.activeElement` inside an effect:

1. The capture lived in an effect keyed `[onClose]`, and `onClose` is an inline arrow at nearly
   every one of the **63** call sites. The effect therefore re-ran on every render and re-captured
   the opener from whatever had focus at that moment — which, after mount, is inside the panel.
2. A child `autoFocus` is applied during commit, *before* any effect runs, so even a mount-only
   effect can observe the wrong element.

Fixed by capturing during the first render (`useRef` + lazy init, which runs before commit and
cannot re-run) and splitting the two concerns: a mount-only effect enters and restores focus, and
the keyboard effect keeps its `[onClose]` subscription. The restore guards on `isConnected` rather
than truthiness — focusing a detached node silently does nothing, which is precisely how this hid.

`CopilotPanel` re-implements the same trap and had **no** restore at all, deferring to a
`requestAnimationFrame` in `App.jsx:253`. It now owns its own restore under the same rule. Stage 12's
verification recorded that path as unmeasurable because rAF never fires in a backgrounded tab; with
the restore moved into the component that owns the trap, it no longer depends on rAF and **was**
measurable here — it passes.

Verified live on four callers, in the same automation tab that previously reported `<body>`:

| Panel | Focus on mount | Escape closes | Focus restored |
|---|---|---|---|
| `Record attendee` (AdoptionComms) | Close | yes | **opener** |
| `Add wave` (AdoptionComms) | Close | yes | **opener** |
| `New expansion opportunity` (Commercial — has an `autoFocus` child) | Close | yes | **opener** |
| Account Copilot (`Ask`) | Close | yes | **opener** |

No test covers this: `node --test` cannot import JSX, and the failure is a DOM focus outcome rather
than a pure function. It is recorded here as a rendered check rather than claimed as automated.

## Executed — live, in a real browser

Driven at `http://localhost:8000` on the mock seed. Each item is an observed response:

- the card renders in the Plan tab under `prog-tv-global` with the standing line
  **"Planned waves and session attendance · never auto-sent"**;
- a `running` sequence shows wave 1 `sent` with a `9d` age chip and wave 2 `planned` with its
  **derived** expected date — a sent wave carries `Record sent` / `Cancel`, a sent one does not;
- all four attendance treatments render simultaneously (table above);
- the `Record attendee` slide-over opens over the account workspace — above the sticky topbar, so
  the D-138 portal fix holds here too — with `role="dialog"`, `aria-modal="true"`, a session-role
  select (`audience` / `facilitator` / `observer` / `unknown`) and an attendance select;
- the slide-over states the trust boundary in the form itself: **"Attendance is meeting engagement
  only. It is never joined to product usage."**

## Both-theme contrast, measured on the rendered card

Computed over every text node in the Adoption communications card against its own resolved
background, not against the page body:

| Theme | Nodes | Floor | Under 4.5:1 |
|---|---|---|---|
| light | 62 | **4.82:1** | 0 |
| dark | 62 | **4.87:1** | 0 |

No new color tokens and no raw hex were introduced.

## Keyboard — what was exercised, and what was not

Exercised live against the panel's own handlers, on the `Record attendee` slide-over:

- focus enters the panel on open (Close is the first focusable and holds focus after mount);
- Escape closes it;
- focus containment wraps in both directions — from the last control Tab returns to the first, from
  the first Shift+Tab returns to the last;
- focus returns to the opening control on close (the defect above);
- 7 focusable controls, no `tabindex="-1"` traps.

These used dispatched `KeyboardEvent`s, not OS keypresses — no hardware key primitive is available
to the automation. They exercise the app's own handlers, which is what the wrap-around logic *is*;
they do **not** prove the browser's native tab traversal order.

## Observations, not fixed

1. **Form inputs have no programmatic label.** Every `Field` renders
   `<div class="field"><label>{label}</label>{children}</div>` — a `<label>` with no `for` and no
   wrapping, so each input's accessible name is empty (measured: 4 of 4 inputs in the attendee
   panel, `labels: 0`, no `aria-label`). This is **app-wide and pre-existing**, not a Stage 13
   regression: the same `Field` is copied verbatim in `AdoptionComms.jsx`, `Growth.jsx`,
   `Internal.jsx`, and `PortfolioInternal.jsx`. Fixing it means changing every form in the app, and
   the honest scope of this pass is one stage's rendering, so it is reported rather than
   half-corrected.
2. **The calendar row prints every attendee inline, uncapped.** With the 15-attendee mock session
   added here, `CalendarPanel.jsx:26` joins all names into a single cell and the row grows to three
   wrapped lines. It was never visible before because the seed had small sessions. A display cap is
   a product judgement call, not a correctness fix.
3. **A `suppressed` derived readout does not hide the underlying names**, and should not be read as
   claiming to. The calendar row still lists the eight individually recorded attendees, because the
   privacy floor governs *publishing a rate over a cohort*, not the operator's own record of who was
   in a meeting they ran. Worth stating so the two surfaces are not mistaken for a contradiction.

## Still outstanding

1. **Narrow split-screen viewport** — the sessions and waves tables at a narrow width.
2. **Sequence and wave create flows, submitted.** The slide-overs were opened, focus-checked, and
   captured, but no record was created through them in this pass; creation is covered by the backend
   suite.

## Automated evidence

- **670 backend tests pass**, 13 of them in `tests/test_adoption_comms_stage13.py` — derived
  sequence state and expected dates, the immutability of a recorded send, cohort-linked attendance,
  the audience/facilitator/observer distinction, and each withholding rule.
- **168 frontend tests pass.** The production Vite build passes. 50 migrations apply to an empty
  database.
- A localhost API read returns all four attendance states with their reasons, matching what the card
  renders.

`npx eslint src/` does not run in this repository — there is no `eslint.config.js`. That is
pre-existing and is stated here rather than reported as a lint pass.
