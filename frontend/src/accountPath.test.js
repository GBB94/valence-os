import test from "node:test";
import assert from "node:assert/strict";

import {
  GROUP_CAP, LANE_CAP,
  capped, coverageNotice, dayDelta, emptyStateCopy, laneOrder, ownerLabel, phaseAria,
  phaseState, primaryActionLabel, sourceLabel, urgencyLabel, waitingLabel, withoutNextMove,
} from "./accountPath.js";

const TODAY = "2026-08-04"; // a Tuesday

test("an unrecognized phase state renders as Unknown and reports itself", () => {
  // §10.2: a future enum value must not be treated as complete or silently dropped.
  const known = phaseState("complete");
  assert.equal(known.label, "Complete");
  assert.equal(known.recognized, true);
  const future = phaseState("provisionally_waived_pending_review");
  assert.equal(future.label, "Unknown");
  assert.equal(future.recognized, false);
  assert.equal(future.mark, "unknown");
});

test("every phase state carries a word and a shape, not only a colour", () => {
  for (const key of ["complete", "current", "future", "blocked", "waived", "not_applicable",
    "unknown"]) {
    const state = phaseState(key);
    assert.ok(state.label.length > 0, `${key} has no label`);
    assert.ok(state.symbol.length > 0, `${key} has no shape`);
  }
});

test("the primary button names the object it opens", () => {
  assert.equal(primaryActionLabel({ source_type: "task" }), "Open task");
  assert.equal(primaryActionLabel({ source_type: "commitment" }), "Follow up");
  assert.equal(primaryActionLabel({ source_type: "risk" }), "Resolve blocker");
  assert.equal(primaryActionLabel({ source_type: "issue" }), "Resolve blocker");
  assert.equal(primaryActionLabel({ source_type: "milestone" }), "Prepare");
  assert.equal(primaryActionLabel({ source_type: "phase_gate_item" }), "Open requirement");
  assert.equal(primaryActionLabel({ source_type: "something_new" }), "Open record");
});

test("urgency language is specific and never neutral about a missing date", () => {
  assert.deepEqual(urgencyLabel({ due_date: "2026-07-26" }, TODAY),
    { text: "9 days overdue", tone: "risk" });
  assert.deepEqual(urgencyLabel({ due_date: "2026-08-03" }, TODAY),
    { text: "1 day overdue", tone: "risk" });
  assert.deepEqual(urgencyLabel({ due_date: TODAY }, TODAY), { text: "Due today", tone: "risk" });
  assert.deepEqual(urgencyLabel({ due_date: "2026-08-05" }, TODAY),
    { text: "Due tomorrow", tone: "warn" });
  assert.deepEqual(urgencyLabel({ due_date: "2026-08-07" }, TODAY),
    { text: "Due Friday", tone: "warn" });
  assert.deepEqual(urgencyLabel({ due_date: "2026-09-15" }, TODAY),
    { text: "Due Sep 15", tone: "neutral" });
  // A missing due date is a fact the row states, not a blank the reader has to interpret.
  assert.deepEqual(urgencyLabel({ due_date: null }, TODAY),
    { text: "No due date", tone: "neutral" });
});

test("day deltas are calendar days and survive a month boundary", () => {
  assert.equal(dayDelta("2026-08-04", "2026-08-11"), 7);
  assert.equal(dayDelta("2026-07-31", "2026-08-01"), 1);
  assert.equal(dayDelta("2026-08-04", "2026-07-26"), -9);
  assert.equal(dayDelta("2026-08-04", null), null);
});

test("an absent owner is stated, not omitted", () => {
  assert.equal(ownerLabel({ owner: { name: "Operator" } }), "Operator");
  assert.equal(ownerLabel({ owner: null }), "Unassigned");
  assert.equal(waitingLabel({ responsible_party: { name: "Programme lead" } }),
    "Waiting on Programme lead");
  assert.equal(waitingLabel({ responsible_party: null }), "Waiting on the customer");
});

test("lanes lead with blocked or at-risk programmes, then date, then name", () => {
  const lanes = laneOrder([
    { program_name: "Zebra rollout", steps: [{ state: "current" }],
      next_milestone: { target_date: "2026-08-10" } },
    { program_name: "Alpha rollout", steps: [{ state: "current" }], next_milestone: null },
    { program_name: "Delta rollout", steps: [{ state: "blocked" }],
      next_milestone: { target_date: "2026-12-01" } },
    { program_name: "Beta rollout", steps: [{ state: "current" }],
      next_milestone: { target_date: "2026-08-10", at_risk: true } },
  ]);
  // §6.3 sorts by the *nearest* blocked/at-risk milestone, so within the urgent group the closer
  // date leads: Beta is at risk on Aug 10, Delta is blocked but not until December.
  assert.deepEqual(lanes.map((l) => l.program_name),
    ["Beta rollout", "Delta rollout", "Zebra rollout", "Alpha rollout"]);
});

test("an account with several programmes keeps one lane each and no aggregate", () => {
  const lanes = laneOrder([
    { program_name: "One", steps: [{ state: "current" }] },
    { program_name: "Two", steps: [{ state: "future" }] },
  ]);
  assert.equal(lanes.length, 2);
  assert.ok(!lanes.some((l) => l.program_id === null || l.current_phase === "aggregate"));
});

