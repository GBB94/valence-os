import test from "node:test";
import assert from "node:assert/strict";

import { viewScope, viewScopeClauses } from "./viewScope.js";

const BANDS = [
  { key: "now", label: "Needs you now" },
  { key: "week", label: "This week" },
  { key: "watch", label: "Keep an eye" },
];

const ALL = { band: "all", accountId: "", query: "" };

test("a view showing everything states nothing", () => {
  // The strip exists for the silent case. Rendering it unconditionally would make the one place
  // that says "you are not seeing all of this" indistinguishable from page furniture.
  const scope = viewScope(ALL, { bands: BANDS, shown: 41, total: 41 });
  assert.equal(scope.narrowed, false);
  assert.equal(scope.lead, null);
  assert.equal(scope.count, null);
  assert.deepEqual(viewScopeClauses(ALL, { bands: BANDS }), []);
  assert.deepEqual(viewScopeClauses(null, { bands: BANDS }), []);
});

test("a non-empty narrowed view says what it narrowed to and what is not listed", () => {
  // The verified gap: twelve rows under a heading reading "Today" look like the whole day.
  const scope = viewScope({ band: "now", accountId: "", query: "" },
    { bands: BANDS, shown: 12, total: 41 });
  assert.equal(scope.narrowed, true);
  assert.equal(scope.lead, "Narrowed to the Needs you now band.");
  assert.equal(scope.count, "12 of 41 shown · 29 not listed here.");
});

test("every active filter names itself, in the order it is applied", () => {
  const scope = viewScope({ band: "week", accountId: "acc-1", query: "  renewal  " },
    { bands: BANDS, accountName: "Northwind Synthetic", shown: 2, total: 41 });
  assert.deepEqual(scope.clauses.map((c) => c.key), ["band", "account", "query"]);
  assert.equal(scope.lead,
    "Narrowed to the This week band, Northwind Synthetic, and the search “renewal”.");
});

test("an account with no known label is counted, not guessed at", () => {
  // An id in a sentence is noise, and inventing a name we were not handed would be worse than
  // declining to. The narrowing is still stated either way.
  const scope = viewScope({ band: "all", accountId: "acc-9", query: "" },
    { bands: BANDS, shown: 3, total: 41 });
  assert.equal(scope.lead, "Narrowed to one account.");
});

test("a filter that matches everything is still stated as a filter", () => {
  // "0 not listed here" is true and reads as though something were missing. This is the honest
  // reading of the same fact: the filter is on, and nothing falls outside it.
  const scope = viewScope({ band: "now", accountId: "", query: "" },
    { bands: BANDS, shown: 41, total: 41 });
  assert.equal(scope.narrowed, true);
  assert.equal(scope.count, "All 41 items match it.");
  const one = viewScope({ band: "now", accountId: "", query: "" },
    { bands: BANDS, shown: 1, total: 1 });
  assert.equal(one.count, "All 1 item matches it.");
});

test("an unknown band is not treated as a narrowing", () => {
  // `band` is normalised to a known key upstream, but a stale saved view can carry anything. A
  // clause naming a band that filters nothing would describe a narrowing that is not happening.
  const scope = viewScope({ band: "urgent", accountId: "", query: "" },
    { bands: BANDS, shown: 41, total: 41 });
  assert.equal(scope.narrowed, false);
});

test("whitespace is not a search", () => {
  assert.equal(viewScope({ band: "all", accountId: "", query: "   " },
    { bands: BANDS, shown: 41, total: 41 }).narrowed, false);
});

test("the strip states the count and never scores it", () => {
  // §7.3 is the hueless one. There is no coverage reading of a filter, no percentage, and no
  // status: the operator chose this, and a tone here would render their own selection as a fault.
  const scope = viewScope({ band: "now", accountId: "acc-1", query: "renewal" },
    { bands: BANDS, accountName: "Northwind Synthetic", shown: 2, total: 41 });
  assert.deepEqual(Object.keys(scope).sort(), ["clauses", "count", "lead", "narrowed"]);
  assert.equal(/%|percent|score|coverage|healthy|warning|risk/i.test(scope.lead + scope.count), false);
});

test("missing counts degrade to a stated narrowing rather than to NaN", () => {
  const scope = viewScope({ band: "now", accountId: "", query: "" }, { bands: BANDS });
  assert.equal(scope.narrowed, true);
  assert.equal(/NaN|undefined/.test(scope.count), false);
});
