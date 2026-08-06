import test from "node:test";
import assert from "node:assert/strict";

import {
  ESSENTIALS_GAP_CAP,
  controlsWriteNoState, dueRuleText, essentialsGaps, evaluatorConfigSentence,
  exceptionHistoryRows, linkedRecords,
  EXCEPTION_STATUS_LABEL,
  planStatus, planVariance, recordedCompleteNote, requirementAxes, requirementControls,
  suppressedRequirements, trackedRequirements,
} from "./requirementDetail.js";

const TODAY = "2026-08-04";

const ROW = {
  requirement_key: "exec_engaged",
  label: "Executive sponsor engaged",
  state: "thin",
  freshness: "stale",
  applicability: "required",
  due_date: "2026-07-15",
  overdue: true,
  due_rule: { anchor: "kickoff", offset_days: 14 },
  playbook: { key: "enterprise-launch", label: "Enterprise launch", version: 1 },
};

test("the four axes stay four readings and are never combined", () => {
  const axes = requirementAxes(ROW, { status: "partial" });
  assert.deepEqual(axes.map((a) => a.axis),
    ["state", "freshness", "coverage", "applicability"]);
  assert.deepEqual(axes.map((a) => a.label),
    ["Thin", "Stale", "Partial", "Required now"]);
  // Each carries its own word as well as its own mark, so none is conveyed by colour alone, and
  // a stale reading cannot be hidden behind a met one.
  for (const axis of axes) {
    assert.ok(axis.label.length > 0, `${axis.axis} has no word`);
    assert.ok(axis.mark.length > 0, `${axis.axis} has no shape class`);
  }
  const met = requirementAxes({ ...ROW, state: "met" }, { status: "complete" });
  assert.equal(met[0].label, "Met");
  assert.equal(met[1].label, "Stale", "freshness must survive a met state");
});

test("an unreported coverage reading says so instead of borrowing the state", () => {
  const axes = requirementAxes(ROW, null);
  const coverage = axes.find((a) => a.axis === "coverage");
  assert.equal(coverage.label, "Not reported");
  assert.equal(coverage.recognized, false);
});

test("an enum this build does not know reads as unknown, not as the benign end", () => {
  const axes = requirementAxes({ state: "provisionally_met", applicability: "deferred" });
  assert.equal(axes[0].label, "Not evaluated");
  assert.equal(axes[0].recognized, false);
  assert.equal(axes[0].mark, "unknown");
  assert.equal(axes[3].label, "Not determined");
});

test("the plan status speaks only for the plan", () => {
  const overdue = planStatus(ROW, TODAY);
  assert.equal(overdue.tone, "risk");
  assert.match(overdue.text, /past its planned date/);
  // The same date on a met requirement is a timing fact, not an outstanding item.
  const late = planStatus({ ...ROW, state: "met", overdue: false }, TODAY);
  assert.equal(late.tone, "neutral");
  assert.match(late.text, /evidenced after its planned date/);
  // An unscheduled requirement says it is unscheduled rather than showing a blank date.
  const unscheduled = planStatus({ ...ROW, playbook: null }, TODAY);
  assert.equal(unscheduled.scheduled, false);
  assert.match(unscheduled.text, /Not scheduled/);
});

test("the compact due reading names itself rather than relying on its colour", () => {
  // The row renders `due_label` beside a red mark. A bare date there would leave the reader to
  // infer from colour alone what kind of date it is, which DESIGN-GUIDE.md forbids.
  assert.equal(planStatus(ROW, TODAY).due_label, "Overdue · due 2026-07-15");
  assert.equal(planStatus({ ...ROW, overdue: false }, TODAY).due_label, "Due 2026-07-15");
  // Nothing scheduled means nothing to label, so the row omits the chip entirely.
  assert.equal(planStatus({ ...ROW, playbook: null }, TODAY).due_label, undefined);
  assert.equal(planStatus({ ...ROW, due_date: null }, TODAY).due_label, undefined);
});

test("the relative rule is readable in both directions and at zero", () => {
  assert.equal(dueRuleText(ROW), "14 days after the kickoff date");
  assert.equal(dueRuleText({ due_rule: { anchor: "renewal", offset_days: -90 } }),
    "90 days before the renewal date");
  assert.equal(dueRuleText({ due_rule: { anchor: "kickoff", offset_days: 0 } }),
    "On the kickoff date");
  assert.equal(dueRuleText({ due_rule: { anchor: "kickoff", offset_days: null } }), null);
  assert.equal(dueRuleText({}), null);
});

