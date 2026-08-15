import test from "node:test";
import assert from "node:assert/strict";

import {
  COMPATIBILITY_PLAYBOOK_KEY, NEXT_HORIZON_DAYS, NOW_HORIZON_DAYS, STAGES,
  activePlanKeys, anchorRequirement, compatibilityReport, daysUntil, latestPerKey, openCount,
  planPresence, planStages, setupStageOf, stageOf, startableVersions, unmappedLegacy, upgradeOffers,
} from "./planSetup.js";

const TODAY = "2026-08-05";

function req(over = {}) {
  return { requirement_key: "exec_engaged", state: "thin", due_date: null, overdue: false, ...over };
}

/** A phase gate item as the server returns it: a tick and a date, and no readiness axis at all. */
function setup(over = {}) {
  return {
    gate_item_id: "gi-1", description: "Trace the IT / legal path", gate_status: "open",
    complete: false, due_date: null, setup: true,
    state: null, freshness: null, applicability: null, ...over,
  };
}

const LIBRARY = {
  playbooks: [
    { key: "enterprise-launch", version: 1, label: "Enterprise launch", default_scope: "program",
      default_anchor: "kickoff", allowed_anchors: ["kickoff"],
      entries: [{ necessity: "required" }, { necessity: "optional" }] },
    { key: "enterprise-launch", version: 2, label: "Enterprise launch", default_scope: "program",
      default_anchor: "kickoff", allowed_anchors: ["kickoff"],
      entries: [{ necessity: "required" }, { necessity: "required" }] },
    { key: "renewal-readiness", version: 1, label: "Renewal readiness", default_scope: "account",
      default_anchor: "renewal", allowed_anchors: ["renewal"], entries: [] },
    { key: COMPATIBILITY_PLAYBOOK_KEY, version: 1, label: "Compatibility",
      default_scope: "program", default_anchor: "kickoff", allowed_anchors: ["kickoff"],
      entries: [] },
  ],
};

test("daysUntil reads ISO dates as UTC so a timezone cannot shift a due date", () => {
  assert.equal(daysUntil("2026-08-05", TODAY), 0);
  assert.equal(daysUntil("2026-08-19", TODAY), 14);
  assert.equal(daysUntil("2026-07-29", TODAY), -7);
  assert.equal(daysUntil(null, TODAY), null);
  assert.equal(daysUntil("not-a-date", TODAY), null);
});

test("stages partition by the plan's dates, using the server's overdue flag verbatim", () => {
  assert.equal(stageOf(req({ overdue: true, due_date: "2026-07-01" }), TODAY), "overdue");
  assert.equal(stageOf(req({ due_date: "2026-08-10" }), TODAY), "now");
  assert.equal(stageOf(req({ due_date: "2026-09-10" }), TODAY), "next");
  assert.equal(stageOf(req({ due_date: "2027-01-10" }), TODAY), "later");
  assert.equal(stageOf(req({ due_date: null }), TODAY), "undated");
});

test("a past due date the server did not call overdue is never recomputed as overdue", () => {
  // met-late is the case: readiness answered it, and a second answer here could disagree.
  const row = req({ due_date: "2026-06-01", overdue: false, state: "met" });
  assert.equal(stageOf(row, TODAY), "settled");
  const thin = req({ due_date: "2026-06-01", overdue: false, state: "thin" });
  assert.notEqual(stageOf(thin, TODAY), "overdue");
});

test("settled covers met, waived, overridden, and recorded-complete rows", () => {
  assert.equal(stageOf(req({ state: "met" }), TODAY), "settled");
  assert.equal(stageOf(req({ recorded_complete: true }), TODAY), "settled");
  assert.equal(stageOf(req({ waiver: { reason: "x" } }), TODAY), "settled");
  assert.equal(stageOf(req({ applicability_override: { kind: "not_applicable" } }), TODAY),
    "settled");
});

test("settled wins over overdue, so a waived requirement is never shown as owed", () => {
  const waived = req({ overdue: true, due_date: "2026-07-01", waiver: { reason: "agreed" } });
  assert.equal(stageOf(waived, TODAY), "settled");
});

