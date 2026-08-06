/**
 * Reading the server's freshness projection for a persisted copilot run (VISIBILITY-SPEC §3).
 *
 * `copilot_runs` is the one surface that persists generated prose and re-opens it by id, so it is
 * the one place a February answer can render in August at full weight. Past the evidence window for
 * the run's scope the server withholds the body and authors a clause; this module only reads that
 * answer.
 *
 * It composes no part of the refusal. The clause arrives written and goes through the same
 * `withheldSentence` frame the shared plan uses — the same function, not a copy of it, because two
 * frames are two places a refusal can be softened independently (D-153).
 */
// Explicit extension: this module is covered by `node --test`, which resolves without Vite.
import { withheldSentence } from "./sharedPlan.js";

/**
 * What the answer body should do: render, or stand behind an explicit action.
 *
 * `withheld` and `revealed` are separate. A revealed answer is still a withheld one that an operator
 * chose to read, and the age treatment stays on it — revealing does not make it current.
 */
export function answerState(run) {
  const freshness = (run || {}).freshness || {};
  if (!freshness.withheld) {
    return { withheld: false, revealed: false, sentence: null, thresholdDays: freshness.threshold_days ?? null };
  }
  return {
    withheld: true,
    revealed: !!freshness.revealed,
    sentence: withheldSentence(freshness.withheld_reason || "no reason was given"),
    thresholdDays: freshness.threshold_days ?? null,
  };
}

/**
 * The label on the control that opens a withheld answer.
 *
 * It names the date rather than promising currency: "Show what was written on 2026-02-14", never
 * "Show the answer". The operator is being offered a record, not a reading.
 */
export function revealLabel(run) {
  const day = ((run || {}).freshness || {}).generated_at?.slice(0, 10);
  return day ? `Show what was written on ${day}` : "Show what was written";
}
