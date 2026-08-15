/**
 * Requirement presentation rules (ACCOUNT-PATH-SPEC.md §13.6–§13.8).
 *
 * Pure functions, tested without a DOM like the rest of the frontend rules. Three of them exist
 * specifically to stop a merge the spec forbids:
 *
 * - `requirementAxes` returns four readings and never a combined verdict. State, freshness,
 *   coverage, and applicability are independent (RELATIONSHIP-READINESS-SPEC.md §3.4), so a fresh
 *   component can never make a stale one look current.
 * - `planStatus` speaks only for the plan. A due date is a statement about when something was
 *   expected, never about whether it happened; `overdue` therefore sits beside the state instead
 *   of colouring it.
 * - `requirementControls` enumerates every write the panel offers. There is deliberately no
 *   status control in it: readiness has nothing for one to write to, and adding one would be the
 *   stored second source of truth §2 of the readiness spec forbids.
 *
 * `planVariance` (VISIBILITY-SPEC §6) is the fourth, and it exists to stop a subtraction rather
 * than a merge: two dates may only be differenced when both are planning facts.
 */

export const ESSENTIALS_GAP_CAP = 3;   // §13.6

const STATE = {
  met: { label: "Met", mark: "ok" },
  thin: { label: "Thin", mark: "warn" },
  unknown: { label: "Unknown", mark: "unknown" },
  conflicted: { label: "Conflicted", mark: "conflict" },
  not_applicable: { label: "Not applicable", mark: "na" },
};

const FRESHNESS = {
  current: { label: "Current", mark: "ok" },
  stale: { label: "Stale", mark: "warn" },
  mixed: { label: "Mixed dates", mark: "warn" },
  undated: { label: "Undated", mark: "unknown" },
  not_applicable: { label: "Not applicable", mark: "na" },
};

const APPLICABILITY = {
  required: { label: "Required now", mark: "accent" },
  not_due: { label: "Not due yet", mark: "na" },
  not_applicable: { label: "Not applicable", mark: "na" },
};

const COVERAGE = {
  complete: { label: "Complete", mark: "ok" },
  partial: { label: "Partial", mark: "warn" },
  unavailable: { label: "Unavailable", mark: "unknown" },
};

export const PROVENANCE_LABEL = {
  confirmed_source: "confirmed source",
  operator_recorded: "operator recorded",
  unsupported: "unsupported",
};

function reading(table, value, fallbackLabel) {
  const known = table[value];
  if (known) return { ...known, value, recognized: true };
  // An unrecognised enum reads as unknown and says so, rather than defaulting to the benign end.
  return { label: fallbackLabel, mark: "unknown", value: value ?? null, recognized: false };
}

/**
 * §13.7's third bullet: four separate readings, in a fixed order, each with its own word and
 * shape. Callers render them side by side; there is no function here that reduces them to one.
 */
export function requirementAxes(row, coverage = null) {
  const r = row || {};
  return [
    { axis: "state", title: "State", ...reading(STATE, r.state, "Not evaluated") },
    { axis: "freshness", title: "Freshness", ...reading(FRESHNESS, r.freshness, "No dates") },
    {
      axis: "coverage", title: "Evidence coverage",
      // Coverage is readiness's own claim about how much it could evaluate. It is not derived
      // from the state, so a row with no coverage reported says so instead of borrowing one.
      ...reading(COVERAGE, coverage?.status, "Not reported"),
    },
    {
      axis: "applicability", title: "Applicability",
      ...reading(APPLICABILITY, r.applicability, "Not determined"),
    },
  ];
}

/**
 * §13.6 last bullet. The plan layer's own sentence, kept apart from every readiness axis so an
 * overdue date can never be read as a failing condition — or a met condition as an on-time one.
 */
