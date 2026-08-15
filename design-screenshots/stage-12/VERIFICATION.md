# Stage 12 rendered verification

**Status: rendered (2026-08-05).** The captures below were taken in a real browser against the
running app on the mock seed. This file supersedes the 2026-08-02 version, which correctly reported
that no captures existed because every `browser_screenshot` call wrote a zero-byte PNG; that tooling
now works, so the "measured rather than photographed" section is replaced by the captures.

The rendered pass found **two real defects**, both fixed. That is the argument for the pass: the
suite was green through both of them.

## Captures

| File | What it shows |
|---|---|
| `copilot-fact-light.png` / `copilot-fact-dark.png` | a `fact` run — cited claim, "Answer with gaps" coverage badge, a named gap, freshness stamp, claim→source chips |
| `copilot-changes-light.png` / `copilot-changes-dark.png` | a `changes` run over `acc-terravance` — the run that used to fail; eight cited claims including the campaign-creation row that was blanking the statement |

## Defects found by rendering, and fixed

### 1. `changes` died with a bare `failed` badge

The panel showed a `failed` run with no answer and no reason. The database gave the reason:
`NOT NULL constraint failed: copilot_claims.claim_text`.

Cause: `copilot_context._change_feed` builds each row's `statement` by SQL concatenation, and
SQLite's `||` yields NULL if **any** operand is NULL. Three of the four change queries concatenated
a nullable column unguarded; the fourth (`ask_change`) already used `COALESCE`, which is what makes
this a slip rather than a design. `adoption_campaign_state_history.from_status` is null on every
campaign's *creation* row, so the feed broke as soon as a campaign existed.

Fixed in two layers:

- `copilot_context.py` — `COALESCE(h.from_status,'created')` and
  `COALESCE(' — '||s.rationale,' — no rationale recorded')`. The whole `' — '||s.rationale`
  expression is NULL exactly when the rationale is, so the fallback replaces the clause rather than
  being appended to it.
- `copilot_model.generate()` — an item with no readable statement is now dropped **and named** as an
  evidence gap, and the run's `evidence_state` can no longer read `supported` with a hole in it. The
  operator gets a shorter answer that says what is missing, instead of a badge with no reason. The
  NOT NULL constraint was already saying "this should never happen"; the guard makes it survivable.

Four regression tests in `tests/test_copilot_stage12.py`, each verified to fail when the fix is
reverted:

- a status assessment posted through the ordinary API with no rationale must not fail the run;
- **every nullable column in every change statement must be COALESCEd** — the table aliases are
  parsed out of the queries and the nullability is read from the live schema, so a *new* change
  source or a migration that relaxes a NOT NULL fails here rather than in a run;
- an unreadable item is withheld, named, and downgrades coverage to `partial`;
- an entirely unreadable packet abstains rather than answering from nothing.

### 2. The answer body rendered raw markdown

`## What changed` and `- ` were visible on screen. The obvious fix — stop emitting the syntax — is
wrong: `copilot_validation.lint_evidence_section` **parses the generator's own output**, reading
`### Evidence gaps` back out of the string. The structure is load-bearing on the server, so the view
had to stop showing it verbatim instead.

Rendering it as HTML is also prohibited: `ACCOUNT-COPILOT-SPEC.md` treats retrieved prose as
untrusted data, and an HTML path would let a record's contents become markup. `copilotAnswer.js`
therefore recognises only the three block forms the generator actually produces and emits React
elements with **text-node** children. Inline markers (`**`, `<b>`, `*`) pass through verbatim — a
record may legitimately contain an asterisk, and silently rewriting quoted text is worse than
showing the character. Five tests in `copilotAnswer.test.js`; the module is pure JS because
`node --test` cannot import JSX.

Verified live in both themes: `blockTags: ["H4", "UL"]`, `rawSyntaxVisible: false`.

## Executed — live, in a real browser

Driven at `http://localhost:8000` on the mock seed. Each item is an observed response, not a code
reading:

- the panel opens from an account workspace and states its scope — the account name plus
  `deterministic mock`;
- **`fact`** returned a cited claim (`[p001]`, a commitment), coverage **"Answer with gaps"**, a
  named gap ("1 candidate record(s) were excluded by reader or safety rules"), the freshness stamp,
  and claim→source chips;
