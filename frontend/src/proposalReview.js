/**
 * Review-surface rules for one proposal (ACCOUNT-PATH-SPEC.md §14.5, RR-2 §6.7).
 *
 * Pure functions, tested without a DOM. They exist so the decision surface reads the RR-2 store
 * the way the store is actually shaped, and so three specific mistakes are impossible:
 *
 * - **Keyed on `(intent, target_type)`, never on `mutation_type`.** The legacy enum fused verb and
 *   noun, so a UI reading it can only ever describe creations. "Change to person: Robin Vale" is a
 *   different sentence from "New person", and only the pair can say which one this is.
 * - **`accept` and `edit_and_accept` are the same endpoint and must not look like the same act.**
 *   Whether the operator edited the draft is knowable here — the label changes to say so, rather
 *   than letting an edited payload be applied under the word the reviewer read as "as drafted".
 * - **A command is offered only when it can succeed.** Every disabled command carries the reason
 *   it is disabled, because a dead button with no explanation reads as a broken app and pushes the
 *   operator to guess.
 *
 * Nothing here writes, and nothing here decides *for* the reviewer: no resolution is preselected,
 * no confidence value ranks anything, and a conflicted proposal is stopped rather than merged.
 */

export const MOMENT_TYPES = [
  "talent_calendar", "manager_workflow", "business_event", "proactive_coaching", "comms_campaign",
];

// Targets that write against the account. Everything else is program-scoped and cannot be applied
// until a program is chosen — the backend 422s, so the surface says so first.
const ACCOUNT_SCOPED_TARGETS = new Set(["person", "pull_signal", "value_story"]);

// What the operator must supply before the native create/patch path will accept the payload. These
// mirror the server-side schemas; the server still validates, and a mismatch surfaces as its 422.
const REQUIRED_FIELDS = {
  "create:commitment": [
    { key: "responsible_party_id", label: "Responsible party", control: "person" },
    { key: "internal_owner_id", label: "Internal owner", control: "internal_person" },
    { key: "due_date", label: "Due date", control: "date" },
  ],
  "update:person": [{ key: "name", label: "Name", control: "text" }],
  // ACCOUNT-INTAKE-SPEC.md §10. Required here even though the extractor can only ever draft a
  // milestone that already has one — a dateless milestone is reported in coverage and never
  // becomes a proposal. The field is required because the *reviewer* can clear it, and a milestone
  // with no date is a plan entry the rest of the app cannot plan against.
  "create:milestone": [{ key: "target_date", label: "Target date", control: "date" }],
};

// Fields the reviewer may change before applying, beyond the pair's text field and its required
// ones. `update:person` edits the identity fields instead, because that is what it is proposing.
const OPTIONAL_FIELDS = {
  "update:person": [{ key: "title", label: "Title", control: "text" }],
  "create:deployment_moment": [
    { key: "moment_type", label: "Moment type", control: "select", options: MOMENT_TYPES },
  ],
};

const DEFAULT_TEXT_FIELD = { key: "description", label: "Description", control: "textarea" };

// The drafted sentence is `description` for most targets, but the native column does not always
// agree — and the form has to edit the key the server will read, or an edit silently applies
// nothing. `null` means this pair has no free-text field at all.
const TEXT_FIELD = {
  "update:person": null,
  "create:milestone": { key: "name", label: "Milestone", control: "text" },
};

export function pairKey(proposal) {
  return `${proposal?.intent || "create"}:${proposal?.target_type || ""}`;
}

/** Does applying this proposal need a program chosen? */
export function needsProgram(proposal) {
  return !ACCOUNT_SCOPED_TARGETS.has(proposal?.target_type);
}

/**
 * The fields this proposal's review form shows, required ones first. An `update` shows only the
 * fields its target allows to be changed — offering `description` on a placeholder fill would
 * invite an edit the server will refuse.
 */
export function editableFields(proposal) {
  const key = pairKey(proposal);
  const required = (REQUIRED_FIELDS[key] || []).map((f) => ({ ...f, required: true }));
  const optional = (OPTIONAL_FIELDS[key] || []).map((f) => ({ ...f, required: false }));
  const field = key in TEXT_FIELD ? TEXT_FIELD[key] : DEFAULT_TEXT_FIELD;
  const text = field ? [{ ...field, required: false }] : [];
  return [...required, ...text, ...optional];
}

