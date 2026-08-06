/**
 * The wiring between the pure telemetry contract and the running app (`ACCOUNT-PATH-SPEC.md` §17).
 *
 * Everything with a rule in it lives in `./telemetry.js`, which imports nothing and is covered by
 * `telemetry.test.js`. This module holds only the three things that need a browser: the local
 * session identifier, the transport, and a hook that memoizes a tracker for a component's scope.
 * It is not unit-tested because there is nothing here to get wrong that a test could see —
 * splitting it this way is what keeps the derivers testable under bare `node --test`.
 */
import { useMemo } from "react";

import { api } from "./api";
import { createTracker, ensureSessionId, moveThatLeft } from "./telemetry";

function mint() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  // Old-browser fallback. Still a slug, still says nothing about who is using the installation.
  return `s-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}

let cachedSession = null;

/** Pseudonymous and per-installation. Nothing maps it to a person, here or on the server. */
export function sessionId() {
  if (cachedSession) return cachedSession;
  const storage = typeof localStorage === "undefined" ? null : localStorage;
  cachedSession = ensureSessionId(storage, mint);
  return cachedSession;
}

/**
 * A `track(eventName, properties)` bound to one account/program/ruleset scope.
 *
 * `rankingRuleVersion` comes from the Execution Path response rather than a constant, so a later
 * review can tell which ordering the operator was actually looking at (§17.6 step 7).
 */
export function useMeasure({ accountId = null, programId = null, rankingRuleVersion = null } = {}) {
  return useMemo(
    () => createTracker(api.recordEvent, {
      accountId, programId, rankingRuleVersion, sessionId: sessionId(),
    }),
    [accountId, programId, rankingRuleVersion],
  );
}

/** The same tracker outside a component, for a module that has no hook to hang it on. */
export function measure(context = {}) {
  return createTracker(api.recordEvent, { ...context, sessionId: sessionId() });
}

// --- the one piece of state measurement needs ---------------------------------------------
//
// Opening a recommended move navigates to its native record, which unmounts Account Path. So the
// memory of what was recommended cannot live in component state, and it is module-level rather
// than stored: it is a single editor with one open move at a time, and it should not survive a
// reload. `telemetry.moveThatLeft` holds every rule about what the absence means; this is the box.

let openedMove = null;

export function rememberOpenedMove(entry) {
  openedMove = entry ? { ...entry, snoozed: false } : null;
}

/** A snoozed row disappears too. It is a different fact, and it has its own event. */
export function markMoveSnoozed(id) {
  if (openedMove && openedMove.id === id) openedMove.snoozed = true;
}

/** Returns the properties once, then forgets — one departure is not counted twice. */
export function takeMoveThatLeft(body) {
  const properties = moveThatLeft(openedMove, body);
  if (properties) openedMove = null;
  return properties;
}

export function forgetOpenedMove() {
  openedMove = null;
}