test("caps report what they left behind", () => {
  const items = Array.from({ length: 9 }, (_, i) => ({ id: `task:${i}` }));
  const group = capped(items, GROUP_CAP);
  assert.equal(group.shown.length, 5);
  assert.equal(group.remaining, 4);
  assert.equal(capped(items.slice(0, 2), LANE_CAP).remaining, 0);
  assert.deepEqual(capped(null, GROUP_CAP), { shown: [], remaining: 0 });
});

test("the promoted next move is not repeated in You own", () => {
  const items = [{ id: "task:1" }, { id: "task:2" }];
  assert.deepEqual(withoutNextMove(items, { id: "task:1" }).map((i) => i.id), ["task:2"]);
  assert.equal(withoutNextMove(items, null).length, 2);
});

test("each empty state has a heading and keeps the server's own sentence", () => {
  const waiting = emptyStateCopy({ variant: "waiting_on_customer", message: "A wait is open." });
  assert.equal(waiting.title, "Waiting on the customer");
  assert.equal(waiting.message, "A wait is open.");
  assert.equal(waiting.recognized, true);

  const thin = emptyStateCopy({ variant: "insufficient_plan_data", message: "No program." });
  assert.equal(thin.action.tab, "plan");

  const gate = emptyStateCopy({
    variant: "prepare_for_next_gate", message: "Nothing is urgent.",
    requirement: { key: "sponsor_alignment", state: "thin" },
  });
  assert.equal(gate.requirement.state, "thin");

  // An unknown variant still renders its sentence rather than blanking the panel.
  const odd = emptyStateCopy({ variant: "a_new_variant", message: "Something else." });
  assert.equal(odd.recognized, false);
  assert.equal(odd.message, "Something else.");

  assert.equal(emptyStateCopy(null), null);
});

test("partial coverage is named and never reads as caught up", () => {
  assert.equal(coverageNotice({ status: "complete" }), null);
  const partial = coverageNotice({
    status: "partial",
    omitted_sources: [{ source: "milestones", detail: "OperationalError: no such table" }],
    warnings: ["milestones could not be read; its items are missing from this view"],
  });
  assert.equal(partial.status, "partial");
  assert.match(partial.message, /milestones/);
  assert.match(partial.message, /Partial coverage/);
  assert.equal(partial.warnings.length, 1);

  const gone = coverageNotice({ status: "unavailable", omitted_sources: [], warnings: [] });
  assert.match(gone.message, /nothing here can be treated as complete/);
});

test("readiness coverage is not merged into execution coverage", () => {
  // The readiness card reports its own coverage in its own words. Folding the two together would
  // let a failed evaluator read as a missing task, or the reverse. This asserts the readiness
  // block itself is ignored here — an earlier version of this test used a `warnings` entry to make
  // the same point, which is a different field and let the suppression defect below through.
  const notice = coverageNotice({
    status: "complete",
    warnings: [],
    readiness: { status: "partial", failed_evaluators: ["budget_owner"], warnings: ["unknown"] },
  });
  assert.equal(notice, null);
});

test("a complete read still reports what it withheld", () => {
  // A snoozed row is hidden from a response the server calls complete. Reporting only the failures
  // would let the one suppression the operator caused disappear, which is the Slice 3 rule read
  // backwards: a suppression is subtractive and always reported.
  const notice = coverageNotice({
    status: "complete", omitted_sources: [],
    warnings: ["1 item is snoozed and is not shown here"],
  });
  assert.equal(notice.status, "complete");
  assert.equal(notice.message, null, "a withheld row is not a failure and gets no failure sentence");
  assert.match(notice.warnings[0], /snoozed/);

  // And a warning that arrives beside a real failure is not dropped for having worse company.
  const both = coverageNotice({
    status: "partial",
    omitted_sources: [{ source: "milestones", detail: "OperationalError: no such table" }],
    warnings: ["1 item is snoozed and is not shown here"],
  });
  assert.match(both.message, /milestones/);
  assert.equal(both.warnings.length, 1);
});

test("source labels are the section 6.5 vocabulary, separate from evidence provenance", () => {
  assert.equal(sourceLabel({ kind: "interaction", label: "From Jul 31 onboarding call" }),
    "From Jul 31 onboarding call");
  assert.equal(sourceLabel({ kind: "manual", label: "Added manually" }), "Added manually");
  assert.equal(sourceLabel(null), null);
  // `confirmed_source` and friends belong to readiness provenance and must never appear here.
  assert.equal(sourceLabel({ label: "Account standard" }), "Account standard");
});

test("a blocked phase names its reason to assistive technology", () => {
  assert.equal(phaseAria({ label: "Launch", state: "blocked", blocking_reason: "Works council review open" }),
    "Launch: Blocked — Works council review open");
  assert.equal(phaseAria({ label: "Launch", state: "current", missing_count: 2 }),
    "Launch: Current, 2 gate items incomplete");
  assert.equal(phaseAria({ label: "Launch", state: "current", missing_count: 1 }),
    "Launch: Current, 1 gate item incomplete");
  assert.equal(phaseAria({ label: "Renewal", state: "future", missing_count: 0 }),
    "Renewal: Not started");
});
