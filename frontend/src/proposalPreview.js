/**
 * Proposal preview and combined-review presentation rules
 * (RELATIONSHIP-READINESS-SPEC.md §8.1–§8.3).
 *
 * Pure functions, tested without a DOM like the rest of the frontend rules. Three of them exist to
 * stop a specific misreading:
 *
 * - `previewCards` caps the Overview at three and reports what it left out. Three cards over a
 *   backlog of thirty would read as three items of work.
 * - `combinedReviewRows` interleaves machine proposals and hand-typed notes into one list while
 *   keeping each row's own kind, status word, and command set. §0.5 allows the combined
 *   experience and forbids the merge; flattening the vocabularies is the merge, in the UI instead
 *   of the schema.
 * - `proposalMarks` returns proposed-and-cited signals, never asserted ones. A proposal has no
 *   status colour of its own, because it is not a state of the account — it is a draft awaiting a
 *   person.
 */

export const PREVIEW_CAP = 3;   // §8.1 — "up to three proposals from the latest interaction"

const TARGET_LABEL = {
  task: "task", commitment: "commitment", risk: "risk", issue: "issue", decision: "decision",
  person: "person", pull_signal: "pull signal", deployment_moment: "deployment moment",
  value_story: "value story", milestone: "milestone",
};

const INTENT_LABEL = { create: "New", update: "Change to", link: "Link", close: "Close",
                       no_change: "No change to" };

// Deliberately not a status ramp, and deliberately not the accent either. Green/amber/red are
// reserved for account status and a proposal has none; the accent is reserved for interaction, and
// "Proposed" is a condition of the draft rather than something to click. Both marks are neutral
// shapes distinguished by outline, and both always carry a word.
const KIND_MARK = { extraction_proposal: "draft", capture_item: "quiet" };

export function targetLabel(targetType) {
  return TARGET_LABEL[targetType] || String(targetType || "record").replaceAll("_", " ");
}

export function proposalTitle(proposal) {
  const payload = proposal?.payload || {};
  const text = payload.description || payload.name || payload.outcome || "";
  const intent = INTENT_LABEL[proposal?.intent] || "Proposed";
  return `${intent} ${targetLabel(proposal?.target_type)}: ${text}`.trim();
}

/**
 * The marks one proposal renders with. Every one pairs its colour with a word, and `cited` is
 * always present: a proposal card that does not show its source span looks asserted.
 */
export function proposalMarks(proposal) {
  const marks = [{ key: "kind", mark: KIND_MARK.extraction_proposal, label: "Proposed" }];
  if (proposal?.source?.span) marks.push({ key: "cited", mark: "quiet", label: "Cited" });
  if (proposal?.conflict?.stale) {
    marks.push({ key: "conflict", mark: "warn", label: "Record changed since drafted" });
  }
  const candidates = proposal?.match_candidates || [];
  if (candidates.length) {
    marks.push({ key: "candidates", mark: "quiet",
                 label: `${candidates.length} possible match${candidates.length === 1 ? "" : "es"}` });
  }
  const warnings = proposal?.validation_warnings || [];
  if (warnings.length) {
    marks.push({ key: "warnings", mark: "warn",
                 label: `${warnings.length} warning${warnings.length === 1 ? "" : "s"}` });
  }
  return marks;
}

/**
 * §8.1's Overview card. `hiddenCount` counts the whole scope, not the rest of this run, so the
 * link never understates the backlog behind it.
 */
export function previewCards(preview, cap = PREVIEW_CAP) {
  const proposals = (preview?.proposals || []).slice(0, Math.max(0, cap));
  const pending = preview?.pending_count || 0;
  return {
    cards: proposals.map((p) => ({
      id: p.id,
      title: proposalTitle(p),
      span: p.source?.span || null,
      marks: proposalMarks(p),
    })),
    pending,
    hiddenCount: Math.max(0, pending - proposals.length),
    source: preview?.latest_source || null,
    // Nothing to review is a real answer and gets said plainly rather than rendered as a zero.
    empty: pending === 0,
  };
}

/**
 * One review list from two stores. Each row keeps its own `kind`, its own status word, and its own
 * commands — an `untriaged` note never becomes `proposed`, and a proposal never offers "convert".
 */
export function combinedReviewRows(payload) {
  const rows = [];
  for (const group of payload?.groups || []) {
    for (const target of group.targets || []) {
      for (const proposal of target.proposals || []) {
        rows.push({
          kind: "extraction_proposal",
          id: proposal.id,
          title: proposalTitle(proposal),
          status: proposal.status,
          statusLabel: proposal.status.replaceAll("_", " "),
          commands: ["accept", "edit_and_accept", "reject", "use_existing", "supersede"],
          source: group.source,
          span: proposal.source?.span || null,
          marks: proposalMarks(proposal),
          createdAt: proposal.created_at,
          raw: proposal,
        });
      }
    }
  }
  for (const item of payload?.manual_capture || []) {
    rows.push({
      kind: "capture_item",
      id: item.id,
      title: item.text,
      status: item.status,
      statusLabel: item.status,
      commands: item.commands || ["convert", "dismiss"],
      source: null,
      span: null,
      // A hand-typed note is not cited and must not be dressed as though it were.
      marks: [{ key: "kind", mark: KIND_MARK.capture_item, label: "Your note" }],
      createdAt: item.created_at,
      raw: item,
    });
  }
  rows.sort((a, b) => String(b.createdAt || "").localeCompare(String(a.createdAt || "")));
  return rows;
}

/** The one-line source attribution under a group heading. */
export function sourceLabel(source) {
  if (!source) return "Unknown source";
  const kind = String(source.kind || "source").replaceAll("_", " ");
  const when = source.interaction?.occurred_on || (source.created_at || "").slice(0, 10);
  const by = source.extractor?.backend ? ` · ${source.extractor.backend} extractor` : "";
  return `${kind}${when ? ` · ${when}` : ""}${by}`;
}