export function planStatus(row, today) {
  const r = row || {};
  if (!r.playbook) {
    return { scheduled: false, text: "Not scheduled by a playbook", tone: "neutral", due: null };
  }
  const playbook = `${r.playbook.label || r.playbook.key} v${r.playbook.version}`;
  if (!r.due_date) {
    return { scheduled: true, text: `Scheduled by ${playbook}, no due date`, tone: "neutral",
      due: null, playbook };
  }
  const overdue = !!r.overdue;
  const past = today && r.due_date < today;
  return {
    scheduled: true,
    playbook,
    due: r.due_date,
    // A bare date beside a red mark says nothing about what the date *is*. The compact row has no
    // space for the full sentence, so it carries the shortest phrasing that still names the claim
    // as the plan's, not the evaluator's.
    due_label: overdue ? `Overdue · due ${r.due_date}` : `Due ${r.due_date}`,
    tone: overdue ? "risk" : "neutral",
    text: overdue
      ? `Expected by ${r.due_date} — past its planned date`
      : past
        // Met after its date is a fact about timing, not an outstanding item. Saying so keeps the
        // date honest without turning a closed condition back into a chore.
        ? `Expected by ${r.due_date} — evidenced after its planned date`
        : `Expected by ${r.due_date}`,
  };
}

/** The relative rule the date came from, so a re-anchor is legible rather than a mystery edit. */
export function dueRuleText(row) {
  const rule = row?.due_rule;
  if (!rule || rule.offset_days === null || rule.offset_days === undefined) return null;
  const anchor = String(rule.anchor || "anchor").replace(/_/g, " ");
  const n = Math.abs(rule.offset_days);
  if (rule.offset_days === 0) return `On the ${anchor} date`;
  return `${n} day${n === 1 ? "" : "s"} ${rule.offset_days < 0 ? "before" : "after"} the ${anchor} date`;
}

const MS_PER_DAY = 86400000;

