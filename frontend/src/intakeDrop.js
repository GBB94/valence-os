/**
 * Drop-zone logic — ACCOUNT-INTAKE-SPEC.md §16.
 *
 * Everything the drop zone decides lives here as pure functions, because there is no React
 * renderer and no jsdom in this harness: a rule that lives in JSX is a rule nothing tests. The
 * view draws what these return and adds no judgement of its own.
 *
 * Two rules are load-bearing and easy to lose in a refactor:
 *
 *  - **The client never composes a refusal or a coverage sentence.** Both are authored on the
 *    server (§14, D-153). A view that composes any part of an "I did not do this" statement is a
 *    view that can soften one, so these functions *select* and *order* server text and never
 *    build it. `dropSummary` returns the server's sentence verbatim or nothing.
 *  - **Nothing here resolves a proposal.** The receipt is an outcome line and a link. Accepting
 *    happens in `ProposalReview`, which is the one place a drafted proposal becomes a decision.
 */

/** §16.3 — failures first. The failures are what need action; the successes are already done. */
const OUTCOME_ORDER = {
  rejected_kind: 0,
  parse_failed: 1,
  no_proposals: 2,
  duplicate: 3,
  drafted: 4,
};

const KIND_LABELS = {
  notes: "Meeting notes",
  email_paste: "Email thread",
  // Distinct from `email_paste` on purpose. An .eml carries a Message-ID, so it joins the
  // correspondence record and the thread graph; a paste cannot, and says so in its own coverage
  // reason. One label for both would make `commMessageId` being absent unreadable.
  email_file: "Email message",
  transcript: "Transcript",
};

/** A drop whose outcome is not one of ours is shown as-is rather than relabelled into a
 *  neighbouring one — the same discipline as the shared plan's withheld readings. */
export function kindLabel(kind) {
  return KIND_LABELS[kind] || "Document";
}

export function outcomeTone(outcome) {
  // Status colour belongs to account condition. A drop is our own processing of a file, so only a
  // genuine failure earns a warn tone, and "drafted" earns none at all — a draft nobody has
  // accepted is not an account condition.
  if (outcome === "rejected_kind" || outcome === "parse_failed") return "warn";
  return "quiet";
}

export function outcomeLabel(outcome) {
  switch (outcome) {
    case "drafted": return "Drafted";
    case "no_proposals": return "Nothing drafted";
    case "rejected_kind": return "Not read";
    case "parse_failed": return "Could not read";
    case "duplicate": return "Already dropped";
    default: return outcome || "Unknown";
  }
}

/** Bytes → the same shape the server's limit copy uses, so the two never disagree by an order of
 *  magnitude in front of the operator. */