/** The form's starting values: what the source drafted, never a guess of our own. */
export function draftFrom(proposal) {
  const payload = proposal?.payload || {};
  const draft = {};
  for (const field of editableFields(proposal)) {
    const value = payload[field.key];
    draft[field.key] = value === null || value === undefined ? "" : String(value);
  }
  return draft;
}

/** Required fields still empty, by label — the reason `accept` is unavailable. */
export function missingRequired(proposal, draft = {}) {
  return editableFields(proposal)
    .filter((f) => f.required && !String(draft[f.key] ?? "").trim())
    .map((f) => f.label);
}

/** True when the reviewer changed what the source said. Drives the accept vs edit-and-accept label. */
export function isEdited(proposal, draft = {}) {
  const payload = proposal?.payload || {};
  return editableFields(proposal).some((f) => {
    const original = payload[f.key];
    const before = original === null || original === undefined ? "" : String(original);
    return String(draft[f.key] ?? "").trim() !== before.trim();
  });
}

/**
 * The `overrides` body for accept. Empty optional fields are omitted rather than sent as "" — an
 * empty string is a value, and sending one would overwrite a drafted field with nothing.
 */
export function overridesFrom(proposal, draft = {}, { programId = null } = {}) {
  const payload = proposal?.payload || {};
  const overrides = {};
  for (const field of editableFields(proposal)) {
    const value = String(draft[field.key] ?? "").trim();
    if (!value) continue;
    const original = payload[field.key];
    const before = original === null || original === undefined ? "" : String(original).trim();
    if (field.required || value !== before) overrides[field.key] = value;
  }
  if (programId && needsProgram(proposal)) overrides.program_id = programId;
  return overrides;
}

/** The conflict preview in one sentence, or null when the target has not moved. */
export function conflictNote(conflict) {
  if (!conflict || !conflict.stale) return null;
  if (conflict.missing) return "The record this proposal updates no longer exists.";
  const changed = changedFields(conflict).map((f) => f.field).join(", ");
  return `The record changed after this was drafted${changed ? ` (${changed})` : ""}. `
    + "Applying now would overwrite the newer edit — re-read it first.";
}

/** Only the fields whose current value differs from what the proposal would write. */
export function changedFields(conflict) {
  return (conflict?.fields || []).filter((f) => f.changed);
}

/**
 * The commands to render, in the order §6.7 lists them. Each carries whether it can run now and
 * why not. `open_source` is always available: a reviewer who cannot see the source cannot review.
 */
export function commandsFor(proposal, {
  programId = null, draft = {}, rejectReason = "", chosenExistingId = null,
  supersedeById = null, conflict = null, pending = false, siblings = [],
} = {}) {
  const open = proposal?.status === "proposed";
  const missing = missingRequired(proposal, draft);
  const edited = isEdited(proposal, draft);
  const programMissing = needsProgram(proposal) && !programId && !proposal?.program_id;
  const stale = Boolean(conflict?.stale);

  const why = (...reasons) => reasons.filter(Boolean)[0] || null;
  const closed = open ? null : `Already ${String(proposal?.status || "").replaceAll("_", " ")}`;
  const busy = pending ? "Working…" : null;

  const acceptWhy = why(closed, busy,
    stale ? "The record changed since this was drafted" : null,
    programMissing ? "Choose a program first" : null,
    missing.length ? `Needs ${missing.join(", ")}` : null);

  return [
    {
      key: edited ? "edit_and_accept" : "accept",
      label: edited ? "Apply my edits" : "Accept as drafted",
      enabled: !acceptWhy,
      why: acceptWhy,
    },
    {
      key: "reject",
      label: "Reject",
      enabled: !closed && !pending && String(rejectReason).trim().length >= 3,
      why: why(closed, busy, "Give a reason — the next reviewer reads it, not the proposal"),
    },
    {
      key: "use_existing",
      label: "Use existing record",
      enabled: !closed && !pending && Boolean(chosenExistingId),
      why: why(closed, busy, "Pick the record that already holds this"),
    },
    {
      key: "supersede",
      label: "Supersede",
      enabled: !closed && !pending && Boolean(supersedeById) && siblings.length > 0,
      why: why(closed, busy,
        siblings.length ? "Pick the newer proposal that replaces this one"
                        : "No other proposal covers this material"),
    },
    { key: "open_source", label: "Open source", enabled: true, why: null },
  ];
}

