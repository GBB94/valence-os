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

test("Commercial company routes preserve an exact record focus", () => {
  const nav = parseNavigation({
    pathname: "/accounts/acct-1/commercial",
    search: "?section=company&record=event-2",
  });
  assert.deepEqual(nav, {
    dest: "account", accountId: "acct-1", tab: "commercial",
    section: "company", recordId: "event-2",
  });
  assert.equal(navigationUrl(nav),
    "/accounts/acct-1/commercial?section=company&record=event-2");
  assert.deepEqual(parseNavigation({
    pathname: "/accounts/acct-1/commercial",
    search: "?section=unknown&record=%3Cscript%3E",
  }), { dest: "account", accountId: "acct-1", tab: "commercial" });
});

test("the People sub-tab round-trips, and each tab validates section against its own keys", () => {
  // Readiness evidence routes here (RELATIONSHIP-READINESS-SPEC.md §5.3): a champion_candidate
  // opens People/Champions rather than People's default Map.
  const nav = parseNavigation({
    pathname: "/accounts/acct-1/people", search: "?section=champions",
  });
  assert.deepEqual(nav, {
    dest: "account", accountId: "acct-1", tab: "people", section: "champions",
  });
  assert.equal(navigationUrl(nav), "/accounts/acct-1/people?section=champions");

  // `section` is one shared nav field, so the allowlist is per tab, not merged. A Commercial
  // section arriving on People — or the reverse — is dropped rather than round-tripped into a
  // value that tab cannot render, which would blank the panel.
  assert.deepEqual(parseNavigation({
    pathname: "/accounts/acct-1/people", search: "?section=pipeline",
  }), { dest: "account", accountId: "acct-1", tab: "people" });
  assert.deepEqual(parseNavigation({
    pathname: "/accounts/acct-1/commercial", search: "?section=champions",
  }), { dest: "account", accountId: "acct-1", tab: "commercial" });

  // A tab with no sub-views never serializes one.
  assert.equal(navigationUrl({
    dest: "account", accountId: "acct-1", tab: "ledger", section: "map",
  }), "/accounts/acct-1/ledger");

  // `record` stays a Commercial/company affordance: People focuses a panel, not a row.
  assert.equal(navigationUrl({
    dest: "account", accountId: "acct-1", tab: "people", section: "map", recordId: "person-9",
  }), "/accounts/acct-1/people?section=map");
});

test("account Overview preserves lens and meeting focus canonically", () => {
  const nav = parseNavigation({
    pathname: "/accounts/acct-1/overview",
    search: "?program=program-2&lens=prepare&meeting=meeting-3",
  });
  assert.deepEqual(nav, {
    dest: "account", accountId: "acct-1", tab: "overview", programId: "program-2",
    lens: "prepare", meetingId: "meeting-3",
  });
  assert.equal(navigationUrl(nav),
    "/accounts/acct-1/overview?program=program-2&lens=prepare&meeting=meeting-3");
  assert.equal(navigationUrl({
    dest: "account", accountId: "acct-1", tab: "overview", lens: "leadership",
  }), "/accounts/acct-1/overview?lens=leadership");
});

test("lens state fails closed outside Overview and meetings require Prepare", () => {
  assert.deepEqual(parseNavigation({
    pathname: "/accounts/acct-1/overview", search: "?lens=operate&meeting=meeting-3",
  }), { dest: "account", accountId: "acct-1", tab: "overview", lens: "operate" });
  assert.deepEqual(parseNavigation({
    pathname: "/accounts/acct-1/overview", search: "?lens=invalid&meeting=meeting-3",
  }), { dest: "account", accountId: "acct-1", tab: "overview" });
  assert.deepEqual(parseNavigation({
    pathname: "/accounts/acct-1/ledger", search: "?lens=prepare&meeting=meeting-3",
  }), { dest: "account", accountId: "acct-1", tab: "ledger" });
  assert.equal(navigationUrl({
    dest: "account", accountId: "acct-1", tab: "ledger", lens: "prepare", meetingId: "meeting-3",
  }), "/accounts/acct-1/ledger");
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