test("planStages preserves the server's order inside every stage and never re-sorts", () => {
  const payload = { requirements: [
    req({ requirement_key: "z_first", due_date: "2026-08-30" }),
    req({ requirement_key: "a_second", due_date: "2026-08-07" }),
    req({ requirement_key: "m_third", due_date: "2026-08-08" }),
  ] };
  const stages = planStages(payload, TODAY);
  const now = stages.find((s) => s.key === "now");
  assert.deepEqual(now.rows.map((r) => r.requirement_key), ["a_second", "m_third"]);
  const next = stages.find((s) => s.key === "next");
  assert.deepEqual(next.rows.map((r) => r.requirement_key), ["z_first"]);
});

test("every stage is returned even when empty, so an empty horizon can speak for itself", () => {
  const stages = planStages({ requirements: [] }, TODAY);
  assert.deepEqual(stages.map((s) => s.key), STAGES.map((s) => s.key));
  assert.ok(stages.every((s) => s.rows.length === 0));
});

test("openCount excludes settled rows and never merges the two counts", () => {
  const payload = {
    requirements: [
      req({ overdue: true, due_date: "2026-07-01" }),
      req({ due_date: "2026-08-10" }),
      req({ state: "met" }),
    ],
    setup_items: [
      setup({ due_date: "2026-07-01" }),
      setup({ due_date: "2026-08-10" }),
      setup({ due_date: "2026-07-01", complete: true }),
    ],
  };
  // Reported apart, not as one number: "4 open" would invite four ticks as the way to clear it,
  // and two of them are conditions no tick can satisfy.
  assert.deepEqual(openCount(payload, TODAY), { requirements: 2, setup: 2, total: 4 });
});

// --- setup items (the merged standard's operational half, migration 0051) --------------------

test("a setup item is settled by its own tick, not by a readiness state it does not have", () => {
  // stageOf's settled test reads `state`/`waiver`/`applicability_override`. A gate item has none of
  // them, so running it through stageOf would file a completed step under a date bucket forever.
  assert.equal(setupStageOf(setup({ complete: true, due_date: "2026-07-01" }), TODAY), "settled");
  assert.equal(setupStageOf(setup({ due_date: "2026-07-01" }), TODAY), "overdue");
});

test("a settled gate settles its items rather than arguing with the operator who settled it", () => {
  for (const status of ["passed", "waived"]) {
    assert.equal(setupStageOf(setup({ due_date: "2026-07-01", gate_status: status }), TODAY),
      "settled");
  }
});

test("setup overdue is computed from the date, because no server flag claims it", () => {
  // The requirement rows read `overdue` from the server verbatim; a gate item carries no such
  // field. Computing it here is honest only because it is arithmetic — past its date and not
  // ticked — and not a judgment about evidence.
  assert.equal(setupStageOf(setup({ due_date: "2026-08-04" }), TODAY), "overdue");
  assert.equal(setupStageOf(setup({ due_date: "2026-08-05" }), TODAY), "now");
  assert.equal(setupStageOf(setup({ due_date: "2026-09-10" }), TODAY), "next");
  assert.equal(setupStageOf(setup({ due_date: "2026-12-01" }), TODAY), "later");
  assert.equal(setupStageOf(setup({ due_date: null }), TODAY), "undated");
});

test("setup items ride the same horizons in a separate list, never concatenated", () => {
  const stages = planStages({
    requirements: [req({ due_date: "2026-08-10" })],
    setup_items: [setup({ due_date: "2026-08-10" })],
  }, TODAY);
  const now = stages.find((s) => s.key === "now");
  assert.equal(now.rows.length, 1);
  assert.equal(now.setup.length, 1);
  // The two kinds answer different questions, so one array would force one status vocabulary.
  assert.ok(!now.rows.some((r) => r.setup));
});

test("a setup item carries no readiness axis and none is synthesised for it", () => {
  const stages = planStages({ requirements: [], setup_items: [setup({ due_date: "2026-07-01" })] },
    TODAY);
  const row = stages.find((s) => s.key === "overdue").setup[0];
  assert.equal(row.state, null);
  assert.equal(row.freshness, null);
  assert.equal(row.applicability, null);
});

