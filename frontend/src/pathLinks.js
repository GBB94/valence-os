/**
 * Account Path Slice 5 presentation rules (ACCOUNT-PATH-SPEC.md §15.8).
 *
 * Pure functions, like the rest of the frontend rules, so the sentences an operator acts on are
 * testable without a DOM. Four of them exist specifically to stop a claim the spec forbids:
 *
 * - `advancementVerdict` reads the server's `readiness` word and never computes one. `Blocked` and
 *   `Evidence missing` are different answers — the first says the records were read and came back
 *   unsatisfied, the second says something could not be read at all — and collapsing them would be
 *   the carried-forward-good-state failure in reverse.
 * - `overrideConsequences` enumerates what an override does and does not do. An override moves the
 *   phase; it does not fill a gap, does not pass the gate, and does not change a readiness state.
 * - `dependencyLines` draws a line only from an accepted explicit relation. There is deliberately
 *   no inference from a shared date, owner, or matching text (§15.2).
 * - `unblocksReason` returns a sentence only when an explicit gate relation supports it, so an
 *   action's detail can say `Unblocks Launch gate` exactly when that is a recorded fact (§15.8).
 *   The ranked queue does not use it: the server already appends that clause to a candidate's
 *   reason, and a second implementation here could disagree with the sentence on screen.
 */

/** §15.8's three words, plus the two the server can also return. Each carries its own shape. */
const VERDICT = {
  ready: {
    label: "Ready to advance", mark: "ok", symbol: "✓", tone: "ok",
    caveat: "Advancing is still an explicit decision. Nothing moves on its own.",
  },
  blocked: {
    label: "Blocked", mark: "risk", symbol: "▲", tone: "risk",
    caveat: "These conditions were evaluated and are not satisfied.",
  },
  insufficient_data: {
    label: "Evidence missing", mark: "unknown", symbol: "?", tone: "warn",
    caveat: "This is not the same as satisfied. Something could not be evaluated at all.",
  },
  passed: {
    label: "Gate already settled", mark: "ok", symbol: "✓", tone: "ok",
    caveat: "The gate for this phase is recorded as passed or waived.",
  },
};

/**
 * The server's verdict, rendered. The reasons are the server's lists, counted here and never
 * re-derived: a second reading of the same records in the client could disagree with the summary
 * sentence sitting beside it.
 */
export function advancementVerdict(payload) {
  const p = payload || {};
  const known = VERDICT[p.readiness];
  const verdict = known || {
    label: "Not recognized", mark: "unknown", symbol: "?", tone: "warn",
    caveat: "This build does not recognize the answer the server returned, so nothing here should "
      + "be treated as ready.",
  };
  const reasons = [];
  const gaps = (p.requirements || []).filter((r) => r.is_gap);
  const determined = gaps.filter((r) => r.available !== false && r.evaluator_available !== false);
  if (gaps.length) {
    reasons.push({
      key: "requirements",
      text: `${count(gaps.length, "required condition")} not satisfied`,
      items: gaps.map((r) => r.label || r.requirement_key || "Unnamed condition"),
    });
  }
  if ((p.blocking_records || []).length) {
    reasons.push({
      key: "blockers",
      text: `${count(p.blocking_records.length, "open blocker")} on this program`,
      items: p.blocking_records.map((b) => b.description),
    });
  }
  if ((p.open_gate_items || []).length) {
    reasons.push({
      key: "gate_items",
      text: `${count(p.open_gate_items.length, "gate item")} still incomplete`,
      items: p.open_gate_items.map((i) => i.description),
    });
  }
  if ((p.coverage_failures || []).length) {
    reasons.push({
      key: "coverage",
      // Named separately from the gaps above, and worded as a reading failure rather than as an
      // outstanding chore. An evaluator that could not run is not work anybody can do.
      text: `${count(p.coverage_failures.length, "evaluator")} could not be read`,
      items: p.coverage_failures,
    });
  }
  return {
    ...verdict,
    state: p.readiness ?? null,
    recognized: !!known,
    summary: p.summary || "",
    reasons,
    determinedCount: determined.length,
    coverage: p.coverage || null,
    // Said out loud in the UI as well as the payload: reading this moved nothing.
    advancesAutomatically: false,
    stamp: p.readiness_stamp || null,
  };
}

function count(n, singular, plural) {
  return `${n} ${n === 1 ? singular : (plural || `${singular}s`)}`;
}

