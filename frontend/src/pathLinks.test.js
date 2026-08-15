import test from "node:test";
import assert from "node:assert/strict";

import {
  actionAdvances, actionLinkGroups, advancementVerdict, dependencyLines, evidenceRows,
  linkControlsWriteNoState, overrideConsequences, relationLabel, unblocksReason,
} from "./pathLinks.js";

const BLOCKED = {
  readiness: "blocked",
  readiness_stamp: "pr1:abc",
  summary: "1 required condition outstanding.",
  coverage: "complete",
  coverage_failures: [],
  proposed_next_phase: "adoption",
  proposed_next_phase_label: "Adoption",
  requirements: [
    { requirement_key: "exec_engaged", label: "Executive sponsor engaged", is_gap: true,
      necessity: "required", state: "thin", reason: "One dated judgment, no second source.",
      available: true },
    { requirement_key: "value_agreed", label: "Value target agreed", is_gap: false,
      necessity: "required", state: "met", available: true },
  ],
  blocking_records: [{ type: "risk", id: "r1", description: "Data feed unavailable" }],
  open_gate_items: [{ id: "gi1", gate_id: "g1", description: "Signed scope attached" }],
};

// --- the verdict ---------------------------------------------------------------------------------

test("blocked and evidence missing are different answers with different words", () => {
  const blocked = advancementVerdict(BLOCKED);
  assert.equal(blocked.label, "Blocked");
  assert.equal(blocked.mark, "risk");

  const thin = advancementVerdict({
    ...BLOCKED, readiness: "insufficient_data",
    requirements: [], blocking_records: [], open_gate_items: [],
    coverage: "partial", coverage_failures: ["field_present"],
  });
  assert.equal(thin.label, "Evidence missing");
  // The distinction the spec turns on: an unreadable evaluator is not an unsatisfied condition,
  // and the caveat has to say so rather than leaving the reader to assume the benign reading.
  assert.match(thin.caveat, /not the same as satisfied/);
  assert.notEqual(thin.mark, blocked.mark);
});

test("ready never implies the phase moves on its own", () => {
  const v = advancementVerdict({ ...BLOCKED, readiness: "ready", requirements: [],
    blocking_records: [], open_gate_items: [] });
  assert.equal(v.label, "Ready to advance");
  assert.equal(v.advancesAutomatically, false);
  assert.match(v.caveat, /explicit decision/);
});

test("an unrecognized verdict reads as unrecognized, never as ready", () => {
  const v = advancementVerdict({ readiness: "probably_fine" });
  assert.equal(v.recognized, false);
  assert.notEqual(v.label, "Ready to advance");
  assert.match(v.caveat, /nothing here should be treated as ready/);
});

test("the reasons are the server's lists, each named by what it is", () => {
  const v = advancementVerdict(BLOCKED);
  assert.deepEqual(v.reasons.map((r) => r.key),
    ["requirements", "blockers", "gate_items"]);
  assert.equal(v.reasons[0].text, "1 required condition not satisfied");
  assert.deepEqual(v.reasons[0].items, ["Executive sponsor engaged"]);
  assert.deepEqual(v.reasons[2].items, ["Signed scope attached"]);
});

test("an unreadable evaluator is reported as a reading failure, not as a chore", () => {
  const v = advancementVerdict({ ...BLOCKED, coverage: "partial",
    coverage_failures: ["field_present", "composite"] });
  const coverage = v.reasons.find((r) => r.key === "coverage");
  assert.equal(coverage.text, "2 evaluators could not be read");
  // Deliberately not phrased as an outstanding condition — nobody can do work to fix it.
  assert.doesNotMatch(coverage.text, /condition|outstanding/);
});

test("the verdict carries the stamp so the advance is checked against what was read", () => {
  assert.equal(advancementVerdict(BLOCKED).stamp, "pr1:abc");
});

// --- the phase-advance dialog --------------------------------------------------------------------

test("a clean advance says the gate is recorded as passed", () => {
  const c = overrideConsequences(BLOCKED);
  assert.equal(c.override, false);
  assert.deepEqual(c.consequences.map((x) => x.key), ["phase", "gate", "history"]);
  assert.match(c.consequences[1].text, /recorded as passed/);
  assert.deepEqual(c.unmet, []);
});

