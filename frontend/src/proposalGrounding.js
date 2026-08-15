/**
 * The grounding pane's rules — ACCOUNT-INTAKE-SPEC.md §11.2.
 *
 * Pure functions, tested with `node --test`. There is no React renderer in this harness, so a rule
 * that lives in JSX is a rule nothing tests — and the rules here are the ones that decide whether a
 * citation is honest.
 *
 * Three of them are load-bearing:
 *
 *  - **The quote always renders.** Whether the source survives, whether it was located, and whether
 *    it was windowed are three separate questions, and none of them removes the span. §11.2: "A
 *    missing snapshot degrades the citation; it never removes it."
 *  - **Nothing here composes a sentence.** Every note in `notes` was authored on the server and is
 *    passed through verbatim (D-153). This module selects and orders; it never writes.
 *  - **Marking is a rule *and* a tint, never a tint.** `DESIGN-GUIDE.md` forbids conveying anything
 *    by colour alone, and a highlight is a claim about which words the draft cited — the one place
 *    a colour-blind reader must not be left guessing. The class this returns carries both.
 */

/** The states the server can report for the retained source text. Anything else is shown as-is
 *  rather than folded into a neighbouring one — the shared plan's discipline, for the same reason:
 *  a state we do not recognize is not a state we may reinterpret. */
const DOCUMENT_HEADINGS = {
  present: "Source text",
  deleted: "Source text was deleted",
  never_captured: "No source text was kept",
};

export function documentHeading(state) {
  return DOCUMENT_HEADINGS[state] || "Source text";
}

/**
 * Split the returned document into render segments, one of them marked.
 *
 * Offsets arrive already re-based onto the windowed text, so this never has to know whether the
 * server truncated. Out-of-range or inverted offsets fall back to a single unmarked segment rather
 * than throwing or marking something arbitrary: a highlight in the wrong place is a citation of the
 * wrong words, and no highlight is the safe failure.
 */
export function segmentsOf(text, location) {
  const body = typeof text === "string" ? text : "";
  if (!body) return [];
  const start = location?.found ? Number(location.start) : -1;
  const end = location?.found ? Number(location.end) : -1;
  if (!(start >= 0 && end > start && end <= body.length)) {
    return [{ key: "all", text: body, marked: false }];
  }
  const parts = [];
  if (start > 0) parts.push({ key: "before", text: body.slice(0, start), marked: false });
  parts.push({ key: "marked", text: body.slice(start, end), marked: true });
  if (end < body.length) parts.push({ key: "after", text: body.slice(end), marked: false });
  return parts;
}

/**
 * Everything the pane draws, from the server's payload. `pending` and `error` are states of the
 * fetch, not of the evidence, and they are kept apart from `notes` for that reason — "we could not
 * load this" must never read like "the source is gone".
 */
export function groundingView(payload, { pending = false, error = null } = {}) {
  if (pending) {
    return { status: "loading", span: null, heading: "Source text", notes: [], segments: [],
             filename: null, kind: null, matched: null };
  }
  if (error) {
    return { status: "error", span: null, heading: "Source text",
             notes: [], segments: [], filename: null, kind: null, matched: null, error };
  }
  if (!payload) {
    return { status: "empty", span: null, heading: "Source text", notes: [], segments: [],
             filename: null, kind: null, matched: null };
  }
  const doc = payload.document || {};
  return {
    status: doc.available ? "ready" : "no_document",
    // The citation, unconditionally. Every other field here is allowed to be absent.
    span: payload.span || null,
    locator: payload.locator || null,
    heading: documentHeading(doc.state),
    // Server-authored, in the server's order. Never rewritten, never shortened, never merged.
    notes: payload.notes || [],
    segments: doc.available ? segmentsOf(doc.text, payload.location) : [],
    filename: doc.filename || null,
    kind: doc.kind || null,
    chars: doc.chars || 0,
    truncated: Boolean(doc.truncated),
    // `exact` and `whitespace_normalized` are both real matches and are labelled the same. The
    // distinction is diagnostic, not something to make the reader adjudicate.
    matched: payload.location ? Boolean(payload.location.found) : null,
  };
}
