/**
 * Account Path presentation logic (ACCOUNT-PATH-SPEC.md §6, §11).
 *
 * Pure functions only, so the rules that decide what an operator reads — the primary button
 * label, the urgency sentence, lane order, the caps — are testable without a DOM. The repo's
 * frontend tests are `node --test` over plain modules; the JSX in `views/AccountPath.jsx`
 * consumes these and adds no rules of its own.
 *
 * Nothing here ranks. Order arrives from the server already sorted by band (§10.5); a second
 * ranking implementation in the client could disagree with the one the reason text explains.
 */

export const GROUP_CAP = 5;        // §11.5 rows per execution group
export const LANE_CAP = 3;         // §6.3 program lanes before "View all programs"
export const UPCOMING_CAP = 3;     // §11.5 upcoming gates and dates
export const SUPPLEMENT_CAP = 3;   // §11.5 essentials shown before "View all"

/**
 * §6.2 display states. Each carries a word and a shape as well as a colour class, because no
 * state may be conveyed by colour alone (DESIGN-GUIDE.md).
 */
const PHASE_STATE = {
  complete: { label: "Complete", mark: "ok", symbol: "✓" },
  current: { label: "Current", mark: "accent", symbol: "◆" },
  future: { label: "Not started", mark: "future", symbol: "○" },
  blocked: { label: "Blocked", mark: "risk", symbol: "▲" },
  waived: { label: "Waived", mark: "neutral", symbol: "—" },
  not_applicable: { label: "Not applicable", mark: "na", symbol: "—" },
  unknown: { label: "Unknown", mark: "unknown", symbol: "?" },
};

/**
 * An enum value this build does not know renders as `Unknown` and reports itself, rather than
 * being treated as complete or dropped (§10.2). A silently ignored state would read as progress.
 */
export function phaseState(state) {
  const known = PHASE_STATE[state];
  if (known) return { ...known, recognized: true };
  return { ...PHASE_STATE.unknown, recognized: false };
}

const PRIMARY_ACTION = {
  task: "Open task",
  commitment: "Follow up",
  risk: "Resolve blocker",
  issue: "Resolve blocker",
  milestone: "Prepare",
  deployment_moment: "Prepare",
  phase_gate_item: "Open requirement",
  checklist_item: "Open requirement",
  contract_version: "Open contract",
  interaction: "Open interaction",
};

/** §11.4: the primary button names the object, so its destination is predictable before clicking. */
export function primaryActionLabel(candidate) {
  return PRIMARY_ACTION[candidate?.source_type] || "Open record";
}

const WEEKDAY = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(isoDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(isoDate || ""));
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

/** Whole days between two `YYYY-MM-DD` dates. Calendar days, never elapsed hours. */
export function dayDelta(fromDate, toDate) {
  const a = parts(fromDate);
  const b = parts(toDate);
  if (!a || !b) return null;
  return Math.round((Date.UTC(...[b[0], b[1] - 1, b[2]]) - Date.UTC(...[a[0], a[1] - 1, a[2]]))
    / 86400000);
}

/**
 * §11.6 urgency language. Direct and specific: a count of days, a weekday, or a date — never a
 * bare `At risk`, and never a neutral-sounding phrase for a missing date.
 */
export function urgencyLabel(candidate, today) {
  const due = candidate?.due_date;
  if (!due) return { text: "No due date", tone: "neutral" };
  const delta = dayDelta(today, due);
  if (delta === null) return { text: "No due date", tone: "neutral" };
  if (delta < 0) {
    const days = Math.abs(delta);
    return { text: `${days} day${days === 1 ? "" : "s"} overdue`, tone: "risk" };
  }
  if (delta === 0) return { text: "Due today", tone: "risk" };
  if (delta === 1) return { text: "Due tomorrow", tone: "warn" };
  const [y, m, d] = parts(due);
  if (delta <= 6) {
    return { text: `Due ${WEEKDAY[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}`, tone: "warn" };
  }
  return { text: `Due ${MONTH[m - 1]} ${d}`, tone: "neutral" };
}

/** Owner and responsible party are rendered as explicit facts when absent, never omitted (§6.1). */
export function ownerLabel(candidate) {
  return candidate?.owner?.name || "Unassigned";
}

