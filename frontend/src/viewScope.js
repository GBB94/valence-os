/**
 * View-level scope: what a saved view is narrowing, stated before the numbers (VISIBILITY-SPEC §7.3).
 *
 * The verified gap this closes is small and easy to miss, which is the point. Today's queue already
 * accounts for two kinds of missing row — it explains an empty result, and it states the snoozed
 * remainder behind its own control — but a **non-empty** saved view narrows silently. Twelve rows
 * under a heading that reads "Today" look like the whole day. They are not, and nothing on screen
 * says so.
 *
 * Two rules shape this module:
 *
 * - **Hueless.** `.coverage-callout` carries `is-warning` / `is-healthy`, correct for a per-card
 *   coverage claim and wrong here. A filter the operator chose is not a fault, and colouring it
 *   would make their own selection read as a problem. D-160 in the other direction: a response the
 *   server calls `complete` can still be subtractive, and the subtraction is stated quietly.
 * - **The client may author this sentence, because it is withholding nothing.** D-153 puts refusal
 *   wording on the server precisely because a view that composes part of an "I did not do this"
 *   statement can soften one. That reasoning does not reach here: every row is already in hand and
 *   the operator can see all of them by clearing the filter. Were the narrowing ever moved
 *   server-side, the sentence moves with it.
 *
 * It states the count and never scores it. There is no "coverage" reading of a filter.
 */

/** The narrowing clauses in the order they are applied, each able to name itself. */
export function viewScopeClauses(state, { bands = [], accountName } = {}) {
  const clauses = [];
  const band = (bands || []).find((candidate) => candidate.key === state?.band);
  if (band) clauses.push({ key: "band", text: `the ${band.label} band` });
  if (state?.accountId) {
    // Named where the label is known. "one account" rather than an id: an id in a sentence is
    // noise, and guessing a name we were not given would be worse than declining to.
    clauses.push({ key: "account", text: accountName ? accountName : "one account" });
  }
  const query = (state?.query || "").trim();
  if (query) clauses.push({ key: "query", text: `the search “${query}”` });
  return clauses;
}

function join(texts) {
  if (texts.length === 1) return texts[0];
  if (texts.length === 2) return `${texts[0]} and ${texts[1]}`;
  return `${texts.slice(0, -1).join(", ")}, and ${texts[texts.length - 1]}`;
}

function plural(count, noun) {
  return count === 1 ? noun : `${noun}s`;
}

/**
 * `{ narrowed, clauses, lead, count }`, or `narrowed: false` when the view shows everything.
 *
 * `count` is stated separately from `lead` so the view can render the number at its own weight
 * without the sentence being reassembled anywhere else.
 */
export function viewScope(state, { bands, accountName, shown, total } = {}) {
  const clauses = viewScopeClauses(state, { bands, accountName });
  if (!clauses.length) return { narrowed: false, clauses: [], lead: null, count: null };
  const visible = Number.isFinite(shown) ? shown : 0;
  const all = Number.isFinite(total) ? total : visible;
  const hidden = Math.max(0, all - visible);
  return {
    narrowed: true,
    clauses,
    lead: `Narrowed to ${join(clauses.map((clause) => clause.text))}.`,
    // A filter that happens to match everything is still a filter, and saying so is the honest
    // reading — "0 not listed" would be true and would read as though something were missing.
    count: hidden === 0
      ? `All ${all} ${plural(all, "item")} ${all === 1 ? "matches" : "match"} it.`
      : `${visible} of ${all} shown · ${hidden} not listed here.`,
  };
}
