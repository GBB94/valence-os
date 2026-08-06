/**
 * Public-facing advocacy tags (VISIBILITY-SPEC §8, migration 0054).
 *
 * The schema requires a date and an evidence note — NOT NULL plus a non-empty CHECK — so the only
 * job here is to say *which* one is missing before the request is sent. This is not a second
 * validation the server trusts: an empty draft that reached the API would still 422. It exists so
 * the operator reads "an evidence note" rather than a constraint name.
 *
 * `advocacyTagBody` returns exactly the four fields the record has. It is written as an explicit
 * object rather than a spread of the draft precisely so that a `level`, `strength`, or `sentiment`
 * added to a form somewhere cannot ride along into the request — §9 refuses those outright, and
 * the shortest path to one existing is a form field nobody notices being posted.
 */

const BLOCKER = {
  kind: "a kind",
  occurred_on: "the date it happened",
  evidence_note: "an evidence note",
};

/** The order blockers are read back in, so the sentence is stable between renders. */
const ORDER = ["kind", "occurred_on", "evidence_note"];

function filled(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function advocacyTagDraft(draft) {
  const d = draft || {};
  const missing = ORDER.filter((field) => !filled(d[field]));
  return {
    valid: missing.length === 0,
    missing,
    // A tag without these is not a lighter record, it is a different and worse one — so the
    // sentence says what the tag would be missing rather than what the form is missing.
    reason: missing.length === 0 ? null
      : `A tag records ${missing.map((f) => BLOCKER[f]).join(", ")
        .replace(/, ([^,]*)$/, missing.length > 1 ? " and $1" : "$1")}.`,
  };
}

export function advocacyTagBody(personId, draft) {
  const d = draft || {};
  return {
    person_id: personId,
    kind: d.kind,
    occurred_on: (d.occurred_on || "").trim(),
    evidence_note: (d.evidence_note || "").trim(),
  };
}
