import test from "node:test";
import assert from "node:assert/strict";
import {
  acceptFileList, byteLabel, isActivationKey, kindLabel, orderReceipts, outcomeLabel, outcomeTone,
  receipt, screenFile, zoneHint, zoneLabel,
} from "./intakeDrop.js";

const LIMITS = {
  max_bytes: 1000000,
  max_bytes_label: "1 MB",
  max_items_per_drop: 10,
  accepted_extensions: [".txt", ".md", ".vtt", ".srt"],
  accepted_summary: "Email threads, transcripts, or notes.",
  assurance: "Nothing is saved to your trackers until you say so.",
  refusals: { ".pdf": "PDF isn't accepted yet. Open it and paste the text." },
  generic_refusal: "Only text can be dropped here.",
};

const DRAFTED = {
  id: "d1", filename: "kickoff-notes.txt", detected_kind: "notes", byte_length: 4200,
  outcome: "drafted", outcome_reason: null, proposals_drafted: 6, proposals_pending: 6,
  extraction_run_id: "r1", snapshot_present: true, created_at: "2026-08-06T14:02:00Z",
  coverage: {
    read_chars: 4127,
    skipped: [{ reason: "quoted_history", chars: 8840, note: "Quoted history was not read." }],
    named_not_proposed: [], refused: [], other_accounts_mentioned: [], read_whole_thread: false,
  },
};

test("the receipt is an outcome line, and carries nothing that resolves a proposal", () => {
  const view = receipt(DRAFTED);
  assert.equal(view.outcomeLabel, "Drafted");
  assert.equal(view.drafted, 6);
  assert.equal(view.runId, "r1");
  for (const key of Object.keys(view)) {
    assert.ok(!/accept|reject|resolve|supersede|apply/i.test(key),
      `${key} would make the receipt a second review surface`);
  }
});

test("the not-drafted block is present even when there is nothing in it", () => {
  const clean = receipt({ ...DRAFTED, coverage: { ...DRAFTED.coverage, skipped: [] } });
  assert.deepEqual(clean.notDrafted, []);
  assert.equal(clean.notDraftedEmptyNote, "Everything in this document was read.");
});

test("coverage sentences are the server's, never composed here", () => {
  const view = receipt(DRAFTED);
  assert.equal(view.notDrafted[0].note, "Quoted history was not read.");
  const refused = receipt({
    ...DRAFTED, outcome: "rejected_kind", outcome_reason: "PDF isn't accepted yet.",
  });
  assert.equal(refused.reason, "PDF isn't accepted yet.");
  // No fallback sentence: a refusal the server did not author is not shown at all.
  assert.equal(receipt({ ...DRAFTED, outcome_reason: null }).reason, null);
});

test("drafting earns no status colour; only a genuine failure does", () => {
  assert.equal(outcomeTone("drafted"), "quiet");
  assert.equal(outcomeTone("no_proposals"), "quiet");
  assert.equal(outcomeTone("duplicate"), "quiet");
  assert.equal(outcomeTone("rejected_kind"), "warn");
  assert.equal(outcomeTone("parse_failed"), "warn");
});

test("an unknown outcome is shown as itself, never relabelled into a neighbour", () => {
  assert.equal(outcomeLabel("something_new"), "something_new");
  assert.equal(kindLabel("something_new"), "Document");
});

test("failures sort first, then newest within a band", () => {
  const ordered = orderReceipts([
    { id: "a", outcome: "drafted", created_at: "2026-08-01" },
    { id: "b", outcome: "rejected_kind", created_at: "2026-07-01" },
    { id: "c", outcome: "drafted", created_at: "2026-08-05" },
    { id: "d", outcome: "parse_failed", created_at: "2026-07-02" },
  ]);
  assert.deepEqual(ordered.map((d) => d.id), ["b", "d", "c", "a"]);
});

test("client screening only ever repeats the server's own sentence", () => {
  assert.equal(screenFile({ name: "q.pdf", size: 10 }, LIMITS).reason, LIMITS.refusals[".pdf"]);
  assert.equal(screenFile({ name: "q.xyz", size: 10 }, LIMITS).reason, LIMITS.generic_refusal);
  assert.equal(screenFile({ name: "notes.txt", size: 10 }, LIMITS), null);
  assert.equal(screenFile({ name: "notes.txt", size: 10 }, null), null);
  const big = screenFile({ name: "notes.txt", size: 2000000 }, LIMITS);
  assert.equal(big.tooBig, true);
  // The size refusal has no client sentence either — the server states the limit it enforces.
  assert.equal(big.reason, null);
});

