import test from "node:test";
import assert from "node:assert/strict";

import {
  isEmptyPlan, manifestSummary, previewVerdict, stampLine, staleSourceNote, statusChip,
  unsharedSummary, withheldSentence, withheldSummary,
} from "./sharedPlan.js";

const ARTIFACT = {
  account_name: "Northwind Systems",
  stamp: { data_current_through: "2026-08-04", missing_or_stale_sources: [] },
  summary: { programs: 1, shared_items: 3, milestones_shared: 2, milestones_complete: 1,
    next_milestone: { name: "Europe go-live", target_date: "2026-09-15", program: "Europe Deployment" } },
  programs: [{ program_id: "pr1", name: "Europe Deployment", groups: [], requirements: [] }],
  account_requirements: [],
  growth_lines: [],
  pre_agreed_triggers: [],
};

// --- status words --------------------------------------------------------------------------------

test("each of the five client statuses carries a shape as well as a word", () => {
  for (const status of ["complete", "in_progress", "blocked", "not_started", "not_applicable"]) {
    const chip = statusChip(status);
    assert.ok(chip.label && chip.mark && chip.symbol, status);
  }
  // No two statuses share a mark-and-symbol pair, so removing colour removes nothing.
  const pairs = ["complete", "in_progress", "blocked", "not_started", "not_applicable"]
    .map((s) => `${statusChip(s).mark}/${statusChip(s).symbol}`);
  assert.equal(new Set(pairs).size, pairs.length);
});

test("an unrecognized status is shown as unknown rather than mapped onto a neighbour", () => {
  const chip = statusChip("nearly_done");
  assert.equal(chip.mark, "unknown");
  assert.equal(chip.label, "nearly_done");
});

// --- the stamp -----------------------------------------------------------------------------------

test("the stamp line carries currency, volume, and what is next", () => {
  const line = stampLine(ARTIFACT);
  assert.match(line, /Current through 2026-08-04/);
  assert.match(line, /3 shared items/);
  assert.match(line, /1 of 2 milestones complete/);
  assert.match(line, /Next: Europe go-live \(2026-09-15\)/);
});

test("the next milestone is the projected object, so a bare string is not printed as one", () => {
  // Guards the shape mismatch directly: `next_milestone` is a record, and interpolating it whole
  // would put "[object Object]" in front of the operator.
  assert.doesNotMatch(stampLine(ARTIFACT), /\[object Object\]/);
  assert.doesNotMatch(stampLine({ summary: { next_milestone: {} } }), /Next:/);
});

test("one shared item is not pluralized", () => {
  assert.match(stampLine({ summary: { shared_items: 1 } }), /1 shared item(?!s)/);
});

test("a missing or stale source is stated on the plan rather than silently dropped", () => {
  assert.equal(staleSourceNote(ARTIFACT), null);
  const note = staleSourceNote({ stamp: { missing_or_stale_sources: ["Joint plan notes"] } });
  assert.match(note, /1 source behind this plan is missing or past its freshness window/);
  assert.match(note, /Joint plan notes/);
});

// --- empty vs unshared ---------------------------------------------------------------------------

test("an empty plan is empty across every block, not just the programs", () => {
  assert.equal(isEmptyPlan({ programs: [], account_requirements: [], growth_lines: [],
    pre_agreed_triggers: [] }), true);
  assert.equal(isEmptyPlan(ARTIFACT), false);
  assert.equal(isEmptyPlan({ programs: [], growth_lines: [{ id: "g1" }] }), false);
});

test("unshared work is counted so an empty plan differs from a forgotten one", () => {
  assert.equal(unsharedSummary({ unshared_counts: {} }), null);
  assert.equal(
    unsharedSummary({ unshared_counts: { milestones: 1, commitments: 2, tasks: 0 } }),
    "1 milestone and 2 commitments not on this plan.",
  );
});

// --- withholding ---------------------------------------------------------------------------------

test("withheld items are grouped by the server's reason, verbatim", () => {
  const groups = withheldSummary({ withheld: [
    { kind: "requirement", id: "i1", label: "Exec sponsor confirmed", reason: "no readiness reading" },
    { kind: "requirement", id: "i2", label: "Value agreed", reason: "no readiness reading" },
    { kind: "requirement", id: "i3", label: "Budget owner named", reason: "carries a waiver" },
  ] });
  assert.equal(groups.length, 2);
  assert.equal(groups[0].reason, "no readiness reading");
  assert.equal(groups[0].items.length, 2);
  assert.equal(groups[1].items[0].label, "Budget owner named");
});

test("a withheld item with no reason still says something rather than nothing", () => {
  const groups = withheldSummary({ withheld: [{ kind: "requirement", id: "i1" }] });
  assert.equal(groups[0].reason, "no reason given");
});

test("the withheld sentence adds punctuation and nothing else", () => {
  // The server's reasons are lower-case clauses written to complete this frame. An earlier build
  // supplied a linking "it" here, which read as "held back because it no readiness reading is
  // available" — the view had started rewriting a refusal it did not author.
  const reasons = [
    "no readiness reading is available in this scope",
    "readiness is conflicted, and a customer plan is no place to guess between sources",
    "the evidence behind it is past its freshness window",
  ];
  for (const reason of reasons) {
    assert.equal(withheldSentence(reason), `Held back because ${reason}.`);
  }
});

// --- source manifest -----------------------------------------------------------------------------

test("the manifest is summarized by record type in a stable order", () => {
  const rows = manifestSummary({ source_manifest: [
    { type: "commitment", id: "c1" }, { type: "source_reference", id: "s1" },
    { type: "commitment", id: "c2" }, { type: "milestone", id: "m1" },
  ] });
  assert.deepEqual(rows.map((r) => r.type), ["commitment", "milestone", "source_reference"]);
  assert.equal(rows[0].label, "2 commitments");
  assert.equal(rows[2].label, "1 source reference");
});

// --- promotion preview ---------------------------------------------------------------------------

test("a preview the server would withhold cannot read as ready to confirm", () => {
  const v = previewVerdict({ withheld_reason: "no client-visible source supports it yet" });
  assert.equal(v.ok, false);
  assert.equal(v.detail, "no client-visible source supports it yet");
});

test("a preview with client-safe content reads as what the customer would see", () => {
  assert.equal(previewVerdict({ what: "Confirm the data-processing addendum" }).ok, true);
  assert.equal(previewVerdict({}).ok, false);
});