export function waitingLabel(candidate) {
  const name = candidate?.responsible_party?.name;
  return name ? `Waiting on ${name}` : "Waiting on the customer";
}

/**
 * §6.3 lane order: nearest blocked or at-risk state first, then target date, then name. An
 * account with several programs gets one lane each and never a fabricated aggregate phase.
 */
export function laneOrder(programPaths) {
  return [...(programPaths || [])].sort((a, b) => {
    const urgent = (lane) => (lane.steps || []).some((s) => s.state === "blocked")
      || !!lane.next_milestone?.at_risk;
    if (urgent(a) !== urgent(b)) return urgent(a) ? -1 : 1;
    const date = (lane) => lane.next_milestone?.target_date || "9999-12-31";
    if (date(a) !== date(b)) return date(a) < date(b) ? -1 : 1;
    return String(a.program_name || "").localeCompare(String(b.program_name || ""));
  });
}

/** A cap is a presentation choice, so the count left behind is always reported alongside it. */
export function capped(items, cap) {
  const all = items || [];
  return { shown: all.slice(0, cap), remaining: Math.max(0, all.length - cap) };
}

/** §11.5: the promoted next move is not repeated in You own. */
export function withoutNextMove(items, nextMove) {
  if (!nextMove) return items || [];
  return (items || []).filter((item) => item.id !== nextMove.id);
}

const EMPTY_STATE_COPY = {
  waiting_on_customer: {
    title: "Waiting on the customer",
    action: null,
  },
  prepare_for_next_gate: {
    title: "Prepare for the next gate",
    action: null,
  },
  caught_up: {
    title: "Account is caught up",
    action: null,
  },
  coverage_incomplete: {
    title: "Coverage is incomplete",
    action: null,
  },
  insufficient_plan_data: {
    title: "Insufficient plan data",
    action: { label: "Open Plan", tab: "plan" },
  },
};

/**
 * §6.1 requires one of these explicit states rather than an empty panel. The server supplies the
 * variant and the sentence; the client supplies only the heading and any navigation affordance,
 * so the two can never disagree about which state is showing.
 */
export function emptyStateCopy(emptyState) {
  if (!emptyState) return null;
  const known = EMPTY_STATE_COPY[emptyState.variant];
  return {
    title: known ? known.title : "Nothing selected",
    message: emptyState.message || "",
    action: known ? known.action : null,
    requirement: emptyState.requirement || null,
    recognized: !!known,
  };
}

/**
 * §11.10: partial coverage is named and can never present as caught up. Readiness reports its own
 * coverage inside its own card, so this notice speaks only for the execution sources.
 *
 * A complete read can still be *subtractive*: a snoozed row is withheld from a response the server
 * calls complete, and it says so in `coverage.warnings`. Returning null there dropped the only
 * statement that anything was hidden, which is the suppression rule of Slice 3 read backwards —
 * a suppression is always reported. A withheld row and an unreadable source are different claims,
 * so the notice carries `status` and the view tones them differently rather than sharing a callout.
 */
export function coverageNotice(coverage) {
  if (!coverage) return null;
  const warnings = coverage.warnings || [];
  if (coverage.status === "complete") {
    return warnings.length ? { status: "complete", message: null, warnings } : null;
  }
  const sources = (coverage.omitted_sources || []).map((entry) => entry.source).join(", ");
  return {
    status: coverage.status,
    message: coverage.status === "unavailable"
      ? "No execution source could be read, so nothing here can be treated as complete."
      : `Partial coverage: ${sources || "some sources"} could not be read. Items from them are missing.`,
    warnings,
  };
}

/** §6.5 source labels. Distinct from readiness `provenance`, which describes evidence quality. */
export function sourceLabel(provenance) {
  return provenance?.label || null;
}

/** A blocked phase always names its reason; a state word with no reason is the §11.6 failure. */
export function phaseAria(step) {
  const state = phaseState(step.state);
  const base = `${step.label}: ${state.label}`;
  if (step.blocking_reason) return `${base} — ${step.blocking_reason}`;
  if (step.state === "current" && step.missing_count > 0) {
    return `${base}, ${step.missing_count} gate item${step.missing_count === 1 ? "" : "s"} incomplete`;
  }
  return base;
}
