import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_COMMAND_CENTER_LENS,
  lastVisitStorageKey,
  readLastVisit,
  readPreferredLens,
  resolveCommandCenterLens,
  writeLastVisit,
  writePreferredLens,
} from "./accountCommandCenter.js";

function memoryStorage(seed = {}) {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
  };
}

test("command-center lenses fail closed and explicit URL state wins", () => {
  const storage = memoryStorage({ "valence-command-center:lens:v1": "leadership" });
  assert.equal(readPreferredLens(storage), "leadership");
  assert.equal(resolveCommandCenterLens("prepare", storage), "prepare");
  assert.equal(resolveCommandCenterLens("not-a-lens", storage), "leadership");
  assert.equal(readPreferredLens(memoryStorage({ "valence-command-center:lens:v1": "<script>" })),
    DEFAULT_COMMAND_CENTER_LENS);
});

test("lens preferences tolerate unavailable storage", () => {
  const unavailable = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  assert.equal(readPreferredLens(unavailable), "operate");
  assert.equal(writePreferredLens(unavailable, "prepare"), false);
  assert.equal(writePreferredLens(memoryStorage(), "invalid"), false);
});

test("last visits are isolated by account and program scope", () => {
  const storage = memoryStorage();
  const stamp = "2026-08-03T15:00:00+00:00";
  assert.equal(writeLastVisit(storage, "account-1", undefined, stamp), true);
  assert.equal(writeLastVisit(storage, "account-1", "program-1", stamp), true);
  assert.equal(readLastVisit(storage, "account-1", undefined), stamp);
  assert.equal(readLastVisit(storage, "account-1", "program-1"), stamp);
  assert.notEqual(lastVisitStorageKey("account-1"), lastVisitStorageKey("account-1", "program-1"));
  assert.equal(readLastVisit(storage, "account-2", undefined), null);
  assert.equal(writeLastVisit(storage, "account-1", undefined, "2026-08-03"), false);
});
