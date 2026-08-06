import test from "node:test";
import assert from "node:assert/strict";

import { documentHeading, groundingView, segmentsOf } from "./proposalGrounding.js";

const SPAN = "Ada will send the rollout plan by Friday.";
const TEXT = `Kickoff notes\n${SPAN}\nRisk: the room may slip.\n`;
const START = TEXT.indexOf(SPAN);

function payload(over = {}) {
  return {
    proposal_id: "p1",
    run_id: "r1",
    span: SPAN,
    locator: { line: 2 },
    document: {
      state: "present", available: true, text: TEXT,
      chars: TEXT.length, window_start: 0, truncated: false,
      drop_id: "d1", filename: "kickoff-notes.txt", kind: "notes", deleted_at: null,
    },
    location: { found: true, start: START, end: START + SPAN.length,
                match: "exact", occurrences: 1 },
    notes: [],
    ...over,
  };
}

// --- segmentsOf ---------------------------------------------------------------------------------

test("the marked segment is exactly the cited text and nothing else", () => {
  const p = payload();
  const parts = segmentsOf(p.document.text, p.location);
  const marked = parts.filter((s) => s.marked);
  assert.equal(marked.length, 1);
  assert.equal(marked[0].text, p.span);
  // And the split is lossless — nothing is dropped on the way to the screen.
  assert.equal(parts.map((s) => s.text).join(""), p.document.text);
});

test("a quote at the very start or end still produces one marked segment", () => {
  const text = "Ada will send the plan.";
  const whole = segmentsOf(text, { found: true, start: 0, end: text.length });
  assert.deepEqual(whole, [{ key: "marked", text, marked: true }]);

  const head = segmentsOf(text, { found: true, start: 0, end: 3 });
  assert.deepEqual(head.map((s) => s.marked), [true, false]);
});

test("an unlocatable quote marks nothing rather than marking something arbitrary", () => {
  // The choice this asserts: a highlight in the wrong place is a citation of the wrong words, so
  // the failure has to be no highlight — not a nearest guess.
  const text = "Kickoff notes\n";
  for (const location of [
    null,
    { found: false, start: 0, end: 5 },
    { found: true, start: -1, end: 5 },
    { found: true, start: 5, end: 2 },
    { found: true, start: 2, end: 900 },
    { found: true, start: 3, end: 3 },
  ]) {
    const parts = segmentsOf(text, location);
    assert.deepEqual(parts, [{ key: "all", text, marked: false }],
      `expected no mark for ${JSON.stringify(location)}`);
  }
});

test("no text is no segments, not an empty mark", () => {
  assert.deepEqual(segmentsOf("", { found: true, start: 0, end: 4 }), []);
  assert.deepEqual(segmentsOf(null, null), []);
});

// --- documentHeading ----------------------------------------------------------------------------

test("each document state gets its own heading and an unknown one is not folded into a wrong one", () => {
  assert.equal(documentHeading("present"), "Source text");
  assert.equal(documentHeading("deleted"), "Source text was deleted");
  assert.equal(documentHeading("never_captured"), "No source text was kept");
  // A state we do not recognize gets the neutral heading. What it must never get is "deleted" or
  // "no source text kept" — either would be a claim about the record that nothing established.
  assert.equal(documentHeading("something_new"), "Source text");
});

// --- groundingView ------------------------------------------------------------------------------

test("the quote survives every degraded state of its source", () => {
  // §11.2, the whole rule in one assertion set. Deleted, never captured, and unlocatable are three
  // different reasons the text is not on screen, and none of them is a reason to drop the citation.
  const deleted = groundingView(payload({
    document: { state: "deleted", available: false, text: null, deleted_at: "2026-08-06" },
    location: null,
    notes: ["Source text was deleted on 2026-08-06. This quote is what the draft was made from."],
  }));
  assert.equal(deleted.status, "no_document");
  assert.equal(deleted.span, "Ada will send the rollout plan by Friday.");
  assert.equal(deleted.heading, "Source text was deleted");
  assert.deepEqual(deleted.segments, []);

  const never = groundingView(payload({
    document: { state: "never_captured", available: false, text: null },
    location: null,
    notes: ["No source text was kept for this run."],
  }));
  assert.equal(never.span, "Ada will send the rollout plan by Friday.");
  assert.equal(never.heading, "No source text was kept");

  const unfound = groundingView(payload({
    location: { found: false, start: null, end: null, match: null, occurrences: 0 },
    notes: ["That quote is not in the retained text as written."],
  }));
  assert.equal(unfound.span, "Ada will send the rollout plan by Friday.");
  assert.equal(unfound.matched, false);
  assert.equal(unfound.segments.filter((s) => s.marked).length, 0);
});

test("server notes pass through verbatim, in order, and nothing here writes one", () => {
  // D-153: a view that composes any part of an "I did not do this" statement can soften one. So the
  // assertion is identity, not a substring match.
  const notes = [
    "Showing 3000 of 41000 characters, around the quote.",
    "That passage appears 2 times in this document. The first is marked.",
  ];
  const view = groundingView(payload({ notes }));
  assert.deepEqual(view.notes, notes);
  assert.equal(view.notes[0], notes[0]);

  // And with no notes there is no invented one.
  assert.deepEqual(groundingView(payload()).notes, []);
});

test("a failed fetch never reads like a missing source", () => {
  const failed = groundingView(null, { error: "network" });
  assert.equal(failed.status, "error");
  assert.equal(failed.error, "network");
  // The three things that would make it look like an evidence problem instead of a load problem:
  assert.equal(failed.heading, "Source text");
  assert.deepEqual(failed.notes, []);
  assert.equal(failed.matched, null);

  const loading = groundingView(null, { pending: true });
  assert.equal(loading.status, "loading");
  assert.deepEqual(loading.notes, []);

  const empty = groundingView(null);
  assert.equal(empty.status, "empty");
});

test("both match strategies are presented as a match, because the difference is diagnostic", () => {
  const exact = groundingView(payload());
  const rewrapped = groundingView(payload({
    location: { found: true, start: START, end: START + SPAN.length,
                match: "whitespace_normalized", occurrences: 1 },
  }));
  assert.equal(exact.matched, true);
  assert.equal(rewrapped.matched, true);
  assert.equal(exact.heading, rewrapped.heading);
  // Nothing asks the reader to adjudicate which kind of match they got.
  assert.equal(rewrapped.notes.length, 0);
});

test("truncation is reported as a fact about the document, not inferred from the text length", () => {
  const view = groundingView(payload({
    document: { ...payload().document, truncated: true, chars: 41000, window_start: 8200 },
    notes: ["Showing 3000 of 41000 characters, around the quote."],
  }));
  assert.equal(view.truncated, true);
  assert.equal(view.chars, 41000);
  assert.equal(view.status, "ready");
});
