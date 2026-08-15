import test from "node:test";
import assert from "node:assert/strict";

import {
  PREVIEW_CAP, combinedReviewRows, previewCards, proposalMarks, proposalTitle, sourceLabel,
} from "./proposalPreview.js";

function proposal(over = {}) {
  return {
    id: "p1", kind: "extraction_proposal", intent: "create", target_type: "task",
    status: "proposed", created_at: "2026-08-04T09:00:00Z",
    payload: { description: "Publish the rollout plan" },
    source: { kind: "transcript", span: "Action item: publish the rollout plan." },
    validation_warnings: [], match_candidates: [], conflict: null,
    ...over,
  };
}

const SOURCE = {
  run_id: "r1", kind: "transcript", created_at: "2026-08-04T09:00:00Z",
  interaction: { occurred_on: "2026-08-03" }, extractor: { backend: "mock" },
};

function payload(over = {}) {
  return {
    groups: [{ source: SOURCE, count: 1,
               targets: [{ target_type: "task", count: 1, proposals: [proposal()] }] }],
    manual_capture: [],
    counts: { proposals: 1, manual_capture: 0 },
    ...over,
  };
}

test("the Overview preview is capped but reports the whole backlog behind it", () => {
  // Three cards over a backlog of eleven must not read as three items of work (§8.1).
  const preview = previewCards({
    pending_count: 11,
    proposals: [proposal({ id: "a" }), proposal({ id: "b" }), proposal({ id: "c" })],
    latest_source: SOURCE,
  });
  assert.equal(preview.cards.length, PREVIEW_CAP);
  assert.equal(preview.pending, 11);
  assert.equal(preview.hiddenCount, 8);
  assert.equal(preview.empty, false);
});

test("nothing pending is said plainly instead of rendered as a zero", () => {
  const preview = previewCards({ pending_count: 0, proposals: [], latest_source: null });
  assert.equal(preview.empty, true);
  assert.equal(preview.hiddenCount, 0);
  assert.deepEqual(preview.cards, []);
  assert.equal(preview.source, null);
});

test("a proposal reads as proposed and cited, never as an account status", () => {
  const marks = proposalMarks(proposal());
  assert.deepEqual(marks.map((m) => m.key), ["kind", "cited"]);
  // Green/amber/red are reserved for account status, and the accent for interaction. A draft is
  // neither, so it may borrow neither.
  assert.ok(!marks.some((m) => ["ok", "risk", "accent"].includes(m.mark)));
  assert.equal(marks[0].mark, "draft");
  // No mark is colour-only: every one carries a word.
  assert.ok(marks.every((m) => m.label && m.label.length > 2));
});

test("a stale update and its candidates are shown as review signals, not as failures", () => {
  const marks = proposalMarks(proposal({
    intent: "update",
    conflict: { stale: true, fields: [] },
    match_candidates: [{ check: "exact_content" }],
    validation_warnings: ["Owner could not be resolved."],
  }));
  const byKey = Object.fromEntries(marks.map((m) => [m.key, m]));
  assert.match(byKey.conflict.label, /changed since drafted/);
  assert.equal(byKey.candidates.label, "1 possible match");
  assert.equal(byKey.warnings.label, "1 warning");
  assert.equal(byKey.conflict.mark, "warn");
});

test("the intent is spelled out in the title so a change never reads as a new record", () => {
  assert.match(proposalTitle(proposal()), /^New task: Publish the rollout plan$/);
  assert.match(proposalTitle(proposal({ intent: "update", target_type: "person",
                                        payload: { name: "Sam Okafor" } })),
               /^Change to person: Sam Okafor$/);
});

test("the combined list keeps two vocabularies and two command sets", () => {
  // §0.5 permits the combined experience and forbids the merge. Flattening the status words here
  // would be the merge, in the UI instead of the schema.
  const rows = combinedReviewRows(payload({
    manual_capture: [{ kind: "capture_item", id: "n1", text: "Ask about the security review",
                       status: "untriaged", created_at: "2026-08-04T10:00:00Z",
                       commands: ["convert", "dismiss"] }],
  }));
  const note = rows.find((r) => r.kind === "capture_item");
  const drafted = rows.find((r) => r.kind === "extraction_proposal");
  assert.equal(note.statusLabel, "untriaged");
  assert.equal(drafted.statusLabel, "proposed");
  assert.deepEqual(note.commands, ["convert", "dismiss"]);
  assert.ok(drafted.commands.includes("use_existing"));
  assert.ok(!drafted.commands.includes("convert"));
  assert.ok(!note.commands.includes("accept"));
});

test("a hand-typed note is never dressed as cited", () => {
  const rows = combinedReviewRows(payload({
    manual_capture: [{ id: "n1", text: "Ask about the security review", status: "untriaged",
                       created_at: "2026-08-04T10:00:00Z" }],
  }));
  const note = rows.find((r) => r.kind === "capture_item");
  assert.equal(note.span, null);
  assert.equal(note.source, null);
  assert.ok(!note.marks.some((m) => m.key === "cited"));
});

test("the combined list is newest-first regardless of which store a row came from", () => {
  const rows = combinedReviewRows(payload({
    manual_capture: [{ id: "n1", text: "Later note", status: "untriaged",
                       created_at: "2026-08-05T10:00:00Z" }],
  }));
  assert.deepEqual(rows.map((r) => r.id), ["n1", "p1"]);
});

test("the source line names what was read, when, and by which extractor", () => {
  assert.equal(sourceLabel(SOURCE), "transcript · 2026-08-03 · mock extractor");
  assert.equal(sourceLabel(null), "Unknown source");
});
