import test from "node:test";
import assert from "node:assert/strict";

import {
  EVENT_NAMES, SESSION_STORAGE_KEY,
  buildEvent, createTracker, currentPhase, departureProperties, dueState, ensureSessionId,
  groupProperties, moveProperties, moveThatLeft, ownerSide, pathViewProperties,
  requirementProperties, retryProperties, snoozeDays,
} from "./telemetry.js";

const TODAY = "2026-08-05";

/**
 * A response body that is deliberately full of the things §17.2 prohibits: titles, sentences,
 * person names, an email address, and a source span. Every deriver in this module is pointed at
 * it, and the assertion is always the same — none of it comes out the other side.
 */
function bodyWithFreeText() {
  return {
    scope: { mode: "program", account_id: "acc-1", account_name: "Northwind Manufacturing" },
    stamp: { data_current_through: `${TODAY}T09:00:00+00:00` },
    ranking_rules: { version: "v1-2026-08-04" },
    program_paths: [{ program_id: "prog-1", program_name: "Launch", current_phase: "launch" }],
    next_move: {
      id: "task:t-1",
      source_type: "task",
      title: "Send the revised deployment brief to the steering group",
      reason: "Overdue since 2026-07-28 and owned by you",
      reason_code: "overdue_operator_task",
      band: 4,
      urgency: "now",
      due_date: "2026-07-28",
      owner: { id: "p-1", name: "Dana Whitfield", email: "dana.whitfield@example.invalid" },
      responsible_party: null,
      provenance: { label: "Task · recorded 2026-07-01", source_span: "line 42 of the transcript" },
    },
    empty_state: null,
    coverage: {
      status: "partial",
      omitted_sources: [{ source: "commitments", message: "the commitments table is locked" }],
      readiness: { status: "partial", omitted: ["value_realisation"] },
    },
    work: {
      you_own: [{ id: "task:t-1" }, { id: "gate:g-1" }],
      waiting_on_customer: [{ id: "commitment:c-1" }],
    },
  };
}

function everyValue(object) {
  return Object.values(object).map((value) => String(value));
}

test("the client event names are §17.3's sixteen plus the drop zone's six", () => {
  assert.equal(EVENT_NAMES.length, 22);
  assert.equal(new Set(EVENT_NAMES).size, 22);
  assert.ok(EVENT_NAMES.includes("account_path_viewed"));
  assert.ok(EVENT_NAMES.includes("execution_path_retry"));
  assert.ok(EVENT_NAMES.includes("drop_zone_shown"));
  assert.ok(EVENT_NAMES.includes("drop_receipt_opened"));
  // Frozen because a view that pushed onto it would be inventing an event the server will drop.
  assert.throws(() => EVENT_NAMES.push("account_renamed"));
});

test("an event name outside the allowlist is never sent", () => {
  const sent = [];
  const track = createTracker((payload) => sent.push(payload), { clock: () => "2026-08-05T09:00:00Z" });
  assert.equal(track("account_path_viewed", { has_next_move: true }) !== null, true);
  assert.equal(track("next_move_hovered", { source_type: "task" }), null);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].event_name, "account_path_viewed");
});

test("a sender that throws never reaches the caller", () => {
  // §17.4: telemetry failure never blocks user work. The view calls this inline in a click
  // handler, so a throw here would take the navigation with it.
  const track = createTracker(() => { throw new Error("network down"); },
    { clock: () => "2026-08-05T09:00:00Z" });
  assert.doesNotThrow(() => track("next_move_opened", { source_type: "task" }));
});

test("a missing sender is not an error", () => {
  const track = createTracker(undefined, { clock: () => "2026-08-05T09:00:00Z" });
  assert.doesNotThrow(() => track("next_move_opened", { source_type: "task" }));
});

test("the envelope carries context, a timestamp, and nothing else", () => {
  const payload = buildEvent("next_move_opened", {
    accountId: "acc-1", programId: "prog-1", rankingRuleVersion: "v1-2026-08-04",
    sessionId: "7f3c2a10-9b4d-4e21-8f60-1c2d3e4f5a6b", occurredAt: "2026-08-05T09:00:00Z",
    properties: { source_type: "task", reason_code: "overdue_operator_task" },
  });
  assert.deepEqual(Object.keys(payload).sort(), [
    "account_id", "event_name", "occurred_at", "program_id", "properties",
    "ranking_rule_version", "session_id",
  ]);
  assert.deepEqual(payload.properties,
    { source_type: "task", reason_code: "overdue_operator_task" });
});

test("null and undefined properties are dropped rather than measured as values", () => {
  const payload = buildEvent("next_move_opened",
    { properties: { source_type: "task", reason_code: null, band: undefined, urgency: "now" } });
  assert.deepEqual(payload.properties, { source_type: "task", urgency: "now" });
});

