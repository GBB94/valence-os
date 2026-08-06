/**
 * Account Path Slice 7 — the client half of the product-measurement boundary
 * (`ACCOUNT-PATH-SPEC.md` §17).
 *
 * Pure module. It imports nothing — not even `./api` — for two reasons. The repo's frontend tests
 * are `node --test` over plain modules and `api.js` reads `import.meta.env`, which throws there;
 * and a measurement module that owns its own transport is a measurement module that can fail a
 * page. The caller passes a `send` function in, and `createTracker` guarantees a throw from it
 * never reaches the view.
 *
 * The client is deliberately **not** a second validator. `backend/app/telemetry.py` holds the one
 * contract: the sixteen event names, the per-event property allowlist, and the slug rule that
 * structurally excludes titles, names, and free text (§17.2). What lives here instead are the
 * *derivers* — the functions that turn a response body or a path row into bounded enum fields.
 * They are the place a person name could leak into a payload, so they are what the tests point at:
 * `telemetry.test.js` feeds them bodies full of titles and people and asserts none of it survives.
 *
 * The one thing duplicated from the server is the list of event names, so a typo is caught at the
 * call site rather than dropped by a production server that has been told to ignore unknown
 * events. `test_account_path_slice7.py::test_the_client_event_names_match_the_server_allowlist`
 * fails if the two lists ever drift.
 */

/** §17.3. Order matches the spec section so the two can be read side by side. */
export const EVENT_NAMES = Object.freeze([
  "account_path_viewed",
  "next_move_opened",
  "next_move_snoozed",
  "next_move_left_list",
  "successor_action_created",
  "execution_group_opened",
  "program_path_filtered",
  "requirement_opened",
  "requirement_action_created",
  "proposal_review_opened",
  "proposal_accepted",
  "proposal_rejected",
  "phase_readiness_opened",
  "phase_transition_completed",
  "execution_native_target_opened",
  "execution_path_retry",
]);

const NAMES = new Set(EVENT_NAMES);
export const SESSION_STORAGE_KEY = "valence-measurement-session";

/**
 * A pseudonymous per-installation identifier, minted once and kept in local storage. It identifies
 * a browser profile, never a person: nothing anywhere maps it to a name, and the server's
 * `^[a-z0-9][a-z0-9-]{7,63}$` rule means it can only ever hold a slug. `crypto.randomUUID()`
 * satisfies that shape; storage and the mint are arguments so this is testable without either.
 */
