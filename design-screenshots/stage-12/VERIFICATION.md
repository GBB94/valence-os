# Stage 12 visual verification

Stage 12's account/portfolio Copilot panel and Operations surfaces are implemented. **No rendered
captures are claimed.** The in-app browser now connects and drives the app, but every
`browser_screenshot` call writes a zero-byte PNG, so image evidence still cannot be produced. There
is also no Tab/Escape key primitive available, so the keyboard pass remains un-run.

What follows separates what was executed from what is still outstanding. Nothing in the "live"
section is inferred from reading source.

## Executed — automated

- production frontend build and lint pass;
- all 322 backend tests pass, including the executable 13-case replay/evaluation/activation/rollback
  path, zero-tolerance activation refusal, scoped retrieval, reviewed cursors, aliases/fuzzy
  candidates, bounded follow-ups, retry/dedupe, stale/private evidence, immutable provenance,
  correction review, preview-only drafting, audience/style rejection, export/restore, and
  decomposed release gates;
- 34 migrations apply to an empty database with `integrity_check=ok` and `foreign_key_check` empty.

## Executed — live, in a real browser against the running app

Driven at `http://localhost:8000` on the reseeded mock database (2026-08-02). Each item is an
observed response, not a code reading:

- the panel opens from an account workspace and states its scope — the account name plus
  `deterministic mock`;
- **`fact`** returned a cited claim (`[p001]`, a commitment), the coverage badge **"Answer with
  gaps"**, a named gap ("1 candidate record(s) were excluded by reader or safety rules"), the
  freshness stamp "Current through 2026-08-02", and a claim→source chip. No numeric confidence
  badge appears anywhere in the rendered response — the prohibition holds in the output, not only
  in the validator;
- **`changes`** **abstained**: "Insufficient evidence" / "I can't defend an answer from this scope"
  / "No in-scope native record supports this question", with the interpreted window shown. This is
  the behaviour that matters most — the mode declined rather than padding an answer out of generic
  account context;
- **`weekly`** returned coverage **"Supported"** with every suggested move individually cited
  (`[p001]`–`[p005]`), including the line "Record the acknowledgment interaction; **do not
  auto-send**";
- saved runs persist and are listed with their completion date, so a prior answer stays inspectable;
- Operations renders the connection registry showing `COPILOT_BACKEND=mock only; real modes have no
  implementation` and the standing policy line "build everything, connect nothing real".

## Executed — both-theme rendering, measured rather than photographed

Theme flip verified live; the two themes resolve to distinct token values and the body pair clears
the `DESIGN-GUIDE.md` 4.5:1 floor by a wide margin:

| Theme | Background | Foreground | Contrast |
|---|---|---|---|
| dark | `rgb(14, 16, 19)` | `rgb(232, 234, 238)` | **15.8:1** |
| light | `rgb(246, 247, 249)` | `rgb(20, 22, 28)` | **16.9:1** |

This is weaker evidence than a capture: it confirms both themes resolve and that body text passes,
but says nothing about status glyphs, the freshness ramp, or per-component contrast inside the
panel. Treat it as a floor check, not a design review.

## Still required

1. **Rendered captures** of account Q&A, the conflicted/disambiguation response, what-changed,
   weekly, and the Operations Copilot surfaces in both themes — blocked on zero-byte screenshot
   writes, not on the app;
2. **Live keyboard pass** — tab through the panel, confirm focus never escapes the modal, press
   Escape, and confirm focus returns to the invoking control (including via cmd-K). Focus
   containment and return are present in the source (`copilotTriggerRef` / `copilotReturnFocusRef`
   in `App.jsx`) but that is not interaction evidence;
3. **Narrow split-screen viewport** — open a claim source and confirm navigation reaches the correct
   account workspace surface.

The conflicted/disambiguation path is covered by the backend suite but was not driven in the UI
here, so it stays on the outstanding list rather than moving up.