test("the session identifier is minted once and reused", () => {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  let minted = 0;
  const mint = () => `7f3c2a10-9b4d-4e21-8f60-1c2d3e4f5a${String(++minted).padStart(2, "0")}`;
  const first = ensureSessionId(storage, mint);
  const second = ensureSessionId(storage, mint);
  assert.equal(first, second);
  assert.equal(minted, 1);
  assert.equal(store.get(SESSION_STORAGE_KEY), first);
  // The server's rule: a pseudonymous slug, never anything that could name a person.
  assert.match(first, /^[a-z0-9][a-z0-9-]{7,63}$/);
});

test("storage that refuses to write still yields a usable session", () => {
  const hostile = {
    getItem: () => { throw new Error("blocked"); },
    setItem: () => { throw new Error("blocked"); },
  };
  const id = ensureSessionId(hostile, () => "7f3c2a10-9b4d-4e21-8f60-1c2d3e4f5a6b");
  assert.equal(id, "7f3c2a10-9b4d-4e21-8f60-1c2d3e4f5a6b");
});

test("the path-view deriver reports shape and coverage, never content", () => {
  const props = pathViewProperties(bodyWithFreeText());
  assert.deepEqual(props, {
    has_next_move: true,
    empty_state_variant: null,
    coverage_status: "partial",
    readiness_coverage: "partial",
    program_count: 1,
    you_own_count: 2,
    waiting_count: 1,
    scope_mode: "program",
    current_phase: "launch",
  });
  // Execution coverage and readiness coverage stay two claims, never one merged number (§13.6).
  assert.ok("coverage_status" in props && "readiness_coverage" in props);
});

test("an empty state is measured by its variant, not by its message", () => {
  const body = bodyWithFreeText();
  body.next_move = null;
  body.empty_state = {
    variant: "waiting_on_customer",
    message: "No operator-owned action is due. A customer responsibility is open.",
  };
  const props = pathViewProperties(body);
  assert.equal(props.has_next_move, false);
  assert.equal(props.empty_state_variant, "waiting_on_customer");
  assert.ok(!everyValue(props).some((v) => v.includes(" ")));
});

test("no deriver emits a title, a name, an address, a reason sentence, or a span", () => {
  const body = bodyWithFreeText();
  const forbidden = [
    "Northwind Manufacturing", "Send the revised deployment brief", "Dana Whitfield",
    "dana.whitfield@example.invalid", "Overdue since", "line 42 of the transcript",
    "the commitments table is locked", "Launch",
  ];
  const derived = [
    pathViewProperties(body),
    moveProperties(body.next_move),
    retryProperties(body.coverage, 1),
    groupProperties("you_own", body.work.you_own),
    requirementProperties({
      pillar_key: "commercial_clarity", state: "not_met", applicability: "required",
      freshness: { status: "stale" },
      title: "Signed order form on file",
      reason: "No accepted evidence is linked to this requirement",
    }, body.coverage.readiness),
  ];
  for (const props of derived) {
    for (const value of everyValue(props)) {
      for (const text of forbidden) {
        assert.ok(!value.includes(text), `"${text}" leaked into a measured value: ${value}`);
      }
    }
  }
});

test("every derived string value satisfies the server's slug rule", () => {
  // The structural guarantee, asserted rather than assumed: a slug cannot hold a sentence, a
  // name, or an address, so a deriver that starts emitting one fails here rather than at the API.
  const body = bodyWithFreeText();
  const derived = Object.assign({},
    pathViewProperties(body), moveProperties(body.next_move), retryProperties(body.coverage, 2),
    groupProperties("waiting_on_customer", body.work.waiting_on_customer));
  for (const [key, value] of Object.entries(derived)) {
    if (typeof value !== "string") continue;
    assert.match(value, /^[a-z0-9][a-z0-9_.:-]{0,63}$/, `${key} is not a bounded slug: ${value}`);
  }
});

test("the phase is measured only when a single program is in scope", () => {
  const body = bodyWithFreeText();
  assert.equal(currentPhase(body), "launch");
  // An account view has several current phases; naming one would attribute the event to a phase
  // the reader never chose.
  const account = { ...body, scope: { mode: "all_programs" } };
  assert.equal(currentPhase(account), null);
  assert.equal(pathViewProperties(account).current_phase, null);
});

test("owner side distinguishes a customer wait with no internal follow-up", () => {
  // §17.5 question 4 exists precisely to find these, so they cannot share a value with the rest.
  assert.equal(ownerSide({ owner: { id: "p-1" } }), "operator");
  assert.equal(ownerSide({}), "operator_unassigned");
  assert.equal(ownerSide({ responsible_party: { id: "p-2" }, owner: { id: "p-1" } }),
    "customer_with_follow_up");
  assert.equal(ownerSide({ responsible_party: { id: "p-2" } }), "customer_unowned");
});