export function ensureSessionId(storage, mint) {
  try {
    const existing = storage?.getItem?.(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const minted = String(mint());
    storage?.setItem?.(SESSION_STORAGE_KEY, minted);
    return minted;
  } catch {
    // Private-mode storage throws on write. A session that lasts one page load still measures
    // honestly; refusing to measure at all would be the worse answer.
    return String(mint());
  }
}

/** Drops keys with nothing to say. A null property is absence, and the server strips it anyway. */
function present(properties) {
  const out = {};
  for (const [key, value] of Object.entries(properties || {})) {
    if (value !== null && value !== undefined) out[key] = value;
  }
  return out;
}

/**
 * The §17.2 envelope. `occurredAt` and the context fields are injected rather than read from
 * globals so a test can assert an exact payload.
 */
export function buildEvent(eventName, {
  accountId = null, programId = null, rankingRuleVersion = null,
  sessionId = null, occurredAt = null, properties = null,
} = {}) {
  return {
    event_name: eventName,
    occurred_at: occurredAt,
    session_id: sessionId,
    account_id: accountId || null,
    program_id: programId || null,
    ranking_rule_version: rankingRuleVersion || null,
    properties: present(properties),
  };
}

/**
 * Wraps a sender into a `track(name, properties)` a view can call inline.
 *
 * Two guarantees, both from §17.4 — *telemetry failure never blocks user work*: an unknown event
 * name returns without sending, and any throw from `send` is swallowed here. `send` itself is
 * expected to be fire-and-forget; this catch covers the synchronous path only, which is why
 * `api.recordEvent` swallows its own rejection as well.
 */
export function createTracker(send, context = {}) {
  const { clock = () => new Date().toISOString() } = context;
  return function track(eventName, properties) {
    if (!NAMES.has(eventName)) return null;
    const payload = buildEvent(eventName, {
      ...context, occurredAt: clock(), properties,
    });
    try {
      send?.(payload);
    } catch {
      /* a diagnostic sink must never surface its own faults */
    }
    return payload;
  };
}

// --- derivers ---------------------------------------------------------------------------------
//
// Everything below turns a response object into bounded enum fields. None of them reads a title,
// a name, a reason sentence, or any other free text — that is the property being tested, not an
// incidental one.

const coverageStatus = (coverage) => coverage?.status || null;

/** §17.5 question 1 and 8: was an explainable move offered, and was the answer trustworthy? */
export function pathViewProperties(body) {
  if (!body) return {};
  const work = body.work || {};
  return {
    has_next_move: Boolean(body.next_move),
    empty_state_variant: body.empty_state?.variant || null,
    coverage_status: coverageStatus(body.coverage),
    readiness_coverage: coverageStatus(body.coverage?.readiness),
    program_count: (body.program_paths || []).length,
    you_own_count: (work.you_own || []).length,
    waiting_count: (work.waiting_on_customer || []).length,
    scope_mode: body.scope?.mode || null,
    current_phase: currentPhase(body),
  };
}

/**
 * The phase only when one program is in scope. An account with several programs has several
 * current phases, and picking one would attribute the event to a phase the reader never chose —
 * the same reason the path itself refuses to stamp a phase on a Task (§10.2).
 */
export function currentPhase(body) {
  const paths = body?.program_paths || [];
  if (body?.scope?.mode !== "program" || paths.length !== 1) return null;
  return paths[0].current_phase || null;
}

/** §17.5 questions 2, 3 and 7: which recommendation, and what happened to it. */
export function moveProperties(row) {
  if (!row) return {};
  return {
    source_type: row.source_type || null,
    reason_code: row.reason_code || null,
    band: typeof row.band === "number" ? row.band : null,
    urgency: row.urgency || null,
    owner_side: ownerSide(row),
    due_state: dueState(row),
  };
}

/**
 * The four properties `next_move_left_list` declares. Narrower than `moveProperties` on purpose:
 * `band` and `owner_side` describe how a row was ranked and who held it at the moment it was
 * recommended, and neither is a fact about the closure.
 */
export function departureProperties(row, today = null) {
  if (!row) return {};
  return {
    source_type: row.source_type || null,
    reason_code: row.reason_code || null,
    urgency: row.urgency || null,
    due_state: dueState(row, today),
  };
}

/**
 * §17.5 question 4. `waiting_on_customer` rows carry a `responsible_party` on the customer side
 * and an `owner` as the internal follow-up; a customer wait with no follow-up owner is exactly
 * the gap the question asks about, so it gets its own value rather than collapsing into `none`.
 */
export function ownerSide(row) {
  if (row?.responsible_party) return row.owner ? "customer_with_follow_up" : "customer_unowned";
  return row?.owner ? "operator" : "operator_unassigned";
}

/** Coarse enough to be diagnostic, never a date. `today` is the response's own stamp. */
export function dueState(row, today = null) {
  if (!row?.due_date) return "no_due_date";
  if (!today) return row.urgency === "now" ? "overdue" : row.urgency === "soon" ? "due_soon" : "dated";
  if (row.due_date < today) return "overdue";
  return row.due_date === today ? "due_today" : "dated";
}

/** Whole days between the response stamp and a chosen snooze date; a condition-only snooze has none. */
export function snoozeDays(today, until) {
  if (!today || !until) return null;
  const days = Math.round((Date.parse(`${until}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`))
    / 86_400_000);
  return Number.isFinite(days) && days >= 0 && days <= 400 ? days : null;
}

/** §17.5 question 5: which requirement gaps recur. Keys and states only; never the requirement text. */
export function requirementProperties(row, coverage = null) {
  if (!row) return {};
  return {
    pillar: row.pillar_key || null,
    requirement_state: row.state || "unknown",
    freshness: row.freshness?.status || row.freshness || null,
    applicability: row.applicability || null,
    coverage: coverageStatus(coverage) || (typeof coverage === "string" ? coverage : null),
  };
}

/**
 * §17.5 question 3, and the one deriver that infers rather than reads.
 *
 * Account Path never closes anything (§7.1) — closure happens in the native record, on a screen
 * that has no idea a row was ever recommended. So the only thing the path can observe is that a
 * move it recommended, and watched somebody open, is absent from a later response. Three cases are
 * excluded rather than counted, because each has a different meaning:
 *
 * - a snoozed row, which has its own event and is not a completion;
 * - a different account or program, where absence says nothing;
 * - an incomplete-coverage response, where a row can be missing because a source could not be
 *   read. Counting that as a completion is exactly the carried-forward-good-state error the rest
 *   of the app refuses to make.
 *
 * `remembered` is `{ id, accountId, programId, snoozed, properties }` from the open event.
 */
export function moveThatLeft(remembered, body) {
  if (!remembered || !body || remembered.snoozed) return null;
  if (body.coverage?.status !== "complete") return null;
  if ((body.scope?.account_id || null) !== (remembered.accountId || null)) return null;
  if ((body.scope?.program_id || null) !== (remembered.programId || null)) return null;
  const work = body.work || {};
  const stillListed = [body.next_move, ...(work.you_own || []), ...(work.waiting_on_customer || [])]
    .some((row) => row && row.id === remembered.id);
  return stillListed ? null : { ...remembered.properties };
}

/** A group is identified by the lane it is, not by the heading it renders. */
export function groupProperties(group, items) {
  return { group, item_count: (items || []).length };
}

/**
 * §11.10 retry. `omitted_source` names the adapter that failed, which is a source identifier the
 * server already publishes in `coverage.omitted_sources`, not an error message.
 */
export function retryProperties(coverage, attempt) {
  const omitted = (coverage?.omitted_sources || [])[0];
  return {
    failure_kind: coverage ? coverageStatus(coverage) || "unavailable" : "request_failed",
    omitted_source: omitted?.source || null,
    attempt: typeof attempt === "number" ? attempt : null,
  };
}
