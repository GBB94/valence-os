/**
 * The wiring between the pure telemetry contract and the running app (`ACCOUNT-PATH-SPEC.md` §17).
 *
 * Everything with a rule in it lives in `./telemetry.js`, which imports nothing and is covered by
 * `telemetry.test.js`. This module holds only the three things that need a browser: the local
 * session identifier, the transport, and a hook that memoizes a tracker for a component's scope.
 * It is not unit-tested because there is nothing here to get wrong that a test could see —
 * splitting it this way is what keeps the derivers testable under bare `node --test`.
 */
import {
  createContext, createElement, useCallback, useContext, useEffect, useMemo, useState,
} from "react";

import { api } from "./api";
import { createTracker, ensureSessionId, moveThatLeft } from "./telemetry";

function mint() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  // Old-browser fallback. Still a slug, still says nothing about who is using the installation.
  return `s-${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}

let cachedSession = null;

/**
 * Pseudonymous and per **session**. Nothing maps it to a person, here or on the server.
 *
 * `sessionStorage`, not `localStorage`: the latter never expires, which made this a permanent
 * per-installation identifier threading every event the operator ever emitted into one trace —
 * stronger than the "rotating session token" the migration, the spec, and CLAUDE.md all describe,
 * and bought for nothing, since no server-side reading groups by it.
 */
export function sessionId() {
  if (cachedSession) return cachedSession;
  const storage = typeof sessionStorage === "undefined" ? null : sessionStorage;
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

// --- Stage 17: ambient scope for the `<Surface>` wrapper -------------------------------------
//
// `SURFACE-USAGE-SPEC.md` §7.3 wants one wrapper a view can put around a section without threading
// anything through it — a wrapper with a required `track` prop would be one more thing to forget,
// and a surface nobody instrumented reads in the report as a surface nobody used. So the shell
// publishes the account scope once and `<Surface>` reads it.
//
// The default is a no-op tracker rather than a throw. A view rendered outside the provider — a
// test, a storybook, a future embed — should render, not fail: measurement is a diagnostic, and
// §17.8's rule that it never blocks work applies to its absence as much as to its failure.

const SurfaceScopeContext = createContext(null);

export function SurfaceScopeProvider({ accountId = null, programId = null, children }) {
  const value = useMemo(
    () => createTracker(api.recordEvent, { accountId, programId, sessionId: sessionId() }),
    [accountId, programId],
  );
  return createElement(SurfaceScopeContext.Provider, { value }, children);
}

/** The ambient tracker, or a no-op when there is no provider above. Never null. */
export function useSurfaceTracker() {
  return useContext(SurfaceScopeContext) || noopTrack;
}

function noopTrack() { return null; }

// --- Stage 17 Slice 3: the retirement half of the same wrapper ------------------------------
//
// §7.3 asks one component to do both instrumentation and retirement, so both halves are ambient and
// read by the same `surfaceKey`. Fetched once for the app rather than per surface: it is one small
// map over a code-defined registry, and a request per wrapped section would put dozens of
// round-trips in front of every screen for a diagnostic feature. Once *per applied decision*, not
// once ever — see the provider.
//
// The default is an **empty map**, which `presentationFor` reads as `normal` for every key. A
// failed or pending fetch therefore shows everything, which is the direction to fail: wrongly
// showing a surface costs clutter, and wrongly hiding one costs something the operator cannot find
// and the usage data will never mention.

const RetirementContext = createContext(null);

export function SurfaceRetirementProvider({ children }) {
  const [state, setState] = useState(null);
  // Once per session, plus once per applied decision. "Fetched once" was the right instinct about
  // *per-surface* requests and the wrong amount of never: an operator who retired four surfaces in
  // Operations then walked the app to check went on seeing all four, because the map they were
  // read against was the one fetched before the decision. A retirement that appears to have done
  // nothing is one somebody applies twice.
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    api.surfaceRetirement()
      .then((body) => { if (live) setState(body && body.surfaces ? body.surfaces : {}); })
      // Note the empty map on failure is only correct for the *first* load. On a refetch it would
      // reveal every retired surface at once on a dropped connection, so the last good map stands.
      .catch(() => { if (live) setState((prev) => prev || {}); });
    return () => { live = false; };
  }, [tick]);

  // Stable across renders on purpose. A `refresh` that changed identity every time the map loaded
  // would churn the dependency list of any callback holding it, and a consumer that refetches from
  // an effect keyed on that callback refetches forever.
  const refresh = useCallback(() => setTick((n) => n + 1), []);
  const value = useMemo(() => ({
    surfaces: state || {}, loaded: state !== null, refresh,
  }), [state, refresh]);
  return createElement(RetirementContext.Provider, { value }, children);
}

/** The retirement map, or an empty one when there is no provider above. Never null. */
export function useSurfaceRetirement() {
  return useContext(RetirementContext) || EMPTY_RETIREMENT;
}

const EMPTY_RETIREMENT = { surfaces: {}, loaded: false, refresh: () => {} };

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