test("over the item cap we take none, not a silent prefix", () => {
  const many = Array.from({ length: 12 }, (_, i) => ({ name: `n${i}.txt` }));
  const result = acceptFileList(many, LIMITS);
  assert.deepEqual(result.files, []);
  assert.deepEqual(result.overflow, { count: 12, cap: 10 });
  assert.equal(acceptFileList(many.slice(0, 3), LIMITS).files.length, 3);
});

test("drag-over changes the label, and the label names the account", () => {
  assert.equal(zoneLabel({ dragging: false, busy: false, accountName: "Bluepeak Synthetic" }),
    "Drop a file, or paste a thread");
  assert.equal(zoneLabel({ dragging: true, busy: false, accountName: "Bluepeak Synthetic" }),
    "Drop to add to Bluepeak Synthetic");
  assert.equal(zoneLabel({ dragging: true, busy: true, accountName: "Bluepeak Synthetic" }),
    "Reading…");
});

test("the hint states the limits and the trust sentence before anyone can hit them", () => {
  const hint = zoneHint(LIMITS);
  assert.ok(hint.includes("1 MB"));
  assert.ok(hint.includes("until you say so"));
  assert.equal(zoneHint(null), "");
});

test("the zone is operable without a drag", () => {
  assert.ok(isActivationKey("Enter"));
  assert.ok(isActivationKey(" "));
  assert.ok(!isActivationKey("j"));
});

test("byte labels stay in the same units as the stated limit", () => {
  assert.equal(byteLabel(900), "900 B");
  assert.equal(byteLabel(4200), "4.1 KB");
  assert.equal(byteLabel(1500000), "1.43 MB");
});

// --- Slice 2: a dropped .eml is not a pasted thread -------------------------------------------

const DROPPED_EML = {
  id: "d2", filename: "cohort-2.eml", detected_kind: "email_file", byte_length: 3100,
  outcome: "drafted", outcome_reason: null, proposals_drafted: 3, proposals_pending: 3,
  extraction_run_id: "r2", comm_message_id: "c9", snapshot_present: true,
  created_at: "2026-08-06T15:00:00Z",
  coverage: {
    read_chars: 210,
    skipped: [
      { reason: "quoted_history", chars: 640, note: "Quoted history was not read." },
      { reason: "attachments", chars: 0, note: "1 attachment(s) are named but not read." },
    ],
    named_not_proposed: [], refused: [], other_accounts_mentioned: [], read_whole_thread: false,
  },
};

test("an .eml and a pasted thread are different kinds, because one joins the thread graph", () => {
  assert.equal(kindLabel("email_file"), "Email message");
  assert.equal(kindLabel("email_paste"), "Email thread");
  assert.notEqual(kindLabel("email_file"), kindLabel("email_paste"));
});

test("the correspondence link is carried, and its absence on a paste is not an omission", () => {
  assert.equal(receipt(DROPPED_EML).commMessageId, "c9");
  // A paste has no message id, so it has no thread identity — it says so in `notDrafted` instead.
  const pasted = receipt({ ...DRAFTED, detected_kind: "email_paste", coverage: {
    ...DRAFTED.coverage,
    skipped: [{ reason: "no_message_id", chars: 0,
                note: "Pasted text has no message id, so this is not added to the correspondence record." }],
  } });
  assert.equal(pasted.commMessageId, null);
  assert.ok(pasted.notDrafted.some((e) => e.key === "no_message_id"));
});

test("a refused option reaches the receipt with the server's own reason", () => {
  // `Read the whole thread` is right for a paste and refused for an .eml. A refusal that changed
  // behaviour without saying so would be the worse half of that call.
  const view = receipt({ ...DROPPED_EML, coverage: { ...DROPPED_EML.coverage, refused: [
    { what: "Read the whole thread", why: "Its quoted history carries its own message ids." },
  ] } });
  const entry = view.notDrafted.find((e) => e.key === "refused:Read the whole thread");
  assert.ok(entry);
  assert.equal(entry.note, "Its quoted history carries its own message ids.");
  assert.equal(view.readWholeThread, false);
});

test("an .eml that only duplicates an existing record earns no failure colour", () => {
  const view = receipt({ ...DROPPED_EML, outcome: "duplicate", extraction_run_id: null,
                         proposals_drafted: 0, outcome_reason: "That message is already here." });
  assert.equal(view.outcomeLabel, "Already dropped");
  assert.equal(view.tone, "quiet");
  assert.equal(view.reason, "That message is already here.");
});