- **`changes`** now returns coverage **"Supported"** with eight individually cited claims
  (`[p001]`–`[p008]`), the interpreted window shown, and the previously-fatal
  `Campaign created to draft` row present;
- **`weekly`** returned **"Supported"** with every suggested move individually cited, including
  "Record the acknowledgment interaction; **do not auto-send**";
- an unanswerable question **abstains** — "Insufficient evidence" / "I can't defend an answer from
  this scope" — rather than padding an answer out of generic account context;
- saved runs persist and are listed with their completion date, so a prior answer stays inspectable;
- Operations renders the connection registry showing `COPILOT_BACKEND=mock only; real modes have no
  implementation` and the standing policy line "build everything, connect nothing real";
- **no numeric confidence badge appears in either theme** (`noConfidenceNumber: true`). The
  prohibition holds in the rendered output, not only in the validator.

## Both-theme contrast, measured on the rendered panel

Computed over the answer blocks, coverage badge, packet chips, and claim rows — 20 text nodes per
theme, each against its own resolved background rather than against the page body:

| Theme | Nodes | Floor | Under 4.5:1 | Answer-body floor |
|---|---|---|---|---|
| light | 20 | **5.85:1** | 0 | 18.08:1 |
| dark | 20 | **8.38:1** | 0 | 15.91:1 |

This replaces the old body-pair-only figure, which said nothing about per-component contrast inside
the panel. No new color tokens and no raw hex were introduced; the block styles use `--t-body` and
`--t-small` from `tokens.css`.

## Keyboard — what was exercised, and what was not

Exercised live, against the panel's own handlers:

- **Focus enters the panel on open** — `closeRef.current.focus()`; the Close button is the first
  focusable and holds focus after mount.
- **Escape closes the panel.**
- **Focus containment wraps in both directions** — with the last control focused, Tab returns focus
  to the first (`forwardWrapped: true`); with the first focused, Shift+Tab returns it to the last
  (`backWrapped: true`).
- 14 focusable controls in the panel, no `tabindex="-1"` traps, and a global `:focus-visible` rule
  is present.

These used dispatched `KeyboardEvent`s, not OS keypresses — no hardware key primitive is available
to the automation. They exercise the app's own handlers, which is exactly what the wrap-around logic
is; they do **not** prove the browser's native tab traversal order.

**Focus return to the invoking control after close — resolved 2026-08-05, see below.** At the time
of this pass it could not be measured: the automation tab reports `document.visibilityState:
"hidden"`, `requestAnimationFrame` never fires in it, and `closeCopilot` in `App.jsx` restored focus
inside a rAF. That was recorded as a measurement artifact rather than as pass or fail.

### Observation — since acted on

`CopilotPanel` re-implemented the shared `SlideOver` keyboard contract but **omitted its
focus-restore cleanup**, leaving focus return to rest entirely on the caller's rAF in
`App.jsx:253` — with the note that "a focus restore that silently doesn't happen has no symptom,
which is an argument for moving it into the component that owns the trap."

The Stage 13 pass then found that the shared `SlideOver`'s restore **was itself broken** (it
re-captured its opener from inside the panel and fired at a detached node), fixed it, and applied the
same rule to `CopilotPanel`, which now owns its restore instead of deferring to a rAF. Because the
restore no longer depends on rAF, it became measurable in this same hidden tab and **passes**: with
the `Ask` control focused, opening the panel and pressing Escape returns focus to `Ask`. Full
evidence and the four verified callers are in `design-screenshots/stage-13/VERIFICATION.md`.

## Still outstanding

1. **Narrow split-screen viewport** — open a claim source and confirm navigation reaches the correct
   account workspace surface at a narrow width.
2. **Conflicted / disambiguation response, rendered.** Covered by the backend suite but not driven
   in the UI, so it stays on this list rather than moving up.

## Automated evidence

- 670 backend tests pass, 33 of them in `tests/test_copilot_stage12.py`, including the executable
  replay/evaluation/activation/rollback path, zero-tolerance activation refusal, scoped retrieval,
  reviewed cursors, aliases and fuzzy candidates, bounded follow-ups, retry/dedupe, stale and
  private evidence, immutable provenance, correction review, preview-only drafting, audience/style
  rejection, export/restore, and decomposed release gates.
- 168 frontend tests pass, 5 of them in `copilotAnswer.test.js`.
- The production Vite build passes. 50 migrations apply to an empty database.