test("Account essentials caps current-phase gaps at three and reports the rest", () => {
  const gaps = Array.from({ length: 5 }, (_, i) => ({ requirement_key: `k${i}` }));
  const { shown, remaining } = essentialsGaps({ current_phase_gaps: gaps });
  assert.equal(ESSENTIALS_GAP_CAP, 3);
  assert.equal(shown.length, 3);
  assert.equal(remaining, 2);
  // Server order is preserved exactly: the client does not re-rank (§10.5).
  assert.deepEqual(shown.map((g) => g.requirement_key), ["k0", "k1", "k2"]);
  // Lifting the cap reveals the same list in the same order and reports nothing left over, so the
  // card's "View all N" expands rather than routing somewhere the requirements are not listed.
  const all = essentialsGaps({ current_phase_gaps: gaps }, Number.MAX_SAFE_INTEGER);
  assert.equal(all.remaining, 0);
  assert.deepEqual(all.shown.map((g) => g.requirement_key), ["k0", "k1", "k2", "k3", "k4"]);
  // The label the card prints is the total either way, so expanding never changes the count.
  assert.equal(shown.length + remaining, all.shown.length + all.remaining);
});

test("suppressed requirements stay reachable behind their own count", () => {
  const payload = {
    current_phase_gaps: [{ id: "g", requirement_key: "open" }],
    requirements: [
      { id: "g", requirement_key: "open" },
      { id: "w", requirement_key: "waived", waiver: { kind: "waiver", exception_id: "x1" } },
      { id: "n", requirement_key: "na", applicability_override: { kind: "not_applicable" } },
    ],
  };
  const suppressed = suppressedRequirements(payload);
  // Server order, and only the rows a decision is actually silencing.
  assert.deepEqual(suppressed.map((r) => r.id), ["w", "n"]);
  // They are not gaps — being reachable must not turn a suppressed condition back into a chore.
  assert.deepEqual(essentialsGaps(payload).shown.map((r) => r.id), ["g"]);
  assert.deepEqual(suppressedRequirements({ requirements: [] }), []);
  assert.deepEqual(suppressedRequirements(null), []);
});

test("linking an action moves a condition out of the gaps but not out of reach", () => {
  const link = { type: "task", id: "tk-1", relation: "advances" };
  const payload = {
    // The server drops a linked condition from the gap list (§13.6): the work is the Task's.
    current_phase_gaps: [{ id: "g", requirement_key: "open", applicability: "required",
      state: "thin" }],
    requirements: [
      { id: "g", requirement_key: "open", applicability: "required", state: "thin" },
      { id: "t", requirement_key: "tracked", applicability: "required", state: "thin",
        linked_action: link },
      // Settled, silenced, or not required: none of these is something to route back to.
      { id: "m", requirement_key: "met", applicability: "required", state: "met",
        linked_action: link },
      { id: "o", requirement_key: "optional", applicability: "optional", state: "thin",
        linked_action: link },
      { id: "w", requirement_key: "waived", applicability: "required", state: "thin",
        linked_action: link, waiver: { kind: "waiver", exception_id: "x1" } },
    ],
  };
  assert.deepEqual(trackedRequirements(payload).map((r) => r.id), ["t"]);
  // Reachable, but still not a chore: the gap list is unchanged by the disclosure.
  assert.deepEqual(essentialsGaps(payload).shown.map((r) => r.id), ["g"]);
  assert.deepEqual(trackedRequirements({ requirements: [] }), []);
  assert.deepEqual(trackedRequirements(null), []);
});

test("a legacy tick is labelled a planning record, not evidence", () => {
  const note = recordedCompleteNote({
    recorded_complete: true, recorded_complete_on: "2026-07-02", state: "unknown",
    compatibility_source: { label: "Baselines captured" },
  });
  assert.match(note.text, /legacy checklist/);
  assert.match(note.caveat, /not evidence/);
  assert.equal(note.tone, "warn");
  // When readiness does evidence it, the caveat stops implying a contradiction.
  const met = recordedCompleteNote({ recorded_complete: true, state: "met" });
  assert.match(met.caveat, /independently evidences/);
  assert.equal(recordedCompleteNote({ recorded_complete: false }), null);
});

