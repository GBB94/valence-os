import test from "node:test";
import assert from "node:assert/strict";

import { ABSENCE_WINDOWS, absenceItems, absenceRecordLabel, normalizeWindow } from "./portfolioAbsence.js";

const PAYLOAD = {
  window: { days: 30, since: "2026-07-07", default_days: 30 },
  basis: "Counts of our own record-keeping over the stated window. They are independent and do not combine into a coverage score.",
  counters: [
    { key: "accounts_without_interaction", count: 62, record_kind: "account",
      sentence: "62 accounts with no recorded interaction in 30 days",
      records: [{ id: "acc-1", name: "Northwind Synthetic" }] },
    { key: "programs_without_touch", count: 0, record_kind: "program",
      sentence: "0 programs in an active phase with no recorded touch in 30 days", records: [] },
  ],
};

test("the counters keep the server's sentence, unedited", () => {
  const items = absenceItems(PAYLOAD);
  assert.equal(items[0].sentence, "62 accounts with no recorded interaction in 30 days");
  assert.equal(items[1].sentence, "0 programs in an active phase with no recorded touch in 30 days");
});

test("the module composes no sentence of its own", () => {
  // The count and the window are both on the payload, so a helper here could assemble the sentence
  // — and then the window shown and the window queried could drift. Feeding it a counter with no
  // sentence must drop the counter, never manufacture one.
  const items = absenceItems({ counters: [{ key: "k", count: 4, record_kind: "account", records: [] }] });
  assert.deepEqual(items, []);
});

test("zero is carried through as zero, not dropped and not softened", () => {
  const zero = absenceItems(PAYLOAD).find((item) => item.key === "programs_without_touch");
  assert.equal(zero.count, 0);
  assert.equal(zero.sentence.startsWith("0 "), true);
});

test("nothing here totals the counters", () => {
  // §4.2 rule 2. Four independent counts about our own record-keeping do not add up to a coverage
  // grade, and the strip is exactly the layout where a reader starts adding them.
  const items = absenceItems(PAYLOAD);
  for (const item of items) {
    assert.deepEqual(Object.keys(item).sort(),
      ["count", "key", "recordKind", "records", "sentence"]);
  }
  const exported = { ABSENCE_WINDOWS, absenceItems, absenceRecordLabel, normalizeWindow };
  for (const name of Object.keys(exported)) {
    assert.equal(/total|sum|score|percent|grade/i.test(name), false, name);
  }
});

test("an absent or malformed payload yields no counters rather than a blank strip of zeroes", () => {
  for (const payload of [null, {}, { counters: null }, { counters: "four" }]) {
    assert.deepEqual(absenceItems(payload), []);
  }
});

test("a program record names its account and phase; an account record names itself", () => {
  assert.deepEqual(
    absenceRecordLabel({ id: "prg-1", name: "Europe", account_name: "Northwind Synthetic", phase: "launch" }, "program"),
    { primary: "Europe", secondary: "Northwind Synthetic · launch" });
  assert.deepEqual(absenceRecordLabel({ id: "acc-1", name: "Northwind Synthetic" }, "account"),
    { primary: "Northwind Synthetic", secondary: "" });
  assert.equal(absenceRecordLabel({}, "account").primary, "Untitled");
});

test("the window control only offers values the server accepts", () => {
  assert.deepEqual(ABSENCE_WINDOWS, [14, 30, 60, 90]);
  assert.equal(normalizeWindow("60", 30), 60);
  // Out of range falls back rather than clamping: the API refuses these, and answering a different
  // question than the one asked is worse than an error.
  assert.equal(normalizeWindow(0, 30), 30);
  assert.equal(normalizeWindow(400, 30), 30);
  assert.equal(normalizeWindow("nonsense", 30), 30);
});