test("planPresence names the absence rather than rendering an empty panel", () => {
  const none = planPresence({ plans: [], requirements: [] });
  assert.equal(none.started, false);
  assert.match(none.reason, /No playbook has been instantiated/);

  const compatOnly = planPresence({
    plans: [], requirements: [req({ compatibility_source: { type: "checklist_item", id: "c1" } })],
  });
  assert.equal(compatOnly.started, false);
  assert.match(compatOnly.reason, /checklist compatibility/);

  const started = planPresence({ plans: [{ id: "p1", status: "active" }], requirements: [req()] });
  assert.equal(started.started, true);
  assert.equal(started.requirementCount, 1);
});

test("a superseded plan does not count as started", () => {
  assert.equal(planPresence({ plans: [{ id: "p1", status: "superseded" }] }).started, false);
});

test("the compatibility playbook is never offered as a starting choice", () => {
  const keys = startableVersions(LIBRARY, { hasProgram: true }).map((v) => v.key);
  assert.ok(!keys.includes(COMPATIBILITY_PLAYBOOK_KEY));
});

test("the picker only offers versions whose scope matches the selection", () => {
  const withProgram = startableVersions(LIBRARY, { hasProgram: true });
  assert.deepEqual([...new Set(withProgram.map((v) => v.key))], ["enterprise-launch"]);

  const accountOnly = startableVersions(LIBRARY, { hasProgram: false });
  assert.deepEqual([...new Set(accountOnly.map((v) => v.key))], ["renewal-readiness"]);
});

test("a playbook key already active here is not startable again", () => {
  const offered = startableVersions(LIBRARY,
    { hasProgram: true, activeKeys: ["enterprise-launch"] });
  assert.deepEqual(offered, []);
});

test("startable versions carry the entry counts an operator commits to", () => {
  const v2 = startableVersions(LIBRARY, { hasProgram: true }).find((v) => v.version === 2);
  assert.equal(v2.entryCount, 2);
  assert.equal(v2.requiredCount, 2);
  assert.deepEqual(v2.allowedAnchors, ["kickoff"]);
});

test("a kickoff anchor may be left blank only when the program records a kickoff date", () => {
  const opt = { defaultAnchor: "kickoff" };
  const withDate = anchorRequirement(opt, "2026-05-20");
  assert.equal(withDate.required, false);
  assert.match(withDate.hint, /2026-05-20/);

  // The case that produced a dead Start button: no kickoff on the program, so no fallback exists.
  const without = anchorRequirement(opt, null);
  assert.equal(without.required, true);
  assert.match(without.hint, /no kickoff date recorded/);
});

test("a non-kickoff anchor always needs a date, because the server has no fallback", () => {
  const req = anchorRequirement({ defaultAnchor: "renewal" }, "2026-05-20");
  assert.equal(req.required, true);
  assert.equal(req.label, "renewal date");
});

test("latestPerKey picks the highest version of each key", () => {
  const latest = latestPerKey(startableVersions(LIBRARY, { hasProgram: true }));
  assert.equal(latest.length, 1);
  assert.equal(latest[0].version, 2);
});

test("an upgrade offer reports a fact and carries no applied action", () => {
  const payload = { plans: [
    { id: "pl-1", status: "active", playbook_key: "enterprise-launch", playbook_version: 1 },
  ] };
  const [offer] = upgradeOffers(payload, LIBRARY);
  assert.equal(offer.fromVersion, 1);
  assert.equal(offer.toVersion, 2);
  assert.ok(!("applied" in offer));
  assert.match(offer.text, /v2 is published/);
});

