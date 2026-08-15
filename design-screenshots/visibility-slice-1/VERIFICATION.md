# VISIBILITY-SPEC Slice 1 — decay and withholding on persisted copilot runs (2026-08-06)

Six captures, both themes. The subject is a 173-day-old account-scoped run — the case the slice
exists for, since `copilot_runs` is the only surface that persists generated prose and re-opens it
by id.

## Captures

| File | State |
| --- | --- |
| `copilot-saved-runs-{light,dark}.png` | The history list, with the decay ramp on it: one run at `now`/`1m` (fresh), one at `6mo` (stale) |
| `copilot-withheld-{light,dark}.png` | The 173-day run re-opened: no prose, the server's sentence, one explicit control, claims intact |
| `copilot-revealed-{light,dark}.png` | After the explicit action: the body, with the sentence still above it |

## Measured, not reasoned about

- **The refusal is the server's, byte for byte.** The rendered sentence is
  `Held back because this answer was written 173 days ago, past the 30-day evidence window for an
  account-scoped run.` — the clause comes from the API and goes through `sharedPlan.withheldSentence`
  unedited. `copilotFreshness.test.js` asserts identity against that function, not a substring.
- **The threshold is named, not referred to.** "the 30-day evidence window" is the payload's
  `threshold_days` rendered into the clause on the server. A program-scoped run at the same age
  names 14 days instead.
- **The claims block survives withholding.** Three claims, three packet chips, in both the withheld
  and revealed captures. Evidence count is identical before and after the body disappears.
- **The control names the date, not a promise.** `Show what was written on 2026-02-14`.
- **Revealing does not make it current.** After the reveal the age chip is still `age age-stale`,
  the sentence still renders above the body, and `Preview internal draft` is still disabled — the
  server 409s a withheld run rather than letting the prose into a saved document.
- **No status hue.** `.copilot-withheld` is a dashed `--line-strong` border on `--bg-sunken` in both
  themes; `usesStatusToken` is false. An old answer is not an error, and the amber tint
  `.copilot-gaps` carries would read as one.
- **Contrast, both themes, all ≥ 4.5:1.** Withheld sentence 5.85 (light) / 8.38 (dark); the reveal
  control the same; the age chip 5.44 (light) / 5.53 (dark); the revealed prose 18.08 (light).
- **No horizontal overflow** on the body or the panel, in either theme, in either state.
- **The reveal control takes focus** and is reached by keyboard; the global `:focus-visible` ring
  applies to it as to every other control.

## How the stale run was produced

A completed run is immutable — `trg_copilot_run_answer_frozen` aborts any update to `generated_at`,
correctly, which is why no application path can age one. Both the test fixture and this capture lift
that trigger for a single statement and restore it from `sqlite_master`'s own text, so neither can
leave the invariant weaker than it found it.

The captures were shot against a **copy** of the dev database on a second server (port 8010), not
against `backend/data/valence_os.sqlite`. The copy was deleted afterwards; the dev database was
never written to.

## Not captured

- The portfolio window (45 days). It differs from the account case only in two numbers inside the
  same sentence, both of which are asserted in `test_the_window_is_a_property_of_scope_not_a_constant`.
