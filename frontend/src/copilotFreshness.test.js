import test from "node:test";
import assert from "node:assert/strict";

import { answerState, revealLabel } from "./copilotFreshness.js";
import { withheldSentence } from "./sharedPlan.js";

const FRESH = { freshness: { generated_at: "2026-08-05T09:00:00+00:00", age_days: 1,
  threshold_days: 30, withheld: false, withheld_reason: null, revealed: false } };
const STALE = { freshness: { generated_at: "2026-02-14T09:00:00+00:00", age_days: 173,
  threshold_days: 30, withheld: true, revealed: false,
  withheld_reason: "this answer was written 173 days ago, past the 30-day evidence window for an account-scoped run" } };

test("a run inside its window asks for nothing", () => {
  const state = answerState(FRESH);
  assert.equal(state.withheld, false);
  assert.equal(state.sentence, null);
});

test("a run past its window carries the server's clause in the shared frame", () => {
  const state = answerState(STALE);
  assert.equal(state.withheld, true);
  assert.equal(state.revealed, false);
  // Identity, not substring: the view must not be able to reword, truncate, or soften the reason.
  assert.equal(state.sentence, withheldSentence(STALE.freshness.withheld_reason));
  assert.equal(state.sentence,
    "Held back because this answer was written 173 days ago, past the 30-day evidence window for an account-scoped run.");
});

test("the sentence uses the same frame the shared plan does, not a second copy", () => {
  // If this module ever grew its own frame the two could drift, and a refusal would read
  // differently depending on which surface it landed on.
  assert.equal(answerState(STALE).sentence.startsWith("Held back because "), true);
  assert.equal(answerState(STALE).sentence.endsWith("."), true);
});

test("revealing does not make a run current", () => {
  const state = answerState({ freshness: { ...STALE.freshness, revealed: true } });
  assert.equal(state.withheld, true);
  assert.equal(state.revealed, true);
  assert.equal(state.sentence, withheldSentence(STALE.freshness.withheld_reason));
});

test("a missing reason still produces a sentence rather than a blank refusal", () => {
  const state = answerState({ freshness: { withheld: true } });
  assert.equal(state.sentence, "Held back because no reason was given.");
});

test("an absent freshness projection is not treated as withheld", () => {
  for (const run of [null, {}, { freshness: null }]) {
    assert.equal(answerState(run).withheld, false);
  }
});

test("the reveal control names the date rather than promising currency", () => {
  assert.equal(revealLabel(STALE), "Show what was written on 2026-02-14");
  assert.equal(revealLabel({}), "Show what was written");
  assert.equal(revealLabel(STALE).includes("current"), false);
});