test("an offer carries the plan's own scope, not the scope currently selected", () => {
  // At "All programs" the plan list still returns program-scoped plans. Previewing with the
  // selection instead of the plan's own program asks the server to upgrade a plan that does not
  // exist, and the panel sits on a diff that never arrives.
  const payload = { plans: [
    { id: "pl-1", status: "active", playbook_key: "enterprise-launch", playbook_version: 1,
      program_id: "prog-eu" },
  ] };
  assert.equal(upgradeOffers(payload, LIBRARY)[0].programId, "prog-eu");

  const accountScoped = { plans: [
    { id: "pl-2", status: "active", playbook_key: "enterprise-launch", playbook_version: 1,
      program_id: null },
  ] };
  assert.equal(upgradeOffers(accountScoped, LIBRARY)[0].programId, null);
});

test("a plan already on the highest version offers nothing", () => {
  const payload = { plans: [
    { id: "pl-1", status: "active", playbook_key: "enterprise-launch", playbook_version: 2 },
  ] };
  assert.deepEqual(upgradeOffers(payload, LIBRARY), []);
});

test("unmappedLegacy reports the items no requirement covers, open ones separately", () => {
  // The server has already dropped every mapped item, so each of these is part of the seam.
  const payload = { legacy_items: [
    { checklist_item_id: "c1", label: "Map the talent calendar", status: "open",
      state: null, freshness: null, applicability: null },
    { checklist_item_id: "c2", label: "Comms plan drafted", status: "done",
      state: null, freshness: null, applicability: null },
    { checklist_item_id: "c3", label: "Trace the IT / legal path", status: "open",
      state: null, freshness: null, applicability: null },
  ] };
  const out = unmappedLegacy(payload);
  assert.equal(out.total, 3);
  assert.equal(out.openCount, 2);
  assert.deepEqual(out.open.map((i) => i.checklist_item_id), ["c1", "c3"]);
});

test("legacy items keep their null axes — nothing synthesises a state for them", () => {
  const payload = { legacy_items: [
    { checklist_item_id: "c1", label: "Map the talent calendar", status: "done",
      state: null, freshness: null, applicability: null },
  ] };
  const [item] = unmappedLegacy(payload).items;
  assert.equal(item.state, null);
  assert.equal(item.freshness, null);
  assert.equal(item.applicability, null);
});

test("the compatibility report reads the same for a dry run and a run", () => {
  const counts = { checklist_items: 8, mapped: 3, unmatched: 2, ambiguous: 0 };
  const dry = compatibilityReport({ dry_run: true, counts });
  assert.match(dry.headline, /Would map 3 checklist items of 8 across the account/);
  assert.match(dry.notes[0].text, /2 items would be left as they are/);

  const real = compatibilityReport({ dry_run: false, counts });
  assert.match(real.headline, /Mapped 3 checklist items of 8 across the account/);
  assert.match(real.notes[0].text, /2 items were left as they are/);
  assert.equal(dry.notes.length, real.notes.length);
});

test("an ambiguous mapping is reported as unresolved, never resolved by guess", () => {
  const out = compatibilityReport({
    dry_run: false, counts: { checklist_items: 4, mapped: 2, unmatched: 0, ambiguous: 2 },
  });
  assert.equal(out.notes.length, 1);
  assert.equal(out.notes[0].key, "ambiguous");
  assert.match(out.notes[0].text, /left unmapped rather than resolved by guess/);
});

test("a carried tick readiness does not agree with is named, not hidden (§13.5.7)", () => {
  const out = compatibilityReport({
    dry_run: false,
    counts: { checklist_items: 5, mapped: 5, unmatched: 0, ambiguous: 0 },
    evidence_missing: [{ requirement_key: "value_baseline_locked" }],
  });
  assert.equal(out.complete, false);
  const note = out.notes.find((x) => x.key === "evidence_missing");
  assert.match(note.text, /is not treated as evidence/);
});

test("a clean report carries no qualifying notes", () => {
  const out = compatibilityReport({
    dry_run: false, counts: { checklist_items: 3, mapped: 3, unmatched: 0, ambiguous: 0 },
  });
  assert.equal(out.complete, true);
  assert.deepEqual(out.notes, []);
  assert.equal(out.headline,
    "Mapped 3 checklist items of 3 across the account onto plan requirements.");
  assert.equal(compatibilityReport(null), null);
});

