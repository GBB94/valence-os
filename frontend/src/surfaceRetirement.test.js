import assert from "node:assert/strict";
import test from "node:test";

import {
  COLLAPSE_DISMISS, EXPAND_ENGAGEMENT, PRESENTATIONS, canRestore, presentationFor, retiredRows,
  startsOpen,
} from "./surfaceRetirement.js";

const STATE = {
  "today.queue": { surface: "today.queue", action: "none", cause_code: null },
  "today.saved_views": {
    surface: "today.saved_views", action: "collapse", cause_code: "misunderstood",
    recorded_on: "2026-08-06T09:00:00+00:00",
  },
  "accounts.portfolio_analytics": {
    surface: "accounts.portfolio_analytics", action: "retire", cause_code: "demo_artifact",
    retired_notice: "You retired this view on 2026-08-06.",
  },
  "commercial.whitespace": {
    surface: "commercial.whitespace", action: "demote", cause_code: "not_found",
  },
  "people.champions": { surface: "people.champions", action: "restore", cause_code: "not_needed" },
};

test("each action maps to exactly one presentation and hidden is the only removing one", () => {
  assert.equal(presentationFor(STATE, "today.queue").presentation, "normal");
  assert.equal(presentationFor(STATE, "today.saved_views").presentation, "collapsed");
  assert.equal(presentationFor(STATE, "commercial.whitespace").presentation, "demoted");
  assert.equal(presentationFor(STATE, "accounts.portfolio_analytics").presentation, "hidden");
  assert.deepEqual(PRESENTATIONS, ["normal", "collapsed", "demoted", "hidden"]);
});

test("a restored surface renders exactly as an untouched one", () => {
  // Restoring changes nothing about how the surface looks; it only says so in the record.
  assert.equal(presentationFor(STATE, "people.champions").presentation, "normal");
  assert.equal(presentationFor(STATE, "today.queue").presentation, "normal");
});

test("every failure falls towards showing the surface, never towards hiding it", () => {
  // Wrongly showing something costs clutter. Wrongly hiding it costs a thing the operator cannot
  // find, and the usage data will never mention it — the surface stopped emitting events too.
  for (const state of [null, undefined, {}, { "x.y": {} }]) {
    assert.equal(presentationFor(state, "today.saved_views").presentation, "normal");
  }
  assert.equal(presentationFor({ "a.b": { action: "vaporise" } }, "a.b").presentation, "normal");
  assert.equal(presentationFor({ "a.b": { action: "vaporise" } }, "a.b").action, "none");
});

test("the notice is carried through verbatim and is never composed here", () => {
  const result = presentationFor(STATE, "accounts.portfolio_analytics");
  assert.equal(result.notice, "You retired this view on 2026-08-06.");
  // Nothing is added to it and nothing is stripped from it.
  assert.equal(presentationFor(STATE, "today.saved_views").notice, null);
});

test("a collapsed surface starts closed", () => {
  // §7.2: closed by default, one click to open. Fixed location, varying expansion.
  assert.equal(startsOpen(), false);
});

test("opening a hidden surface reports expanded rather than opened", () => {
  // Reading "I had to open this because it was collapsed" as an ordinary open would make a surface
  // look more engaged the more it had been hidden — the inversion of §6.3.
  assert.equal(EXPAND_ENGAGEMENT, "expanded");
  assert.notEqual(EXPAND_ENGAGEMENT, "opened");
  assert.equal(COLLAPSE_DISMISS, "collapsed");
});

test("the changed list holds only surfaces currently moved and is sorted by key", () => {
  const rows = retiredRows(STATE);
  assert.deepEqual(rows.map((row) => row.surface), [
    "accounts.portfolio_analytics", "commercial.whitespace", "today.saved_views",
  ]);
  // A list that reorders itself as you work it is a list you lose your place in, and this is a
  // record of decisions rather than a leaderboard.
  assert.deepEqual([...rows.map((r) => r.surface)].sort(), rows.map((r) => r.surface));
});

test("an empty or missing state yields no rows rather than throwing", () => {
  assert.deepEqual(retiredRows(null), []);
  assert.deepEqual(retiredRows({}), []);
});

test("restore is offered exactly for the surfaces that carry a hiding action", () => {
  assert.equal(canRestore(STATE, "accounts.portfolio_analytics"), true);
  assert.equal(canRestore(STATE, "today.saved_views"), true);
  assert.equal(canRestore(STATE, "commercial.whitespace"), true);
  assert.equal(canRestore(STATE, "today.queue"), false);
  assert.equal(canRestore(STATE, "people.champions"), false);
  assert.equal(canRestore(STATE, "not.registered"), false);
  assert.equal(canRestore(null, "today.queue"), false);
});

test("nothing here knows the per-kind matrix or the safety check", async () => {
  // The client registry does not mirror `reaches`, `provides`, or `explains_refusal`, and this
  // module must not reintroduce them: a client copy would be a second place a retirement could be
  // judged safe, and the two would eventually disagree.
  const source = await import("node:fs").then((fs) =>
    fs.readFileSync(new URL("./surfaceRetirement.js", import.meta.url), "utf8"));
  for (const forbidden of ["reaches", "provides", "explains_refusal", "AVAILABLE_ACTIONS",
    "field_group"]) {
    const body = source.split("*/").slice(1).join("*/");
    assert.ok(!body.includes(forbidden), `${forbidden} leaked into the client`);
  }
});