test("due state is a bucket, never a date", () => {
  assert.equal(dueState({}), "no_due_date");
  assert.equal(dueState({ due_date: "2026-07-28" }, TODAY), "overdue");
  assert.equal(dueState({ due_date: TODAY }, TODAY), "due_today");
  assert.equal(dueState({ due_date: "2026-09-01" }, TODAY), "dated");
  // With no stamp to compare against it falls back to the server's own urgency word.
  assert.equal(dueState({ due_date: "2026-07-28", urgency: "now" }), "overdue");
  assert.equal(dueState({ due_date: "2026-08-07", urgency: "soon" }), "due_soon");
});

test("a snooze is measured in whole days, and a condition-only snooze in none", () => {
  assert.equal(snoozeDays(TODAY, "2026-08-12"), 7);
  assert.equal(snoozeDays(TODAY, null), null);
  assert.equal(snoozeDays(TODAY, "2020-01-01"), null);
});

test("the move deriver keeps the band it was ranked by", () => {
  // §17.6 step 7: an ordering review needs the band as well as the reason code, or a rule change
  // silently reinterprets every event recorded before it.
  const props = moveProperties(bodyWithFreeText().next_move);
  assert.equal(props.band, 4);
  assert.equal(props.reason_code, "overdue_operator_task");
  assert.equal(props.owner_side, "operator");
  assert.equal(props.due_state, "overdue");
});

test("a retry names the failed adapter, not its error message", () => {
  const body = bodyWithFreeText();
  assert.deepEqual(retryProperties(body.coverage, 1),
    { failure_kind: "partial", omitted_source: "commitments", attempt: 1 });
  // A request that never returned has no coverage block at all.
  assert.deepEqual(retryProperties(null, 2),
    { failure_kind: "request_failed", omitted_source: null, attempt: 2 });
});

test("a requirement is measured on four independent axes", () => {
  // State, freshness, coverage, and applicability never collapse into one another
  // (RELATIONSHIP-READINESS-SPEC.md); the event carries all four separately for the same reason.
  const props = requirementProperties({
    pillar_key: "commercial_clarity", state: "met", applicability: "required",
    freshness: { status: "stale" },
  }, { status: "complete" });
  assert.deepEqual(props, {
    pillar: "commercial_clarity", requirement_state: "met", freshness: "stale",
    applicability: "required", coverage: "complete",
  });
});

test("a requirement with no recorded state is measured as unknown, not omitted", () => {
  const props = requirementProperties({ pillar_key: "commercial_clarity" });
  assert.equal(props.requirement_state, "unknown");
});

test("the departure event is named for the absence it observes, not for a completion", () => {
  // The path never sees *why* a recommended row is gone — it may have been closed, cancelled,
  // archived, or aged out of its band. A name with "completed" in it would assert the one reading
  // the data cannot support, so neither the event nor its deriver carries the word.
  assert.ok(EVENT_NAMES.includes("next_move_left_list"));
  assert.ok(!EVENT_NAMES.includes("next_move_completed"));
  assert.ok(!EVENT_NAMES.some((name) => name.startsWith("next_move") && name.includes("completed")));
  // `phase_transition_completed` keeps its name: an operator recorded that transition, so the
  // completion is observed rather than inferred from an absence.
  assert.ok(EVENT_NAMES.includes("phase_transition_completed"));
});

test("the departure deriver drops the ranking properties the closure cannot speak for", () => {
  const move = bodyWithFreeText().next_move;
  const props = departureProperties(move, TODAY);
  assert.deepEqual(props, {
    source_type: "task", reason_code: "overdue_operator_task",
    urgency: "now", due_state: "overdue",
  });
  // `band` and `owner_side` describe how the row was ranked and who held it when it was
  // recommended. Neither is a fact about its departure, so neither is measured as one.
  assert.ok(!("band" in props) && !("owner_side" in props));
});

test("a row missing from a partial response is not reported as having left the list", () => {
  // The carried-forward-good-state error, in the measurement layer: a source that could not be
  // read makes rows disappear, and counting that as a departure would read as progress.
  const remembered = {
    id: "task:t-1", accountId: "acc-1", programId: null, snoozed: false,
    properties: { source_type: "task", reason_code: "overdue_operator_task" },
  };
  const gone = {
    scope: { account_id: "acc-1" }, coverage: { status: "complete" },
    next_move: null, work: { you_own: [], waiting_on_customer: [] },
  };
  assert.deepEqual(moveThatLeft(remembered, gone), remembered.properties);
  assert.equal(moveThatLeft(remembered, { ...gone, coverage: { status: "partial" } }), null);
  // Still listed, a different account, and a snooze each mean something else.
  assert.equal(moveThatLeft(remembered, { ...gone, work: { you_own: [{ id: "task:t-1" }] } }), null);
  assert.equal(moveThatLeft(remembered, { ...gone, scope: { account_id: "acc-2" } }), null);
  assert.equal(moveThatLeft({ ...remembered, snoozed: true }, gone), null);
});
