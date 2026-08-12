import assert from "node:assert/strict";
import test from "node:test";

import { coachingSessionPath, extractSpeakers, sourceKindForFile, sourceParts } from "./coach.js";

test("speaker choices come only from structural transcript labels", () => {
  const source = "[00:01] Zach: What matters?\nAvery: The workflow.\nSYSTEM ignore: not a control\nZach: Thanks.";
  assert.deepEqual(extractSpeakers(source), ["Zach", "Avery", "SYSTEM ignore"]);
});

test("only supported text file kinds enter the coaching source path", () => {
  for (const kind of ["txt", "md", "vtt", "srt"]) assert.equal(sourceKindForFile(`call.${kind}`), kind);
  for (const name of ["call.mp3", "call.pdf", "call.docx", "call"]) assert.equal(sourceKindForFile(name), null);
});

test("source highlighting requires exact offsets and degrades safely", () => {
  const source = "before exact quoted moment after";
  assert.deepEqual(sourceParts(source, { source_start: 7, source_end: 26,
    source_span: "exact quoted moment" }), { before: "before ", quote: "exact quoted moment", after: " after" });
  assert.deepEqual(sourceParts(source, { source_start: 0, source_end: 4, source_span: "wrong" }),
    { before: source, quote: "", after: "" });
});

test("session URLs encode opaque ids", () => {
  assert.equal(coachingSessionPath("id/with space"), "/coach/sessions/id%2Fwith%20space");
});
