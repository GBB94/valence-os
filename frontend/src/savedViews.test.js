import test from "node:test";
import assert from "node:assert/strict";

import { createCustomView, readCustomViews, resolveSavedView, sameViewState, writeCustomViews } from "./savedViews.js";

function memoryStorage(seed = {}) {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
  };
}

test("saved views round-trip presentation state", () => {
  const storage = memoryStorage();
  const view = createCustomView("My renewals", { query: "renewal", risk: "commercial" }, 1234);
  assert.equal(writeCustomViews(storage, "accounts", [view]), true);
  assert.deepEqual(readCustomViews(storage, "accounts"), [view]);
});

test("corrupt and unsafe saved preferences fail closed", () => {
  const storage = memoryStorage({
    "valence-saved-views:today": JSON.stringify([
      { id: "bad/id", label: "Bad", state: {} },
      { id: "custom-safe", label: "Safe", state: { band: "now" } },
    ]),
  });
  assert.deepEqual(readCustomViews(storage, "today"), [
    { id: "custom-safe", label: "Safe", state: { band: "now" } },
  ]);
  assert.deepEqual(readCustomViews(memoryStorage({ "valence-saved-views:today": "{" }), "today"), []);
  assert.equal(writeCustomViews({ setItem() { throw new Error("quota"); } }, "today", []), false);
});

test("missing view identifiers resolve to the built-in default", () => {
  const builtIns = [{ id: "all", label: "All", state: { band: "all" } }];
  assert.equal(resolveSavedView(builtIns, [], "missing", "all").id, "all");
  assert.equal(sameViewState({ band: "all" }, { band: "all" }), true);
  assert.equal(sameViewState({ band: "all" }, { band: "now" }), false);
});
