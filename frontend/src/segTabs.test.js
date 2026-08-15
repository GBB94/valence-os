import test from "node:test";
import assert from "node:assert/strict";

import { nextTabKey } from "./segTabs.js";

const tabs = [["operate"], ["prepare"], ["leadership"]];

test("segmented tabs wrap with arrow keys and support Home and End", () => {
  assert.equal(nextTabKey(tabs, "operate", "ArrowRight"), "prepare");
  assert.equal(nextTabKey(tabs, "operate", "ArrowLeft"), "leadership");
  assert.equal(nextTabKey(tabs, "leadership", "ArrowRight"), "operate");
  assert.equal(nextTabKey(tabs, "prepare", "Home"), "operate");
  assert.equal(nextTabKey(tabs, "prepare", "End"), "leadership");
  assert.equal(nextTabKey(tabs, "prepare", "Enter"), null);
  assert.equal(nextTabKey([], "prepare", "ArrowRight"), null);
});