/**
 * §15.8's fourth bullet: the phase-advance dialog states the exact consequences before anything
 * moves. Both branches are returned as data so a test can assert the override wording is present
 * and that it never promises the gap is resolved.
 */
export function overrideConsequences(payload, { override = false } = {}) {
  const p = payload || {};
  const unmet = (p.requirements || []).filter((r) => r.is_gap);
  const items = (p.open_gate_items || []);
  const to = p.proposed_next_phase_label || p.proposed_next_phase || "the next phase";
  if (!override) {
    return {
      override: false,
      heading: `Advance to ${to}`,
      consequences: [
        { key: "phase", text: `The program phase becomes ${to}.`, tone: "neutral" },
        { key: "gate", text: "The gate for the current phase is recorded as passed, dated by the "
          + "readiness answer you are looking at.", tone: "neutral" },
        { key: "history", text: "A completed transition is appended to the phase history with "
          + "your name and the conditions as they read now.", tone: "neutral" },
      ],
      unmet: [],
    };
  }
  return {
    override: true,
    heading: `Override and advance to ${to}`,
    consequences: [
      { key: "phase", text: `The program phase becomes ${to}.`, tone: "neutral" },
      // The three sentences an override most invites misreading. Each says what does *not* happen,
      // because that is the part a later reader will otherwise assume.
      { key: "gap", text: `${count(unmet.length + items.length, "condition")} listed below `
        + `${unmet.length + items.length === 1 ? "stays" : "stay"} unmet. Overriding accepts the `
        + "gap; it does not fill it.", tone: "risk" },
      { key: "gate", text: "The gate stays open. The program moves past it rather than through "
        + "it, so it will still read as outstanding.", tone: "risk" },
      { key: "state", text: "No readiness state changes. Every condition is recomputed from the "
        + "records on the next read and will say exactly what it says now.", tone: "risk" },
      { key: "history", text: "The override, your reason, and the unmet conditions are appended "
        + "to the phase history permanently.", tone: "neutral" },
    ],
    unmet: [
      ...unmet.map((r) => ({
        key: r.requirement_key || r.plan_instance_id,
        label: r.label || r.requirement_key,
        detail: r.reason || "",
        necessity: r.necessity || "required",
      })),
      ...items.map((i) => ({
        key: i.id, label: i.description, detail: "Legacy gate item", necessity: "required",
      })),
    ],
  };
}

const RELATION_LABEL = {
  advances: "Advances",
  blocks: "Blocks",
  follow_up_for: "Follow-up for",
};

/** An unrecognized relation reads as itself rather than being silently treated as `advances`. */
export function relationLabel(relation) {
  return RELATION_LABEL[relation] || String(relation || "related").replace(/_/g, " ");
}

/**
 * §15.8's first bullet — linked actions grouped by what the relation claims, in server order.
 * A closed action stays visible: closing an action settles the action, never the requirement,
 * and hiding it would make the requirement look untouched.
 */
export function actionLinkGroups(links) {
  const groups = new Map();
  for (const link of links || []) {
    const key = link.relation || "related";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({
      ...link,
      relationLabel: relationLabel(key),
      // `origin` is the difference between an operator's decision and an accepted suggestion, and
      // §15.2 turns on that difference, so it is shown rather than flattened away.
      originLabel: link.origin === "proposal" ? "From an accepted proposal" : "Linked by an operator",
      closed: !!link.action?.status && link.action.status !== "open",
    });
  }
  return [...groups.entries()]
    .sort((a, b) => order(a[0]) - order(b[0]))
    .map(([relation, items]) => ({ relation, label: relationLabel(relation), items }));
}

function order(relation) {
  const seq = { blocks: 0, advances: 1, follow_up_for: 2 };
  return seq[relation] ?? 3;
}

/**
 * §15.8's first bullet — attached evidence with its review state.
 *
 * `supporting: false` is the one that matters: the definition did not allow that kind, so the
 * record is attached as context and cannot move the state. Saying so is the difference between
 * "we looked at this" and "this counts".
 */
