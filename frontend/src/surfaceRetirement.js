/**
 * Stage 17 Slice 3 — how a recorded retirement changes what a surface looks like
 * (`SURFACE-USAGE-SPEC.md` §7.2, §7.3, §7.5).
 *
 * Pure, so it is testable under bare `node --test`; the wiring is in `Surface.jsx` and `measure.js`.
 *
 * The rules that matter here are all about *not deciding anything locally*.
 *
 * - **The server holds the vocabulary and the matrix.** This module maps an already-decided action
 *   onto a presentation and nothing more. It never asks whether an action was allowed: §7.4's
 *   per-kind matrix and §7.7's safety check are computed from `reaches`, `provides` and
 *   `explains_refusal`, which the client registry deliberately does not mirror. A client copy of
 *   them would be a second place a retirement could be judged safe.
 * - **An unknown action renders normally.** Not hidden. Every failure here should fall towards
 *   *showing* the surface, because the cost of wrongly showing something is clutter and the cost of
 *   wrongly hiding it is a thing the operator cannot find and the usage data will never mention —
 *   the surface that stopped rendering stopped emitting events too.
 * - **The notice is server-authored.** `retired_notice` arrives as a finished sentence. A view that
 *   composes part of an "I did not show you this" statement can soften one (D-153).
 */

/** The four presentations. `hidden` is the only one that removes a surface from the page. */
export const PRESENTATIONS = Object.freeze(["normal", "collapsed", "demoted", "hidden"]);

const BY_ACTION = Object.freeze({
  collapse: "collapsed",
  demote: "demoted",
  retire: "hidden",
  restore: "normal",
  none: "normal",
});

/**
 * `presentationFor(state, key)` → `{ presentation, action, causeCode, notice, recordedOn }`.
 *
 * `state` is the `surfaces` map from `GET /api/telemetry/surface-retirement`. A missing map, a
 * missing key, or an action this build does not recognise all yield `normal` — see above.
 */
export function presentationFor(state, key) {
  const entry = (state && state[key]) || null;
  const action = (entry && entry.action) || "none";
  const presentation = BY_ACTION[action] || "normal";
  return {
    presentation,
    action: BY_ACTION[action] ? action : "none",
    causeCode: (entry && entry.cause_code) || null,
    notice: (entry && entry.retired_notice) || null,
    recordedOn: (entry && entry.recorded_on) || null,
  };
}

/**
 * Whether a collapsed surface starts open.
 *
 * Always false: `collapse` means "closed by default, one click to open" (§7.2). Expressed as a
 * function rather than a literal so the one place that decides it is greppable, and so a future
 * "remember what I opened" setting has somewhere to land that is not twenty call sites.
 */
export function startsOpen() {
  return false;
}

/**
 * The engagement value to report when an operator opens a collapsed or demoted surface.
 *
 * `expanded`, not `opened`. §5's six are distinguishable on purpose, and reading "I had to open
 * this because it was collapsed" as an ordinary open would make a surface look more engaged the
 * more it had been hidden — the exact inversion of §6.3.
 */
export const EXPAND_ENGAGEMENT = "expanded";

/** The dismiss value for closing one again. `collapsed`, one of §5's three. */
export const COLLAPSE_DISMISS = "collapsed";

/**
 * Rows for the Operations retirement list: every surface that currently carries an action.
 *
 * Sorted by key so the list has a stable order that is not "most recently changed" — a list that
 * reorders itself as you work it is a list you lose your place in. Never sorted by count: this is
 * a record of decisions, not a leaderboard.
 */
export function retiredRows(state) {
  if (!state) return [];
  return Object.keys(state)
    .filter((key) => {
      const action = state[key] && state[key].action;
      return action && action !== "none" && action !== "restore";
    })
    .sort()
    .map((key) => ({ ...state[key], surface: key }));
}

/** True when a surface can be handed to the restore command. Mirrors the server's own refusal. */
export function canRestore(state, key) {
  const action = state && state[key] && state[key].action;
  return Boolean(action) && action !== "none" && action !== "restore";
}
