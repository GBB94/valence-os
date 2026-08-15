/**
 * Shared plan presentation rules (ACCOUNT-PATH-SPEC.md §16.5).
 *
 * Pure functions, so the sentences an operator reads before sending something to a customer are
 * testable without a DOM. Three rules shape everything here:
 *
 * - **Nothing is derived from the records.** The artifact arrives already projected; this file
 *   maps the server's five status words onto a label and a shape and stops. A client that
 *   recomputed a status could disagree with the markdown sitting beside it, and §16.7 makes
 *   preview-equals-export a contract rather than a convention.
 * - **The operator's view and the customer's view are different documents.** `diagnostics` never
 *   reaches the rendered plan; it exists so an empty plan is distinguishable from a plan somebody
 *   forgot to promote into. `unsharedSummary` and `withheldSummary` are operator sentences.
 * - **A withheld item says why.** The reason comes from the server verbatim. Guessing at a
 *   friendlier one here would restate a judgment the projection deliberately refused to make.
 */

/** The five words §16.3 allows a client-facing status to be, and nothing else. */
const STATUS = {
  complete: { label: "Complete", mark: "ok", symbol: "✓" },
  in_progress: { label: "In progress", mark: "warn", symbol: "◦" },
  blocked: { label: "Blocked", mark: "risk", symbol: "▲" },
  not_started: { label: "Not started", mark: "neutral", symbol: "·" },
  not_applicable: { label: "Not applicable", mark: "na", symbol: "–" },
};

/**
 * A status word, rendered. An unrecognized word is shown as itself with the unknown treatment
 * rather than quietly mapped onto a neighbour — a build that does not know a status must not make
 * it look settled.
 */
export function statusChip(status) {
  return STATUS[status] || { label: String(status || "Unknown"), mark: "unknown", symbol: "?" };
}

/** True when the plan carries nothing a customer could read. */
export function isEmptyPlan(artifact) {
  const a = artifact || {};
  return !(a.programs || []).length
    && !(a.account_requirements || []).length
    && !(a.growth_lines || []).length
    && !(a.pre_agreed_triggers || []).length;
}

/** The one-line stamp under the title: what the plan covers and how current it is. */
export function stampLine(artifact) {
  const a = artifact || {};
  const stamp = a.stamp || {};
  const summary = a.summary || {};
  const parts = [];
  if (stamp.data_current_through) parts.push(`Current through ${stamp.data_current_through}`);
  parts.push(count(summary.shared_items || 0, "shared item"));
  if (summary.milestones_shared) {
    parts.push(`${summary.milestones_complete || 0} of ${summary.milestones_shared} milestones complete`);
  }
  // `next_milestone` is the projected milestone object, not a string — it carries the target date
  // the operator needs beside the name.
  const next = summary.next_milestone;
  if (next?.name) {
    parts.push(`Next: ${next.name}${next.target_date ? ` (${next.target_date})` : ""}`);
  }
  return parts.join(" · ");
}

/**
 * Missing or stale sources, said plainly. This is the one warning that belongs on the customer's
 * side of the page: a plan assembled from a source we could not read is not a complete plan, and
 * §16.6 requires the artifact to carry that.
 */
export function staleSourceNote(artifact) {
  const missing = ((artifact || {}).stamp || {}).missing_or_stale_sources || [];
  if (!missing.length) return null;
  return `${count(missing.length, "source")} behind this plan ${missing.length === 1 ? "is" : "are"} `
    + `missing or past its freshness window: ${missing.join(", ")}.`;
}

/**
 * The operator's nudge. Counts of native work that exists and is not on the plan, so "nothing is
 * shared" and "nothing exists" read differently. Returns null when there is nothing to say.
 */
export function unsharedSummary(diagnostics) {
  const counts = (diagnostics || {}).unshared_counts || {};
  const parts = [];
  for (const [key, noun] of [["milestones", "milestone"], ["commitments", "commitment"],
    ["tasks", "task"], ["requirements", "requirement"]]) {
    if (counts[key]) parts.push(count(counts[key], noun));
  }
  if (!parts.length) return null;
  return `${joinList(parts)} not on this plan.`;
}

/**
 * Items promoted but held back, grouped by the server's reason. An operator who promoted something
 * and cannot find it on the plan needs the reason, not a second copy of the item.
 */
export function withheldSummary(diagnostics) {
  const withheld = (diagnostics || {}).withheld || [];
  const byReason = new Map();
  for (const item of withheld) {
    const reason = item.reason || "no reason given";
    if (!byReason.has(reason)) byReason.set(reason, []);
    byReason.get(reason).push(item);
  }
  return [...byReason.entries()].map(([reason, items]) => ({
    reason, items, key: reason,
  }));
}

/**
 * The one sentence a withheld item gets.
 *
 * The server authors each reason as a lower-case clause that completes this frame, and the frame
 * lives here rather than in the view so a test can hold it to that. Adding a word of our own — even
 * a linking "it" — is how a refusal we did not write starts getting paraphrased.
 */
export function withheldSentence(reason) {
  return `Held back because ${reason}.`;
}

/** Manifest counts by record type, for the source stamp under a saved artifact. */
export function manifestSummary(diagnostics) {
  const manifest = (diagnostics || {}).source_manifest || [];
  const byType = new Map();
  for (const row of manifest) byType.set(row.type, (byType.get(row.type) || 0) + 1);
  return [...byType.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([type, n]) => ({ type, n, label: count(n, type.replace(/_/g, " ")) }));
}

/**
 * Whether a promotion preview is safe to confirm. The server already refused or allowed; this only
 * reads its answer, so a preview that says "withheld" cannot be confirmed past a green button.
 */
export function previewVerdict(preview) {
  const p = preview || {};
  if (p.withheld_reason) {
    return { ok: false, label: "Would be withheld", mark: "warn", detail: p.withheld_reason };
  }
  if (!p.what) {
    return { ok: false, label: "Nothing to show", mark: "unknown",
      detail: "The projection returned no client-safe content for this record." };
  }
  return { ok: true, label: "Would appear as", mark: "ok", detail: null };
}

function count(n, noun) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function joinList(parts) {
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}