test("no control in the panel can write a readiness state", () => {
  // §13.7's closing paragraph. Asserted as data rather than left to review, because a status
  // dropdown is exactly the control somebody adds for convenience.
  for (const row of [ROW, { ...ROW, waiver: { kind: "waiver" } },
    { ...ROW, applicability_override: { reason: "Out of scope." } },
    { ...ROW, create_action_prefill: { link_note: "…" } }]) {
    assert.ok(controlsWriteNoState(row));
    for (const control of requirementControls(row)) {
      assert.ok(["navigate", "create", "governed"].includes(control.kind));
      assert.ok(["native_record", "exception"].includes(control.writes));
      assert.ok(control.hint.length > 0, `${control.key} offers no explanation`);
    }
  }
});

test("a live decision offers a revocation instead of a second suppression", () => {
  const clean = requirementControls(ROW).map((c) => c.key);
  assert.ok(clean.includes("mark_not_applicable"));
  const waived = requirementControls({ ...ROW, waiver: { kind: "waiver" } }).map((c) => c.key);
  assert.ok(waived.includes("revoke_waiver") === false);
  assert.ok(waived.includes("revoke_exception"));
  assert.ok(!waived.includes("mark_not_applicable"));
});

test("Create action appears only with a supported suggestion and never claims a link", () => {
  assert.ok(!requirementControls(ROW).some((c) => c.key === "create_action"));
  const withSuggestion = requirementControls({
    ...ROW, create_action_prefill: { linked: false, link_note: "The durable link lands in Slice 5." },
  });
  const create = withSuggestion.find((c) => c.key === "create_action");
  assert.equal(create.writes, "native_record");
  assert.match(create.hint, /Slice 5/);
});

test("exception history keeps revoked and lapsed decisions readable", () => {
  // The statuses are exactly what `playbooks._exception_status` emits. An earlier version of this
  // test invented `active`/`expired`, which passed while the panel failed to recognise a live
  // waiver and dropped its revoke control — so the vocabulary is pinned here deliberately.
  const rows = exceptionHistoryRows([
    { id: "a", kind: "not_applicable", status: "revoked", decided_on: "2026-06-01" },
    { id: "b", kind: "waiver", status: "live", decided_on: "2026-07-01" },
    { id: "c", kind: "waiver", status: "lapsed", decided_on: "2026-05-01" },
  ]);
  assert.deepEqual(rows.map((r) => r.id), ["b", "a", "c"]);
  assert.deepEqual(rows.map((r) => r.statusLabel), ["In force", "Revoked", "Lapsed"]);
  assert.deepEqual(rows.map((r) => r.live), [true, false, false]);
  assert.deepEqual(rows.map((r) => r.kindLabel), ["Waiver", "Not applicable", "Waiver"]);
  // A status this build does not know is never live: a drift loses the revoke control rather than
  // suppressing a requirement the operator can no longer see or undo.
  const drift = exceptionHistoryRows([{ id: "d", kind: "waiver", status: "suspended" }]);
  assert.equal(drift[0].live, false);
  assert.equal(drift[0].statusLabel, "Status not recognized");
});

test("the server's exception statuses are all labelled", async () => {
  // Guards the pairing directly: every status the Python emits has a label here.
  const { readFile } = await import("node:fs/promises");
  const src = await readFile(new URL("../../backend/app/playbooks.py", import.meta.url), "utf8");
  const body = src.slice(src.indexOf("def _exception_status"));
  const emitted = [...body.slice(0, body.indexOf("\n\n\n")).matchAll(/return "(\w+)"/g)]
    .map((m) => m[1]);
  assert.ok(emitted.length >= 3, `expected the status branches, saw ${emitted.join(",")}`);
  for (const status of emitted) {
    assert.ok(EXCEPTION_STATUS_LABEL[status], `no label for server status "${status}"`);
  }
});

test("linked records are listed only when a link actually exists", () => {
  assert.deepEqual(linkedRecords(ROW), []);
  const linked = linkedRecords({ ...ROW, linked_action: { record_type: "task", id: "t1" } });
  assert.equal(linked[0].kindLabel, "task");
});