test("an override states plainly that the gap stays, the gate stays open, and no state changes", () => {
  const c = overrideConsequences(BLOCKED, { override: true });
  assert.equal(c.override, true);
  const byKey = Object.fromEntries(c.consequences.map((x) => [x.key, x.text]));
  assert.match(byKey.gap, /does not fill it/);
  assert.match(byKey.gate, /stays open/);
  assert.match(byKey.state, /No readiness state changes/);
  // Each of those three is a risk-toned statement, so the dialog cannot render them as neutral
  // footnotes beside the confirm button.
  const risky = c.consequences.filter((x) => x.tone === "risk").map((x) => x.key);
  assert.deepEqual(risky, ["gap", "gate", "state"]);
});

test("the override dialog lists every condition it is accepting, including legacy gate items", () => {
  const c = overrideConsequences(BLOCKED, { override: true });
  assert.deepEqual(c.unmet.map((u) => u.label),
    ["Executive sponsor engaged", "Signed scope attached"]);
  assert.equal(c.unmet[1].detail, "Legacy gate item");
  // A met condition is not in the list. Overriding accepts the gaps, not the whole gate.
  assert.ok(!c.unmet.some((u) => u.label === "Value target agreed"));
  assert.match(c.consequences.find((x) => x.key === "gap").text, /2 conditions/);
});

test("the dialog names the phase it would move to", () => {
  assert.equal(overrideConsequences(BLOCKED).heading, "Advance to Adoption");
  assert.equal(overrideConsequences(BLOCKED, { override: true }).heading,
    "Override and advance to Adoption");
});

test("no advance path offers a control that writes a readiness state", () => {
  // Asserted rather than reviewed: the override consequence list must contain the sentence that
  // says no state changes, which is only true because there is no route that changes one.
  assert.equal(linkControlsWriteNoState(BLOCKED), true);
});

// --- requirement links ---------------------------------------------------------------------------

const LINKS = [
  { id: "l1", relation: "advances", origin: "operator",
    action: { type: "task", id: "t1", description: "Draft the value case", status: "open" } },
  { id: "l2", relation: "blocks", origin: "proposal",
    action: { type: "commitment", id: "c1", description: "Confirm the budget owner",
      status: "closed" } },
  { id: "l3", relation: "advances", origin: "operator",
    action: { type: "task", id: "t2", description: "Book the review", status: "open" } },
];

test("linked actions group by relation with blockers first", () => {
  const groups = actionLinkGroups(LINKS);
  assert.deepEqual(groups.map((g) => g.relation), ["blocks", "advances"]);
  assert.deepEqual(groups[0].label, "Blocks");
  assert.equal(groups[1].items.length, 2);
});

test("an accepted proposal is labelled differently from an operator's own link", () => {
  const groups = actionLinkGroups(LINKS);
  assert.equal(groups[0].items[0].originLabel, "From an accepted proposal");
  assert.equal(groups[1].items[0].originLabel, "Linked by an operator");
});

test("a closed action stays visible on the requirement", () => {
  // Closing settles the action, never the requirement. Dropping the row would make a requirement
  // that somebody worked on look untouched.
  const groups = actionLinkGroups(LINKS);
  assert.equal(groups[0].items[0].closed, true);
  assert.equal(groups[1].items[0].closed, false);
});

test("an unrecognized relation reads as itself rather than as advances", () => {
  assert.equal(relationLabel("supersedes"), "supersedes");
  assert.equal(relationLabel("follow_up_for"), "Follow-up for");
  const groups = actionLinkGroups([{ id: "x", relation: "supersedes", action: { id: "t" } }]);
  assert.equal(groups[0].label, "supersedes");
});

// --- evidence ------------------------------------------------------------------------------------

test("evidence that cannot move the state says so instead of looking accepted", () => {
  const [supporting, context] = evidenceRows([
    { id: "e1", evidence_type: "decision", supporting: true, reviewed_on: "2026-08-01",
      reviewed_by: "operator" },
    { id: "e2", evidence_type: "interaction", supporting: false },
  ]);
  assert.equal(supporting.supportingLabel, "Counts toward this condition");
  assert.equal(context.supportingLabel, "Context only");
  assert.match(context.supportingHint, /cannot change the state/);
  assert.notEqual(supporting.mark, context.mark);
});