export function byteLabel(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * The receipt (§11.1): an outcome line, a coverage block, and a link. Never a command.
 *
 * `notDrafted` is present even when empty, and that is deliberate — a receipt that lists six
 * drafts and says nothing about the rest reads as "six is what was in there".
 */
export function receipt(drop) {
  if (!drop) return null;
  const coverage = drop.coverage || null;
  const notDrafted = [];
  for (const entry of coverage?.skipped || []) {
    notDrafted.push({ key: entry.reason, note: entry.note, chars: entry.chars || 0 });
  }
  for (const entry of coverage?.named_not_proposed || []) {
    notDrafted.push({ key: `named:${entry.value}`, note: `${entry.value} — ${entry.why}`, chars: 0 });
  }
  for (const entry of coverage?.refused || []) {
    notDrafted.push({ key: `refused:${entry.what}`, note: entry.why, chars: 0 });
  }
  return {
    id: drop.id,
    title: drop.filename || "Pasted text",
    kind: kindLabel(drop.detected_kind),
    size: byteLabel(drop.byte_length),
    outcome: drop.outcome,
    outcomeLabel: outcomeLabel(drop.outcome),
    tone: outcomeTone(drop.outcome),
    // Server-authored, or absent. Never assembled here.
    reason: drop.outcome_reason || null,
    drafted: drop.proposals_drafted || 0,
    pending: drop.proposals_pending || 0,
    runId: drop.extraction_run_id || null,
    // §7.4. Set only for a dropped .eml, and its absence on a paste is not an omission — pasted
    // text has no message id, so it has no thread identity and cannot be deduplicated against
    // synced mail. The paste says exactly that in `notDrafted`; this is the other half.
    commMessageId: drop.comm_message_id || null,
    // §12. The pointer to the earlier receipt, resolved server-side. It is what turns "Already
    // dropped" from a dead end into an answer: silent dedupe and a failed upload look identical
    // from the operator's chair, and the difference is whether there is somewhere to go.
    duplicateOf: drop.duplicate_of
      ? {
        id: drop.duplicate_of.id,
        title: drop.duplicate_of.filename || "Pasted text",
        droppedOn: String(drop.duplicate_of.created_at || "").slice(0, 10),
        runId: drop.duplicate_of.extraction_run_id || null,
      }
      : null,
    notDrafted,
    // The empty case still says something, because silence would read as completeness.
    notDraftedEmptyNote: coverage ? "Everything in this document was read." : null,
    readWholeThread: Boolean(coverage?.read_whole_thread),
    otherAccounts: coverage?.other_accounts_mentioned || [],
    snapshotPresent: Boolean(drop.snapshot_present),
    snapshotDeletedAt: drop.snapshot_deleted_at || null,
    createdAt: drop.created_at,
  };
}

/** Newest first within an outcome band, failures band first (§16.3). */
export function orderReceipts(drops) {
  return [...(drops || [])].sort((a, b) => {
    const rank = (OUTCOME_ORDER[a.outcome] ?? 9) - (OUTCOME_ORDER[b.outcome] ?? 9);
    if (rank !== 0) return rank;
    return String(b.created_at || "").localeCompare(String(a.created_at || ""));
  });
}

/**
 * Client-side screening, before a request is made. It exists to make an obvious refusal instant,
 * never to *decide* one: the server screens again and its answer is the one that gets recorded.
 * A client that could accept something the server refuses is the drift this guards against, so
 * every sentence returned here comes from `/api/intake/limits`.
 */
export function screenFile(file, limits) {
  if (!limits) return null;
  const name = String(file?.name || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  if (Number(file?.size || 0) > limits.max_bytes) {
    return { ext, reason: null, tooBig: true };
  }
  if (ext && limits.refusals && limits.refusals[ext]) {
    return { ext, reason: limits.refusals[ext], tooBig: false };
  }
  if (ext && !(limits.accepted_extensions || []).includes(ext)) {
    return { ext, reason: limits.generic_refusal, tooBig: false };
  }
  return null;
}

/** §4.1's per-drop item cap, applied to one drag gesture. Over the cap we take none rather than a
 *  silent prefix: quietly reading 10 of 40 files is the "it worked" that did not. */
export function acceptFileList(files, limits) {
  const list = Array.from(files || []);
  const cap = limits?.max_items_per_drop || 10;
  if (list.length > cap) {
    return { files: [], overflow: { count: list.length, cap } };
  }
  return { files: list, overflow: null };
}

/** §16.2 — the label changes, not just the border. Colour alone is not a compliant state change,
 *  and the label is also what confirms which account will receive the drop. */
export function zoneLabel({ dragging, busy, accountName }) {
  const where = accountName ? ` to ${accountName}` : "";
  if (busy) return "Reading…";
  if (dragging) return `Drop to add${where}`;
  return "Drop a file, or paste a thread";
}

export function zoneHint(limits) {
  if (!limits) return "";
  return `${limits.accepted_summary} Text up to ${limits.max_bytes_label}. ${limits.assurance}`;
}

/** The zone is reachable by Tab and activated by Enter or Space (WCAG 2.5.7 — any function
 *  achieved by dragging must also be achievable without a drag). Dragging is the convenience
 *  layer, never the only path. */
export function isActivationKey(key) {
  return key === "Enter" || key === " " || key === "Spacebar";
}