test("the horizons are presentation constants, not thresholds any rule depends on", () => {
  assert.ok(NOW_HORIZON_DAYS < NEXT_HORIZON_DAYS);
  assert.equal(stageOf(req({ due_date: "2026-08-19" }), TODAY), "now");   // exactly NOW_HORIZON
  assert.equal(stageOf(req({ due_date: "2026-08-20" }), TODAY), "next");
});

// --- review pass -------------------------------------------------------------------------------

test("a condition readiness says does not apply is not filed as overdue work", () => {
  // The pillar-level reading carries no `applicability_override` — only an operator-recorded
  // exception does — so testing the override alone left this row under "past the date and not yet
  // evidenced", which is a claim about a condition that is not owed here at all.
  const evaluatorNA = req({
    due_date: "2026-06-01", overdue: true, state: "not_applicable",
    applicability: "not_applicable", applicability_override: null, waiver: null,
  });
  assert.equal(stageOf(evaluatorNA, TODAY), "settled");
  assert.equal(openCount({ requirements: [evaluatorNA] }, TODAY).requirements, 0);
});

test("not_due keeps its overdue placement, because two axes disagreeing is worth seeing", () => {
  const notDue = req({ due_date: "2026-06-01", overdue: true, state: "thin",
                       applicability: "not_due" });
  assert.equal(stageOf(notDue, TODAY), "overdue");
});

test("activePlanKeys is scope-exact, so an account plan never hides a program playbook", () => {
  const payload = { plans: [
    { playbook_key: "renewal-readiness", status: "active", program_id: null },
    { playbook_key: "enterprise-launch", status: "active", program_id: "pg-1" },
    { playbook_key: "enterprise-launch", status: "superseded", program_id: "pg-2" },
  ] };
  assert.deepEqual(activePlanKeys(payload, "pg-1"), ["enterprise-launch"]);
  assert.deepEqual(activePlanKeys(payload, "pg-2"), []);
  assert.deepEqual(activePlanKeys(payload, null), ["renewal-readiness"]);
});

test("a program whose account already has a plan can still start its own", () => {
  // The regression this guards: `list_plans` returns the account-wide plan inside the program
  // scope, so deriving the picker's active keys from the whole payload offered nothing and — with
  // the picker gated on presence — the write had no route at all.
  const payload = { plans: [{ playbook_key: "renewal-readiness", status: "active",
                              program_id: null }] };
  const offered = startableVersions(LIBRARY, {
    hasProgram: true, activeKeys: activePlanKeys(payload, "pg-1"),
  });
  assert.deepEqual([...new Set(offered.map((v) => v.key))], ["enterprise-launch"]);
});

test("planPresence reports the requirement count it can see, started or not", () => {
  const compat = planPresence({ plans: [], requirements: [req({ compatibility_source: { id: "c1" } })] });
  assert.equal(compat.requirementCount, 1);
  assert.match(compat.reason, /checklist compatibility/);
});

test("planless requirements are not attributed to a migration that did not produce them", () => {
  const out = planPresence({ plans: [], requirements: [req({ compatibility_source: null })] });
  assert.doesNotMatch(out.reason, /compatibility/);
  assert.match(out.reason, /no active plan in this scope states when they are due/);
});

test("an orphaned migrated instance is reported as itself, not as an unmatched item", () => {
  const out = compatibilityReport({
    dry_run: false,
    counts: { checklist_items: 3, mapped: 3, unmatched: 0, ambiguous: 0, orphaned: 2 },
  });
  assert.equal(out.complete, false);
  const note = out.notes.find((x) => x.key === "orphaned");
  assert.match(note.text, /no longer have the checklist items they came from/);
  assert.match(compatibilityReport({
    dry_run: false, counts: { checklist_items: 1, mapped: 1, orphaned: 1 },
  }).notes[0].text, /no longer has the checklist item it came from/);
  // The wrong reason it used to borrow: these carry no template key to match.
  assert.doesNotMatch(note.text, /template key/);
  assert.equal(out.notes.some((x) => x.key === "unmatched"), false);
});