test("an unreviewed attachment is a fact, not a warning", () => {
  const [row] = evidenceRows([{ id: "e", evidence_type: "decision", supporting: true }]);
  assert.equal(row.reviewLabel, "Not reviewed");
  assert.equal(row.canReview, true);
  assert.equal(row.mark, "ok");
});

test("a retracted attachment keeps its reason and loses its controls", () => {
  const [row] = evidenceRows([{ id: "e", evidence_type: "decision", supporting: true,
    retracted_at: "2026-08-02T00:00:00Z", retracted_reason: "Superseded by a later decision" }]);
  assert.match(row.reviewLabel, /Retracted: Superseded by a later decision/);
  assert.equal(row.canReview, false);
  assert.equal(row.canRetract, false);
});

// --- timeline dependency lines -------------------------------------------------------------------

test("dependency lines are drawn only from explicit relations and stay secondary", () => {
  const lines = dependencyLines([
    { id: "m1", relation: "blocks", note: "Cannot run before the environment exists",
      action: { type: "task", id: "t1", description: "Provision the sandbox" } },
  ]);
  assert.equal(lines.length, 1);
  assert.equal(lines[0].explicit, true);
  assert.equal(lines[0].blocking, true);
  assert.equal(lines[0].emphasis, "secondary");
  assert.equal(lines[0].label, "Provision the sandbox");
});

test("no links means no lines — nothing is inferred from dates or owners", () => {
  assert.deepEqual(dependencyLines([]), []);
  assert.deepEqual(dependencyLines(null), []);
});

// --- the Next best move reason -------------------------------------------------------------------

test("Unblocks names a gate only when an explicit required relation supports it", () => {
  const reason = unblocksReason({
    gates: [{ gate_id: "g1", name: "Launch gate", necessity: "required", status: "open",
      through_requirement: "exec_engaged" }],
  });
  assert.equal(reason.text, "Unblocks Launch gate");
  assert.equal(reason.basis, "explicit_gate_requirement_link");
  assert.equal(reason.through_requirement, "exec_engaged");
});

test("an optional or already-settled gate never produces the Unblocks claim", () => {
  assert.equal(unblocksReason({
    gates: [{ gate_id: "g1", name: "Launch gate", necessity: "optional", status: "open" }],
  }), null);
  assert.equal(unblocksReason({
    gates: [{ gate_id: "g1", name: "Launch gate", necessity: "required", status: "passed" }],
  }), null);
  assert.equal(unblocksReason({ gates: [] }), null);
  assert.equal(unblocksReason(null), null);
});

test("several blocked gates are counted rather than silently reduced to one", () => {
  const reason = unblocksReason({
    gates: [
      { gate_id: "g1", name: "Launch gate", necessity: "required", status: "open" },
      { gate_id: "g2", name: "Scale gate", necessity: "required", status: "open" },
    ],
  });
  assert.equal(reason.text, "Unblocks Launch gate and 1 other gate");
});

// --- the action detail ---------------------------------------------------------------------------

test("an action shows what it advances, by kind, and never claims it settles a condition", () => {
  const rows = actionAdvances({
    requirements: [{ plan_instance_id: "pi1", label: "Executive sponsor engaged",
      relation: "advances", definition_of_done: "A dated judgment from two sources." }],
    milestones: [{ milestone_id: "m1", name: "Go-live", relation: "advances",
      target_date: "2026-09-01" }],
    gates: [{ gate_id: "g1", name: "Launch gate", necessity: "required",
      through_requirement: "exec_engaged" }],
  });
  assert.deepEqual(rows.map((r) => r.kind), ["requirement", "milestone", "gate"]);
  assert.match(rows[0].caveat, /does not set the condition's state/);
  assert.equal(rows[1].detail, "Target 2026-09-01");
  assert.match(rows[2].detail, /Through exec_engaged/);
});

test("a gate that marks the condition optional says the gate does not depend on it", () => {
  const [row] = actionAdvances({
    gates: [{ gate_id: "g1", name: "Launch gate", necessity: "optional",
      through_requirement: "exec_engaged" }],
  });
  assert.match(row.caveat, /does not depend on it/);
});

test("an action with no links returns nothing rather than a guess", () => {
  assert.deepEqual(actionAdvances({}), []);
  assert.deepEqual(actionAdvances(null), []);
});
