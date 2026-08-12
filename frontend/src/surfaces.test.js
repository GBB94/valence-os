/**
 * Stage 17 Slice 1 — the client mirror's derivers (`SURFACE-USAGE-SPEC.md` §4, §5).
 *
 * The registry's agreement with the server is checked from the Python side, which can read both
 * files. What is checked here is the part only the client does: turning a key and a nav state into
 * a payload. The rule under test throughout is that a payload is built from the registry and the
 * closed vocabularies and from nothing else — never from the URL, never from anything on screen.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  SURFACES, SURFACE_KEYS, commandProperties, dismissProperties, engagementProperties,
  isCommand, isSurface, navigationProperties, renderProperties, routeForNav, surfaceMeta,
} from "./surfaces.js";

test("the registry is frozen and every row carries a route, kind, and label", () => {
  assert.throws(() => { SURFACES["today.invented"] = { route: "today" }; });
  assert.ok(SURFACE_KEYS.length >= 25);
  for (const key of SURFACE_KEYS) {
    const meta = SURFACES[key];
    assert.equal(typeof meta.route, "string");
    assert.ok(meta.route.length > 0);
    assert.ok(["section", "panel", "tab", "command", "field_group"].includes(meta.kind));
    assert.ok(meta.label.length > 0);
  }
});

test("commands and surfaces are separate vocabularies", () => {
  assert.ok(isCommand("command.log_interaction"));
  assert.ok(!isSurface("command.log_interaction"));
  assert.ok(isSurface("today.queue"));
  assert.ok(!isCommand("today.queue"));
  assert.ok(!isSurface("today.a_surface_that_never_existed"));
  assert.equal(surfaceMeta("today.a_surface_that_never_existed"), null);
});

test("an unregistered key yields null rather than a half-formed payload", () => {
  // The tracker would drop the event anyway. Returning a payload with `surface: undefined` on it
  // would instead send a render event the report cannot attribute to anything, which can only
  // inflate a total.
  assert.equal(renderProperties("today.not_a_surface"), null);
  assert.equal(engagementProperties("today.not_a_surface", "opened"), null);
  assert.equal(dismissProperties("today.not_a_surface", "closed"), null);
  assert.equal(commandProperties("today.not_a_command", "toolbar"), null);
});

test("a command cannot be reported as rendered, and a surface cannot be invoked", () => {
  assert.equal(renderProperties("command.log_interaction"), null);
  assert.equal(engagementProperties("command.log_interaction", "opened"), null);
  assert.equal(commandProperties("today.queue", "toolbar"), null);
});

test("the render payload carries the registry's route and kind, never a label", () => {
  const properties = renderProperties("overview.account_path", { position: 0 });
  assert.deepEqual(properties, {
    surface: "overview.account_path",
    route: "account.overview",
    kind: "section",
    render_reason: "navigation",
    position: 0,
  });
  assert.ok(!("label" in properties));
});

test("position is a number or nothing — never a string that could carry text", () => {
  assert.equal(renderProperties("today.queue", { position: "second from the top" }).position, null);
  assert.equal(renderProperties("today.queue", { position: -1 }).position, null);
  assert.equal(renderProperties("today.queue", { position: 3 }).position, 3);
});

test("the route comes from nav state, never from the URL", () => {
  assert.equal(routeForNav({ dest: "today" }), "today");
  assert.equal(routeForNav({ dest: "account", accountId: "acc-1", tab: "people" }), "account.people");
  // A missing tab is the workspace default, not the empty string.
  assert.equal(routeForNav({ dest: "account", accountId: "acc-1" }), "account.overview");
  assert.equal(routeForNav(null), null);
  assert.equal(routeForNav({}), null);
});

test("the account id never reaches a route string", () => {
  // The reason `routeForNav` reads nav rather than `window.location`: a URL carries record ids and
  // search terms, and a route field is exactly the kind of property nobody thinks of as content.
  const route = routeForNav({ dest: "account", accountId: "acc-northwind", tab: "ledger" });
  assert.equal(route, "account.ledger");
  assert.ok(!route.includes("acc-northwind"));
});

test("navigation_landed reports a boolean for first-of-session, never a count", () => {
  const properties = navigationProperties({ dest: "today" }, { entryPoint: "keyboard", isFirstOfSession: 1 });
  assert.deepEqual(properties, {
    route: "today", entry_point: "keyboard", is_first_of_session: true,
  });
  assert.equal(navigationProperties({}, {}), null);
});

test("the engagement and dismissal payloads are the shapes the server requires", () => {
  assert.deepEqual(engagementProperties("today.queue", "followed_link"), {
    surface: "today.queue", route: "today", kind: "section", engagement: "followed_link",
  });
  assert.deepEqual(dismissProperties("people.person_card", "closed"), {
    surface: "people.person_card", route: "account.people", dismiss_kind: "closed",
  });
});

test("the client holds no window length, cadence, or reach", () => {
  // §7.7's safety check is computed on the server from `reaches`/`provides`/`explains_refusal`. A
  // client copy of those would be a second place a retirement could be judged safe, and the two
  // would disagree the first time a view changed without the mirror being regenerated.
  for (const key of SURFACE_KEYS) {
    assert.deepEqual(Object.keys(SURFACES[key]).sort(), ["kind", "label", "route"]);
  }
});