/** Parse an ISO date as UTC midnight, so a local timezone cannot shift a planned date by a day. */
function utcDay(iso) {
  if (typeof iso !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function daysBetween(fromIso, toIso) {
  const a = utcDay(fromIso);
  const b = utcDay(toIso);
  if (a === null || b === null) return null;
  return Math.round((b - a) / MS_PER_DAY);
}

function days(n) {
  return `${n} day${n === 1 ? "" : "s"}`;
}

/**
 * Variance between a plan instance's planned date and what actually happened
 * (VISIBILITY-SPEC §6, correcting §2.2).
 *
 * A subtraction is only legal when **both operands are planning facts**. `due_date` is one and
 * `recorded_complete_on` is one, so their difference is one too — that is the `delta` branch, and
 * it is the only branch that subtracts anything.
 *
 * Every other row returns `separate`: the planned date and its age as one statement, and nothing
 * else. The readiness state belongs beside it in readiness's own vocabulary, supplied by the view
 * from the row it already has — this function will not fold the two into "13 days late", because
 * the second operand for that sentence does not exist. `assessed_through` is the date evidence was
 * assessed **through**, not the date a requirement became true; it is never read here, under any
 * label, which is the whole reason §2.2 rejected half of the original proposal.
 *
 * A scheduled row whose anchor never resolved returns `unknown`, for the cross-hatched treatment.
 * The relative rule is deliberately *not* offered as a substitute date there: "2 days after the
 * kickoff date" reads as an answer to "when", and when the kickoff date is unset it is not one.
 */
export function planVariance(row, today = null) {
  const r = row || {};
  const due = r.due_date || null;
  const recorded = r.recorded_complete_on || null;
  const rule = r.due_rule || null;
  const scheduled = !!(rule && rule.anchor);

  if (due && recorded) {
    const delta = daysBetween(due, recorded);
    if (delta !== null) {
      return {
        kind: "delta",
        planned: due,
        recorded,
        days: delta,
        // The age of a planned date stops mattering once the thing was recorded done, and stating
        // both would invite reading them as a pair.
        age: null,
        age_text: null,
        // No tone. A plan item recorded late and one recorded early are the same kind of fact,
        // and late is not a status — colouring this would make the plan layer assert one.
        text: delta === 0
          ? "Recorded complete on the planned date."
          : `Recorded complete ${days(Math.abs(delta))} `
            + `${delta > 0 ? "after" : "before"} the planned date.`,
      };
    }
  }

  if (!due && scheduled) {
    const anchor = String(rule.anchor).replace(/_/g, " ");
    return {
      kind: "unknown",
      planned: null,
      recorded,
      days: null,
      age: null,
      age_text: null,
      text: `No planned date: the ${anchor} date it is measured from is not set.`,
    };
  }

  const age = due && today ? daysBetween(due, today) : null;
  // Arithmetic on one planning date, which is why it can be offered on its own: a surface that
  // already names the planned date renders `age_text` beside it rather than repeating the whole
  // sentence. Neither form ever reaches for a second date to subtract.
  const ageText = age === null ? null
    : age > 0 ? `${days(age)} ago` : age < 0 ? `in ${days(-age)}` : "today";
  return {
    kind: "separate",
    planned: due,
    recorded,
    days: null,
    age,
    age_text: due ? ageText : null,
    // One statement, about the plan and nothing else. The state sits beside it, never inside it.
    text: due ? `Planned for ${due}${ageText ? `, ${ageText}` : ""}` : null,
  };
}

/** A config value as the operand token it will render as. Lists join; nothing is summarised. */
function operand(value) {
  if (Array.isArray(value)) return value.length ? value.map(operand).join(", ") : "none";
  if (value === null || value === undefined) return "none";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * What a requirement definition configured its evaluator with (VISIBILITY-SPEC §7.2).
 *
 * Returns `{ lead, operands: [{ key, label, value }] }` or `null` — the view renders `label` as
 * prose and `value` as a `.mono` token, so an operand always reads as a value rather than as a
 * word in the sentence.
 *
 * This describes the **configuration**, never the evaluator. A per-evaluator English gloss
 * ("checks for two champions with a dated assessment") would be a second statement of what the
 * code does, authored here, free to drift from it — and it would be wrong in exactly the case
 * this exists for, where the evaluator key is not allowlisted and nothing ran at all. Stating
 * `min_count 2` says what was asked for and claims nothing about what happened.
 */
export function evaluatorConfigSentence(row) {
  if (!row?.evaluator_key) return null;
  const version = row.evaluator_version === null || row.evaluator_version === undefined
    ? "" : ` v${row.evaluator_version}`;
  const config = row.evaluator_config;
  const entries = config && typeof config === "object" && !Array.isArray(config)
    ? Object.entries(config) : [];
  return {
    lead: `${row.evaluator_key}${version}`,
    operands: entries.map(([key, value]) => ({
      key,
      label: key.replace(/_/g, " "),
      value: operand(value),
    })),
  };
}

/**
 * §13.6: at most three current-phase gaps, in the order the server ranked them. The client does
 * not re-sort — a second ordering here could disagree with the reasons the rows display.
 */
export function essentialsGaps(requirements, cap = ESSENTIALS_GAP_CAP) {
  const gaps = requirements?.current_phase_gaps || [];
  return { shown: gaps.slice(0, cap), remaining: Math.max(0, gaps.length - cap) };
}

/**
 * Required, unmet conditions whose next step is already a linked native record, in server order.
 *
 * §13.6 keeps these out of the gap list on purpose — the work is the Task's, and listing it twice
 * would double the chore. But the requirement panel is the only surface that can add evidence,
 * link a gate, or archive the link, and the gap list is the only thing that opens it: linking an
 * action would otherwise make the condition unreachable the moment it became tracked. This is the
 * route back. It is a disclosure, not a queue — nothing here is owed to anyone today.
 */
export function trackedRequirements(requirements) {
  return (requirements?.requirements || [])
    .filter((r) => r.linked_action && r.applicability === "required"
      && r.state !== "met" && !r.applicability_override && !r.waiver);
}

/**
 * The requirements a governed decision is currently silencing, in server order.
 *
 * They are deliberately absent from the gap list — a suppressed requirement is not a chore — but
 * §13.6 requires a suppression to be *reported*, and a bare count reports nothing an operator can
 * read or undo. This is the list behind that count, and the only route back to the decision.
 */
export function suppressedRequirements(requirements) {
  return (requirements?.requirements || [])
    .filter((r) => r.applicability_override || r.waiver);
}

/**
 * §13.9: a legacy tick is a planning fact, and the sentence says so outright. It is the one place
 * a checkbox and an evidence state sit together, so it is the one place the difference must be
 * spelled out rather than implied by layout.
 */
export function recordedCompleteNote(row) {
  if (!row?.recorded_complete) return null;
  const on = row.recorded_complete_on ? ` on ${row.recorded_complete_on}` : "";
  const source = row.compatibility_source?.label
    ? ` (${row.compatibility_source.label})` : "";
  const met = row.state === "met";
  return {
    on: row.recorded_complete_on || null,
    text: `Marked complete${on} in the legacy checklist${source}.`,
    caveat: met
      ? "Readiness independently evidences this condition."
      : "That tick is a planning record, not evidence. Readiness still reports the state below.",
    tone: met ? "neutral" : "warn",
  };
}

/**
 * §13.7's last paragraph, expressed as data so a test can assert the absence.
 *
 * Every write this panel offers is a governed flow that records an actor and a reason. Nothing
 * here sets a state: `not_applicable` and `waiver` are decisions *about* a requirement, and
 * `Add evidence` goes to the native record the evaluator reads.
 */
export function requirementControls(row) {
  const r = row || {};
  const live = r.applicability_override || r.waiver;
  return [
    {
      key: "add_evidence",
      label: "Add evidence",
      kind: "navigate",
      writes: "native_record",
      hint: "Opens the record readiness evaluates. Evidence is recorded there, not here.",
    },
    ...(r.create_action_prefill ? [{
      key: "create_action",
      label: "Create action",
      kind: "create",
      writes: "native_record",
      hint: r.create_action_prefill.link_note,
    }] : []),
    ...(live ? [{
      key: "revoke_exception",
      label: r.waiver ? "Revoke waiver" : "Revoke not applicable",
      kind: "governed",
      writes: "exception",
      hint: "Records a revocation with a reason. The prior decision stays in the history.",
    }] : [{
      key: "mark_not_applicable",
      label: "Mark not applicable",
      kind: "governed",
      writes: "exception",
      hint: "Records who decided and why. It suppresses the requirement without changing any "
        + "evidence or state.",
    }]),
  ];
}

/** No control may write a readiness state; the panel asserts this rather than trusting review. */
export function controlsWriteNoState(row) {
  return requirementControls(row).every((c) => c.writes !== "state" && c.kind !== "status");
}

/** The statuses `playbooks._exception_status` emits. Anything else is a drift, not a state. */
export const EXCEPTION_STATUS_LABEL = {
  live: "In force",
  revoked: "Revoked",
  lapsed: "Lapsed",
};

/** §13.7 — the decision trail, newest first, keeping revoked and lapsed rows readable. */
export function exceptionHistoryRows(history) {
  return [...(history || [])].sort((a, b) => String(b.decided_on || "")
    .localeCompare(String(a.decided_on || ""))).map((h) => ({
    ...h,
    kindLabel: h.kind === "waiver" ? "Waiver" : "Not applicable",
    // The vocabulary is the server's — `playbooks._exception_status` emits live/revoked/lapsed.
    // Inventing a second one here is how a live waiver reads as unrecognized and loses its revoke
    // control while still suppressing the requirement.
    statusLabel: EXCEPTION_STATUS_LABEL[h.status] || "Status not recognized",
    // An expiry that has passed is a lapse, not a live suppression. Rendering it as in force would
    // let a temporary decision quietly become permanent — and an unknown status is never live, so
    // a vocabulary drift shows up as a missing revoke control rather than a phantom suppression.
    live: h.status === "live",
  }));
}

/**
 * §13.7 — the linked native record, so the panel never invents a link that is absent.
 *
 * The server ships `{type, id, description}` and no `native_target`: this link is an index entry
 * for the §13.6 dedupe, not a queue row. Reading `record_type` and `label` off it — the shape
 * Slice 3 assumed before Slice 5 stored these — yields a row that says "record", shows no title,
 * and opens nothing, which is worse than showing no row at all. The target is built here from the
 * two fields that do arrive.
 */
const LINK_TARGET_TAB = { task: "ledger", commitment: "ledger" };

export function linkedRecords(row) {
  const link = row?.linked_action;
  if (!link) return [];
  const kind = link.type || link.record_type;
  const id = link.id || link.record_id;
  const tab = LINK_TARGET_TAB[kind];
  return [{
    ...link,
    kindLabel: (kind || "record").replace(/_/g, " "),
    label: link.description || link.label || id || "Linked record",
    // An unrecognized kind has no tab to open, and a button that navigates nowhere is a worse
    // answer than a plain line of text. The caller renders one or the other on this being null.
    native_target: tab ? { tab, record_type: kind, record_id: id } : null,
  }];
}
