import test from "node:test";
import assert from "node:assert/strict";

import { navigationUrl, parseNavigation, sameNavigation } from "./navigation.js";

test("global destinations parse and serialize canonically", () => {
  assert.deepEqual(parseNavigation({ pathname: "/", search: "" }), { dest: "today" });
  assert.equal(navigationUrl(parseNavigation({ pathname: "/", search: "" })), "/today");
  assert.deepEqual(parseNavigation({ pathname: "/library", search: "" }), { dest: "library" });
  assert.deepEqual(parseNavigation({ pathname: "/operations", search: "" }), { dest: "operations" });
});

test("account routes preserve tab and program scope", () => {
  const nav = parseNavigation({ pathname: "/accounts/acct-1/commercial", search: "?program=program-2" });
  assert.deepEqual(nav, { dest: "account", accountId: "acct-1", tab: "commercial", programId: "program-2" });
  assert.equal(navigationUrl(nav), "/accounts/acct-1/commercial?program=program-2");
});

test("invalid tabs and routes fail closed", () => {
  assert.deepEqual(parseNavigation({ pathname: "/accounts/acct-1/not-a-tab", search: "" }), {
    dest: "account", accountId: "acct-1", tab: "overview",
  });
  assert.deepEqual(parseNavigation({ pathname: "/unknown/place", search: "" }), { dest: "today" });
  assert.equal(navigationUrl({ dest: "account" }), "/today");
});

test("saved view identifiers are bounded and addressable", () => {
  assert.deepEqual(parseNavigation({ pathname: "/today", search: "?view=needs-now" }), {
    dest: "today", view: "needs-now",
  });
  assert.deepEqual(parseNavigation({ pathname: "/accounts", search: "?view=%3Cscript%3E" }), {
    dest: "accounts",
  });
  assert.equal(navigationUrl({ dest: "accounts", view: "commercial-risk" }), "/accounts?view=commercial-risk");
});

test("navigation equality compares the canonical URL", () => {
  assert.equal(sameNavigation({ dest: "today" }, { dest: "today" }), true);
  assert.equal(sameNavigation({ dest: "account", accountId: "a", tab: "overview" }, {
    dest: "account", accountId: "a", tab: "ledger",
  }), false);
});