test("a linked record reads the shape the server actually ships", () => {
  // `{type, id, description}` — the §13.6 dedupe index entry, with no `native_target` of its own.
  const [link] = linkedRecords({
    ...ROW,
    linked_action: { type: "commitment", id: "cm-1", relation: "advances",
      description: "Deliver the nomination list." },
  });
  assert.equal(link.kindLabel, "commitment");
  assert.equal(link.label, "Deliver the nomination list.");
  assert.deepEqual(link.native_target,
    { tab: "ledger", record_type: "commitment", record_id: "cm-1" });
  // An unroutable kind yields no target, so the caller renders text instead of a dead button.
  const [odd] = linkedRecords({ ...ROW, linked_action: { type: "sighting", id: "s1" } });
  assert.equal(odd.native_target, null);
  assert.equal(odd.label, "s1");
});

// --- evaluator configuration (VISIBILITY-SPEC §7.2) ---------------------------------------------

test("the configuration sentence names the evaluator and lists what it was given", () => {
  const config = evaluatorConfigSentence({
    evaluator_key: "named_roles_present", evaluator_version: 2,
    evaluator_config: { min_count: 2, roles: ["champion", "exec_sponsor"], require_assessment: true },
  });
  assert.equal(config.lead, "named_roles_present v2");
  assert.deepEqual(config.operands, [
    { key: "min_count", label: "min count", value: "2" },
    { key: "roles", label: "roles", value: "champion, exec_sponsor" },
    { key: "require_assessment", label: "require assessment", value: "true" },
  ]);
});

test("an unallowlisted evaluator still reports what was configured", () => {
  // This is the case §7.2 exists for. Nothing ran, the pillar degrades to `coverage: partial`,
  // and until now the screen said only that a state was unknown. The configuration is an input,
  // so it survives the evaluator's absence and can be read while the reading cannot.
  const config = evaluatorConfigSentence({
    evaluator_key: "not_in_the_registry", evaluator_version: 9,
    evaluator_config: { touch_window_days: 60 },
    state: "unknown",
  });
  assert.equal(config.lead, "not_in_the_registry v9");
  assert.deepEqual(config.operands, [{ key: "touch_window_days", label: "touch window days", value: "60" }]);
});

test("the sentence describes the configuration and never the evaluator", () => {
  // A per-evaluator gloss would be a second statement of what the code does, authored in the
  // view and free to drift from it — and wrong outright when no evaluator ran. So there is no
  // lookup table of English descriptions here, and the operands are the raw configured values.
  const config = evaluatorConfigSentence({
    evaluator_key: "min_contacts_in_window", evaluator_version: 1,
    evaluator_config: { min_contacts: 3 },
  });
  assert.equal(config.operands[0].value, "3");
  assert.equal(/check|look|ensur|verif|pass|fail/i.test(JSON.stringify(config)), false);
});

test("configured values are rendered, not summarised or judged", () => {
  const config = evaluatorConfigSentence({
    evaluator_key: "e", evaluator_version: 1,
    evaluator_config: {
      empty_list: [], nothing: null, off: false, zero: 0, nested: { a: 1 }, text: "kickoff",
    },
  });
  assert.deepEqual(config.operands.map((o) => o.value),
    ["none", "none", "false", "0", '{"a":1}', "kickoff"]);
  // No state word anywhere in the output: a configuration is an input to a reading, never one.
  for (const key of Object.keys(config.operands[0])) {
    assert.equal(["state", "freshness", "coverage", "applicability", "met"].includes(key), false);
  }
});

test("no evaluator key means no sentence, and no operands means an honest empty one", () => {
  assert.equal(evaluatorConfigSentence({ evaluator_config: { min_count: 1 } }), null);
  assert.equal(evaluatorConfigSentence({}), null);
  assert.equal(evaluatorConfigSentence(null), null);
  // Configured with nothing is a fact worth stating; it is not the same as no evaluator.
  assert.deepEqual(evaluatorConfigSentence({ evaluator_key: "e", evaluator_version: 1 }),
    { lead: "e v1", operands: [] });
  assert.deepEqual(evaluatorConfigSentence({ evaluator_key: "e", evaluator_version: 1, evaluator_config: [] }),
    { lead: "e v1", operands: [] });
});

test("a missing version is omitted rather than guessed at v1", () => {
  assert.equal(evaluatorConfigSentence({ evaluator_key: "e" }).lead, "e");
});

// --- plan variance (VISIBILITY-SPEC §6) ---------------------------------------------------------

