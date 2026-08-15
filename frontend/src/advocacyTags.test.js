import test from "node:test";
import assert from "node:assert/strict";

import { advocacyTagBody, advocacyTagDraft } from "./advocacyTags.js";

const FULL = {
  kind: "reference",
  occurred_on: "2026-06-18",
  evidence_note: "Agreed on the 18 Jun call to take reference calls for the rollout.",
};

test("a complete draft is valid and blocks nothing", () => {
  const check = advocacyTagDraft(FULL);
  assert.equal(check.valid, true);
  assert.deepEqual(check.missing, []);
  assert.equal(check.reason, null);
});

test("a draft missing the date or the note names what the record would lack", () => {
  assert.equal(advocacyTagDraft({ ...FULL, occurred_on: "" }).reason,
    "A tag records the date it happened.");
  assert.equal(advocacyTagDraft({ ...FULL, evidence_note: "" }).reason,
    "A tag records an evidence note.");
  assert.equal(advocacyTagDraft({ kind: "quote" }).reason,
    "A tag records the date it happened and an evidence note.");
  assert.equal(advocacyTagDraft({}).reason,
    "A tag records a kind, the date it happened and an evidence note.");
});

test("whitespace is not a note and not a date", () => {
  assert.equal(advocacyTagDraft({ ...FULL, evidence_note: "   " }).valid, false);
  assert.equal(advocacyTagDraft({ ...FULL, occurred_on: "  " }).valid, false);
  assert.equal(advocacyTagDraft(null).valid, false);
});

test("the body carries the four fields the record has and nothing else", () => {
  // The point of the explicit object: a form that grew a `level` field cannot post one.
  const body = advocacyTagBody("p1", { ...FULL, level: "high", sentiment: "positive", score: 9 });
  assert.deepEqual(Object.keys(body).sort(),
    ["evidence_note", "kind", "occurred_on", "person_id"]);
  assert.equal("level" in body, false);
  assert.equal("sentiment" in body, false);
  assert.equal("score" in body, false);
});

test("the body trims, so a note of spaces reaches the server as the refusal it is", () => {
  const body = advocacyTagBody("p1", { kind: "quote", occurred_on: " 2026-06-18 ", evidence_note: "  " });
  assert.equal(body.occurred_on, "2026-06-18");
  assert.equal(body.evidence_note, "");
});

test("the module holds no vocabulary of its own", async () => {
  // The five kinds live on the server and arrive with the person's tags. A copy here would be a
  // second list, and the one that drifted would be the one an operator was choosing from.
  const module = await import("./advocacyTags.js");
  assert.deepEqual(Object.keys(module).sort(), ["advocacyTagBody", "advocacyTagDraft"]);
});