export function evidenceRows(links) {
  return (links || []).map((e) => {
    const retracted = !!e.retracted_at;
    return {
      ...e,
      typeLabel: String(e.evidence_type || "record").replace(/_/g, " "),
      supportingLabel: e.supporting ? "Counts toward this condition" : "Context only",
      supportingHint: e.supporting
        ? "The requirement definition accepts this kind of record."
        : "The requirement definition does not accept this kind, so it is on the record but "
          + "cannot change the state.",
      retracted,
      reviewLabel: retracted
        ? `Retracted${e.retracted_reason ? `: ${e.retracted_reason}` : ""}`
        : e.reviewed_on
          ? `Reviewed ${e.reviewed_on}${e.reviewed_by ? ` by ${e.reviewed_by}` : ""}`
          : "Not reviewed",
      // An unreviewed attachment is not a defect and is not marked as one. It is a fact about the
      // attachment, so it gets the neutral mark and the review control, not a warning.
      mark: retracted ? "neutral" : e.supporting ? "ok" : "unknown",
      canReview: !retracted,
      canRetract: !retracted,
    };
  });
}

/**
 * §15.8's fifth bullet. Explicit relations only, and marked secondary so a dependency line never
 * competes with the milestone it hangs off. An empty list is an empty list — the timeline draws
 * nothing rather than inferring a line from a shared date.
 */
export function dependencyLines(links) {
  return (links || []).map((l) => ({
    id: l.id,
    action: l.action,
    label: l.action?.description || l.action?.label || "Linked action",
    relation: l.relation,
    relationLabel: relationLabel(l.relation),
    blocking: l.relation === "blocks",
    note: l.note || null,
    // Every line here came from an accepted relation. The flag is carried so the renderer cannot
    // accidentally style an inferred line the same way — there are no inferred lines to style.
    explicit: true,
    emphasis: "secondary",
  }));
}

/**
 * `Unblocks Launch gate` for an action's own detail panel, returned only when the action has an
 * explicit `advances` link to a requirement that an explicit gate link marks required. Anything
 * weaker — an optional gate link, a `follow_up_for` relation, a similarly worded task — returns
 * null and the caller says nothing.
 *
 * This is not the ranked queue's copy of the same claim. The server appends its own gate clause to
 * a candidate's `reason`, and that stays the single answer there; this one exists because the
 * action detail has no reason string to append to.
 */
export function unblocksReason(context) {
  const gates = (context?.gates || []).filter((g) => g.necessity === "required"
    && g.status === "open");
  if (!gates.length) return null;
  const [first] = gates;
  const more = gates.length - 1;
  return {
    text: `Unblocks ${first.name}${more > 0 ? ` and ${count(more, "other gate")}` : ""}`,
    gate_id: first.gate_id,
    through_requirement: first.through_requirement,
    // The claim's whole warrant, carried with it. A reason that cannot name its relation is a
    // reason that was inferred, and §15.8 does not allow one.
    basis: "explicit_gate_requirement_link",
  };
}

/**
 * §15.8's second bullet — what this Task or Commitment advances, as one flat list the action
 * detail can render. Requirements, milestones, and gates stay labelled by kind, because a gate
 * reached through a requirement is a weaker claim than a milestone linked directly.
 */
export function actionAdvances(context) {
  const c = context || {};
  return [
    ...(c.requirements || []).map((r) => ({
      kind: "requirement", kindLabel: "Requirement", id: r.plan_instance_id,
      label: r.label || r.requirement_key, relation: r.relation,
      relationLabel: relationLabel(r.relation),
      detail: r.definition_of_done || null,
      // The link says this action advances the condition. It does not say the condition is met —
      // readiness answers that from the records, and only from the records.
      caveat: "Closing this action does not set the condition's state.",
    })),
    ...(c.milestones || []).map((m) => ({
      kind: "milestone", kindLabel: "Milestone", id: m.milestone_id, label: m.name,
      relation: m.relation, relationLabel: relationLabel(m.relation),
      detail: m.target_date ? `Target ${m.target_date}` : null,
      caveat: null,
    })),
    ...(c.gates || []).map((g) => ({
      kind: "gate", kindLabel: "Phase gate", id: g.gate_id, label: g.name,
      relation: "advances", relationLabel: "Advances",
      detail: `Through ${g.through_requirement} · ${g.necessity}`,
      caveat: g.necessity === "required" ? null
        : "This gate marks the condition optional, so the gate does not depend on it.",
    })),
  ];
}

/** True when the panel offers no control that could write a readiness state. Asserted, not trusted. */
export function linkControlsWriteNoState(payload) {
  return overrideConsequences(payload, { override: true }).consequences
    .some((c) => c.key === "state");
}
