/**
 * Reading the portfolio absence counters (VISIBILITY-SPEC §4).
 *
 * The whole module is a normaliser. It deliberately does two things it could easily be tempted out
 * of:
 *
 * It **renders the server's sentence and never builds one.** The count and the window both arrive
 * on the payload, so a view here could assemble "62 accounts with no recorded note in 30 days"
 * itself — and then the window shown and the window queried could drift apart by one refactor. The
 * sentence is the server's string, passed through.
 *
 * It **never totals.** There is no sum, no percentage, no "N of M accounts", and no export that
 * could become one. Four independent counts about our own record-keeping do not add up to a
 * coverage grade, and a strip is exactly the layout where a reader starts adding them (§4.2, rule 2).
 */

// The windows offered in the control. The default lives on the payload (`window.default_days`), not
// here, so the server stays the one place it is decided.
export const ABSENCE_WINDOWS = [14, 30, 60, 90];

/** The counters, normalised, in the server's order. A counter with no sentence is dropped rather
 *  than shown with a fabricated one. */
export function absenceItems(payload) {
  const counters = (payload || {}).counters;
  if (!Array.isArray(counters)) return [];
  return counters
    .map((counter) => ({
      key: counter.key,
      count: Number.isInteger(counter.count) ? counter.count : 0,
      sentence: typeof counter.sentence === "string" ? counter.sentence : "",
      recordKind: counter.record_kind || "record",
      records: Array.isArray(counter.records) ? counter.records : [],
    }))
    .filter((counter) => counter.sentence);
}

/** How one counted record reads in the list the number links to. */
export function absenceRecordLabel(record, recordKind) {
  const primary = (record || {}).name || "Untitled";
  if (recordKind === "program") {
    const parts = [record.account_name, record.phase].filter(Boolean);
    return { primary, secondary: parts.join(" · ") };
  }
  return { primary, secondary: "" };
}

/**
 * The window control's value, clamped to what the server will accept.
 *
 * A value outside the range is refused by the API rather than clamped there — answering a different
 * question than the one asked is worse than an error — so the control never offers one.
 */
export function normalizeWindow(days, fallback) {
  const value = Number(days);
  return ABSENCE_WINDOWS.includes(value) ? value : fallback;
}