/**
 * Proposals from the same run that could replace this one: same target, still open, not itself.
 * Superseding across target types would close a commitment against a risk.
 */
export function supersedeCandidates(proposal, runProposals = []) {
  return runProposals.filter(
    (p) => p.id !== proposal?.id && p.status === "proposed"
      && p.target_type === proposal?.target_type,
  );
}

/**
 * Whether one run's drafts can all be applied in a single act — ACCOUNT-INTAKE-SPEC.md §11.4, D-208.
 *
 * §11.4 names three guards: every item `proposed`, no conflict, no match candidate. A fourth is
 * unavoidable — a proposal missing a required field 422s on accept, and a batch that discovered
 * that halfway through would have created records nobody chose to create. So the rule is
 * all-or-nothing, computed over the *open* items only.
 *
 * **Open, not every item.** A run whose sixth draft was rejected last week still has five that can
 * be applied together; reading "every item `proposed`" as including resolved ones would disable
 * accept-all permanently after a single rejection, which is a rule that punishes reviewing.
 *
 * This is the UX half. The server recomputes all of it and refuses the whole call on one
 * ineligible item — a stale tab or a second reviewer produces a client that thinks a batch is
 * clean when it is not, so the button is a prediction and the endpoint is the answer.
 */
export function acceptAllState(proposals = [], { programId = null, pending = false } = {}) {
  const open = proposals.filter((p) => p?.status === "proposed");
  const blocked = [];
  for (const p of open) {
    const why = acceptAllBlocker(p, programId);
    if (why) blocked.push({ id: p.id, targetType: p.target_type, why });
  }
  const count = open.length;
  let why = null;
  if (pending) why = "Working…";
  else if (!count) why = "Nothing open in this source";
  else if (blocked.length) {
    why = `${blocked.length} of these ${count} needs a decision of its own — review them one at a time`;
  }
  return {
    count,
    blocked,
    enabled: !why,
    why,
    label: count ? `Accept all ${count}` : "Accept all",
  };
}

/** Why one proposal cannot ride in a batch, or null. Mirrors the server's dry run of accept. */
export function acceptAllBlocker(proposal, programId = null) {
  if (proposal?.status !== "proposed") return `already ${String(proposal?.status || "").replaceAll("_", " ")}`;
  if (proposal?.conflict?.stale) return "the record changed after this was drafted";
  // A match candidate means "this may already exist". Whether to create a second record or close
  // against the existing one is the reviewer's judgement — exactly the judgement a bulk key skips.
  if ((proposal?.match_candidates || []).length) return "a record here may already hold this";
  if (needsProgram(proposal) && !programId && !proposal?.program_id) return "it needs a program";
  const missing = missingRequired(proposal, draftFrom(proposal));
  if (missing.length) return `it needs ${missing.join(", ")}`;
  return null;
}

/** What the source was, in the words of the record — never re-derived or prettied up. */
export function sourceFacts(proposal, source = null) {
  const s = proposal?.source || {};
  const facts = [
    ["Kind", String(source?.kind || s.kind || "unknown").replaceAll("_", " ")],
    ["Provider", source?.provider || null],
    ["Message / reference", s.external_id || source?.external_id || null],
    ["Content hash", s.content_hash || source?.content_hash || null],
    ["Locator", s.locator || null],
    ["Extractor", source?.extractor
      ? `${source.extractor.backend} · ${source.extractor.model_version} · ${source.extractor.prompt_version}`
      : null],
  ];
  return facts.filter(([, value]) => value).map(([label, value]) => ({ label, value }));
}

/** The closing sentence on a resolved proposal — what happened, not what could happen. */
export function outcomeLine(proposal) {
  const status = proposal?.status;
  if (status === "proposed") return null;
  const target = proposal?.resolved_target;
  if (status === "accepted") {
    return `Applied — created the ${String(target?.type || "record").replaceAll("_", " ")}.`;
  }
  if (status === "resolved_existing") {
    return `Closed against the ${String(target?.type || "record").replaceAll("_", " ")} that already held this.`;
  }
  if (status === "rejected") {
    return proposal?.rejection_reason
      ? `Rejected — ${proposal.rejection_reason}`
      : "Rejected.";
  }
  if (status === "superseded") return "Superseded by a newer proposal over the same material.";
  return String(status).replaceAll("_", " ");
}
