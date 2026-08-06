import test from "node:test";
import assert from "node:assert/strict";

import { answerBlocks } from "./copilotAnswer.js";

// Verbatim shape of what `copilot_model._answer` emits for a `fact` run — heading, blank line,
// bullets, then the evidence section the server parses back out of this same string.
const FACT_ANSWER = [
  "## Answer",
  "",
  "- Send an anonymized aggregate cohort summary for June.; status: open; due date: 2026-07-16 [p001]",
  "- Fund the executive sponsor touch; status: open; due date: 2026-07-20 [p002]",
  "",
  "### Evidence gaps",
  "- 1 candidate record(s) were excluded by reader or safety rules.",
].join("\n");

test("the generator's block vocabulary becomes blocks, and the syntax stops being visible", () => {
  assert.deepEqual(answerBlocks(FACT_ANSWER).map((b) => b.kind),
    ["h2", "list", "h3", "list"]);
  const [heading, bullets, gapsHeading, gaps] = answerBlocks(FACT_ANSWER);
  assert.equal(heading.text, "Answer");
  assert.equal(bullets.items.length, 2);
  assert.match(bullets.items[0], /^Send an anonymized aggregate cohort summary/);
  assert.equal(gapsHeading.text, "Evidence gaps");
  assert.equal(gaps.items.length, 1);

  // The blank line under a heading closes the block; it must not become an empty paragraph, which
  // is what renders as a stray gap on screen.
  assert.equal(answerBlocks(FACT_ANSWER).some((b) => b.kind === "text"), false);

  // The two lists are separate blocks. Merging them across the `### Evidence gaps` heading would
  // put a named gap in with the answer's claims, which is the one thing this section exists to
  // keep apart.
  assert.notEqual(bullets, gaps);
});

test("inline markers survive verbatim, because the text may be quoted from a record", () => {
  // A record's own prose is untrusted data (ACCOUNT-COPILOT-SPEC.md): it is shown, never rewritten.
  const blocks = answerBlocks("- Renewal **must** clear legal <b>first</b> · 40% * 2 [p001]");
  assert.equal(blocks[0].items[0], "Renewal **must** clear legal <b>first</b> · 40% * 2 [p001]");
});

test("a soft-wrapped paragraph stays one paragraph, and a blank line ends it", () => {
  const blocks = answerBlocks("First line\ncontinues here.\n\nA second paragraph.");
  assert.deepEqual(blocks.map((b) => b.kind), ["text", "text"]);
  assert.equal(blocks[0].text, "First line\ncontinues here.");
  assert.equal(blocks[1].text, "A second paragraph.");
});

test("an abstention carries no body, and an empty body produces no blocks", () => {
  assert.deepEqual(answerBlocks(null), []);
  assert.deepEqual(answerBlocks(""), []);
  assert.deepEqual(answerBlocks("\n\n  \n"), []);
});

test("a heading marker only counts at the start of a line with its space", () => {
  // `##hashtag` and a mid-line `- ` are ordinary prose, not structure.
  const blocks = answerBlocks("##hashtag\nowner - unassigned");
  assert.deepEqual(blocks.map((b) => b.kind), ["text"]);
  assert.equal(blocks[0].text, "##hashtag\nowner - unassigned");
});