test("two planning dates are differenced, and the difference reads as a planning fact", () => {
  const v = planVariance({ due_date: "2026-06-09", recorded_complete_on: "2026-06-22" }, TODAY);
  assert.equal(v.kind, "delta");
  assert.equal(v.days, 13);
  assert.equal(v.text, "Recorded complete 13 days after the planned date.");
  // Early is the same kind of fact as late, and says so in the same shape.
  assert.equal(planVariance({ due_date: "2026-06-09", recorded_complete_on: "2026-06-08" }).text,
    "Recorded complete 1 day before the planned date.");
  assert.equal(planVariance({ due_date: "2026-06-09", recorded_complete_on: "2026-06-09" }).text,
    "Recorded complete on the planned date.");
});

test("a row with no recorded completion produces no delta, whatever the readiness state says", () => {
  for (const state of ["met", "thin", "unknown", "conflicted", "not_applicable", undefined]) {
    const v = planVariance({ due_date: "2026-06-09", state, assessed_through: "2026-06-22" }, TODAY);
    assert.equal(v.kind, "separate", state);
    assert.equal(v.days, null, state);
    // The subtraction the spec refuses: `assessed_through` is not a completion date, so the one
    // pair of dates that would produce "13 days late" here is never formed.
    assert.equal(/\bdays? (after|before|late)\b/.test(v.text), false, state);
  }
});

test("assessed_through is never read, under any label", () => {
  const v = planVariance({ due_date: "2026-06-09", assessed_through: "2026-06-22" }, TODAY);
  assert.equal(v.recorded, null);
  assert.equal(JSON.stringify(v).includes("2026-06-22"), false);
});

test("the planned date is stated with its age and nothing composed onto it", () => {
  assert.equal(planVariance({ due_date: "2026-06-09" }, "2026-07-20").text,
    "Planned for 2026-06-09, 41 days ago");
  assert.equal(planVariance({ due_date: "2026-08-06" }, "2026-08-04").text,
    "Planned for 2026-08-06, in 2 days");
  assert.equal(planVariance({ due_date: TODAY }, TODAY).text, `Planned for ${TODAY}, today`);
  // Without a reference date the age is unknown, so it is omitted rather than assumed.
  assert.equal(planVariance({ due_date: "2026-06-09" }).text, "Planned for 2026-06-09");
  // The age alone, for a surface that already names the date. Same arithmetic, no second date.
  assert.equal(planVariance({ due_date: "2026-06-09" }, "2026-07-20").age_text, "41 days ago");
  assert.equal(planVariance({ due_date: "2026-06-09" }, "2026-07-20").age, 41);
  assert.equal(planVariance({ due_date: "2026-06-09", recorded_complete_on: "2026-06-22" },
    "2026-07-20").age_text, null);
});

test("an unresolved anchor yields the unknown treatment, not a relative phrase", () => {
  const v = planVariance({ due_rule: { anchor: "kickoff", offset_days: 2 } }, TODAY);
  assert.equal(v.kind, "unknown");
  assert.equal(v.planned, null);
  assert.equal(v.text, "No planned date: the kickoff date it is measured from is not set.");
  // The failure this exists to prevent: an offset promising a time nobody can compute.
  assert.equal(/\d/.test(v.text), false);
});

test("a delta carries no tone, because late is not a status", () => {
  const v = planVariance({ due_date: "2026-06-09", recorded_complete_on: "2026-07-20" }, TODAY);
  assert.deepEqual(Object.keys(v).sort(),
    ["age", "age_text", "days", "kind", "planned", "recorded", "text"]);
  for (const banned of ["tone", "severity", "status", "state", "risk", "variance_pct"]) {
    assert.equal(banned in v, false, banned);
  }
});

test("an unscheduled row with no date states nothing rather than inventing one", () => {
  const v = planVariance({ state: "thin" }, TODAY);
  assert.equal(v.kind, "separate");
  assert.equal(v.text, null);
  assert.equal(v.planned, null);
  assert.deepEqual(planVariance(null), {
    kind: "separate", planned: null, recorded: null, days: null,
    age: null, age_text: null, text: null,
  });
});

test("an unparseable date degrades rather than producing NaN days", () => {
  const v = planVariance({ due_date: "soon", recorded_complete_on: "2026-06-22" }, TODAY);
  assert.equal(v.kind, "separate");
  assert.equal(v.days, null);
  assert.equal(v.text, "Planned for soon");
});
