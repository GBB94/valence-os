/**
 * Plan setup and plan-stage presentation rules (ACCOUNT-PATH-SPEC.md §13.3–§13.5, §13.9).
 *
 * This module exists because the planning layer shipped as nine live routes with no caller: a plan
 * could be instantiated by a seed script but never by an operator. The rules here are what the Plan
 * tab needs in order to offer that write without inventing a second source of truth:
 *
 * - `planStages` *partitions* the server's order into date horizons. It never sorts. The server
 *   ranked the requirements once (`playbooks.merged_plan`) and §6 is explicit that the client does
 *   not re-rank; a second ordering here could disagree with the reasons the rows display.
 * - Nothing in this file computes a state, a freshness, or an overdue flag. `overdue` is read from
 *   the server field verbatim, because recomputing it from `due_date` would be a second answer to a
 *   question readiness has already answered.
 * - `startableVersions` hides the `checklist-compatibility` playbook. The API refuses to
 *   instantiate it by hand (`playbooks.instantiate` raises 422), so offering it in a picker would
 *   be offering a control that cannot succeed.
 * - `upgradeOffers` never returns an action, only the fact that a higher version exists. §13.9:
 *   playbook versions do not retire each other, so an upgrade is an explicit previewed action.
 */

/**
 * Presentation horizons, in days. These group rows for reading; they are not benchmarks and carry
 * no judgment about whether a date is good. Edit them freely — no rule depends on the values.
 */
export const NOW_HORIZON_DAYS = 14;
export const NEXT_HORIZON_DAYS = 45;

/** The playbook the compatibility migration owns. Never offered as a starting choice. */
export const COMPATIBILITY_PLAYBOOK_KEY = "checklist-compatibility";

const MS_PER_DAY = 86400000;

export const STAGES = [
  { key: "overdue", title: "Overdue",
    blurb: "Past the date the plan expected, and not yet evidenced." },
  { key: "now", title: "Due now",
    blurb: `Expected within ${NOW_HORIZON_DAYS} days.` },
  { key: "next", title: "Next",
    blurb: `Expected within ${NEXT_HORIZON_DAYS} days.` },
  { key: "later", title: "Later",
    blurb: "Further out on this plan." },
  { key: "undated", title: "No date on this plan",
    blurb: "Scheduled by the playbook without an offset, so the plan states no date." },
  { key: "settled", title: "Already settled",
    blurb: "Met, waived, recorded complete, or not applicable here. Shown for the record, not as work." },
];

/** Parse an ISO date as UTC midnight so a local timezone cannot shift a due date by a day. */
function utcDay(iso) {
  if (typeof iso !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

export function daysUntil(dueDate, today) {
  const a = utcDay(today);
  const b = utcDay(dueDate);
  if (a === null || b === null) return null;
  return Math.round((b - a) / MS_PER_DAY);
}

/**
 * Which partition a requirement reads under.
 *
 * `settled` is decided by state, and that is a placement choice rather than a restatement: the row
 * still renders its own four axes, and nothing here collapses them into one. A met requirement
 * filed under "Due now" would read as outstanding work, which is the one thing the date buckets
 * must not imply.
 *
 * `applicability: "not_applicable"` settles for the same reason an `applicability_override` does,
 * and reading it here is not a second answer: an operator-marked exception arrives as an override
 * and an evaluator-derived one arrives only on this axis, so testing state and the override alone
 * settled one and filed the other under "Overdue — past the date the plan expected, and not yet
 * evidenced". A condition that does not apply here is not owed, whichever way it stopped applying.
 *
 * `not_due` deliberately does *not* settle. The plan's date has passed and readiness reports the
 * condition is not yet due — two independent axes disagreeing, which the row renders in full. That
 * disagreement is worth seeing; hiding it would let a stale anchor pass unnoticed.
 */
export function stageOf(row, today) {
  const r = row || {};
  if (r.state === "met" || r.recorded_complete || r.applicability_override || r.waiver
      || r.applicability === "not_applicable" || r.state === "not_applicable") {
    return "settled";
  }
  if (r.overdue) return "overdue";
  if (!r.due_date) return "undated";
  const days = daysUntil(r.due_date, today);
  if (days === null) return "undated";
  if (days <= NOW_HORIZON_DAYS) return "now";
  if (days <= NEXT_HORIZON_DAYS) return "next";
  return "later";
}

/**
 * Which partition a setup item reads under.
 *
 * Deliberately not `stageOf`. A gate item has no state, no freshness and no applicability, so the
 * settled test above has nothing to read; its `complete` flag is the operator's own tick and is the
 * only thing that can settle it. And `overdue` is computed here from the date rather than read from
 * the server, because a gate item carries no server-computed overdue flag — which is the honest
 * position, since "past its date and not ticked" is arithmetic, not a judgment about evidence.
 */
export function setupStageOf(item, today) {
  const i = item || {};
  if (i.complete || i.gate_status === "passed" || i.gate_status === "waived") return "settled";
  if (!i.due_date) return "undated";
  const days = daysUntil(i.due_date, today);
  if (days === null) return "undated";
  if (days < 0) return "overdue";
  if (days <= NOW_HORIZON_DAYS) return "now";
  if (days <= NEXT_HORIZON_DAYS) return "next";
  return "later";
}

/**
 * Partition the server-ordered requirements into stages, preserving server order inside each one.
 *
 * Empty stages are returned too, with `rows: []`, so the caller decides what an empty horizon says.
 * Dropping them here would let "nothing is overdue" and "overdue was never computed" look the same.
 *
 * Setup items ride in the same horizons under their own `setup` key, and the two lists are never
 * concatenated. Zach asked for one standard rather than three, and one *reading order* is what that
 * means here — not one row type. A gate item and a requirement answer different questions ("did
 * somebody do this?" versus "is this true of the relationship?"), so merging them into a single
 * array would force one status vocabulary onto both, and the weaker one always wins that.
 */
export function planStages(payload, today) {
  const rows = payload?.requirements || [];
  const setup = payload?.setup_items || [];
  const byKey = new Map(STAGES.map((s) => [s.key, []]));
  const setupByKey = new Map(STAGES.map((s) => [s.key, []]));
  for (const row of rows) {
    const stage = stageOf(row, today);
    (byKey.get(stage) || byKey.get("undated")).push(row);
  }
  for (const item of setup) {
    const stage = setupStageOf(item, today);
    (setupByKey.get(stage) || setupByKey.get("undated")).push(item);
  }
  return STAGES.map((s) => ({
    ...s, rows: byKey.get(s.key) || [], setup: setupByKey.get(s.key) || [],
  }));
}

/**
 * The count an operator acts on: everything except what is already settled.
 *
 * Requirements and setup items are counted separately and returned separately. A single number over
 * both would be the merge going one step too far — "9 things outstanding" invites the reader to
 * treat nine ticks as the way to clear it, and eight of them are conditions no tick can satisfy.
 */
export function openCount(payload, today) {
  const stages = planStages(payload, today).filter((s) => s.key !== "settled");
  const requirements = stages.reduce((n, s) => n + s.rows.length, 0);
  const setup = stages.reduce((n, s) => n + s.setup.length, 0);
  return { requirements, setup, total: requirements + setup };
}

/**
 * Whether this scope has a plan at all, and the sentence to show when it does not.
 *
 * The absence is the important case and the reason this module exists: before this surface, an
 * account with no plan showed an empty readiness panel with nothing to explain it and no way in.
 *
 * `started` describes the *list*, not the picker. `list_plans` returns an account-wide plan inside
 * a program scope on purpose — it is in force there too — so this flag says "something governs what
 * you are looking at", which is a different question from "is there anything left to start here".
 * Deciding the second from the first is what made the picker unreachable: one account-scoped plan
 * anywhere hid the control for every program. `activePlanKeys` answers the second question.
 *
 * The provenance sentence is checked rather than assumed. Attributing every planless requirement to
 * the compatibility migration was a claim about where a record came from, made without looking at
 * the record.
 */
export function planPresence(payload) {
  const plans = (payload?.plans || []).filter((p) => p.status === "active");
  const requirements = payload?.requirements || [];
  if (plans.length) return { started: true, plans, requirementCount: requirements.length };
  const fromCompatibility = requirements.length > 0
    && requirements.every((r) => r.compatibility_source);
  return {
    started: false,
    plans: [],
    requirementCount: requirements.length,
    reason: !requirements.length
      ? "No playbook has been instantiated for this scope, so nothing states what is expected or when."
      : fromCompatibility
        ? "Requirements here came from the checklist compatibility mapping, not from a plan."
        : "Requirements are listed here, but no active plan in this scope states when they are due.",
  };
}

/**
 * The playbook keys already active *in the scope being viewed*, for the startable filter.
 *
 * Scope-exact, unlike `planPresence().plans`. At a program, the payload also carries the account's
 * own plans; at "All programs" it carries every program's. Either set would suppress a startable
 * key that is not in fact active here the moment one playbook key is published in both scopes.
 */
export function activePlanKeys(payload, programId = null) {
  return (payload?.plans || [])
    .filter((p) => p.status === "active")
    .filter((p) => (p.program_id || null) === (programId || null))
    .map((p) => p.playbook_key);
}

/**
 * Playbook versions an operator may start here, filtered to the scope they declare.
 *
 * A program-scoped playbook offered without a program, or an account-scoped one offered with a
 * program, would fail validation on submit — the picker refuses to show a choice the API rejects.
 */
export function startableVersions(library, { hasProgram, activeKeys = [] } = {}) {
  const all = library?.playbooks || [];
  const active = new Set(activeKeys);
  return all
    .filter((p) => p.key !== COMPATIBILITY_PLAYBOOK_KEY)
    .filter((p) => (p.default_scope === "program" ? !!hasProgram : !hasProgram))
    // §13.4 allows one active instance per playbook and scope, enforced by a unique index. A key
    // already active is not startable again; the route back to it is the upgrade preview.
    .filter((p) => !active.has(p.key))
    .map((p) => ({
      key: p.key,
      version: p.version,
      label: p.label || p.key,
      scope: p.default_scope,
      defaultAnchor: p.default_anchor,
      allowedAnchors: p.allowed_anchors || [],
      entryCount: (p.entries || []).length,
      requiredCount: (p.entries || []).filter((e) => e.necessity === "required").length,
    }));
}

/**
 * Whether the operator must supply an anchor date, and what to say about it.
 *
 * `playbooks.instantiate` fills a blank kickoff anchor from the program's own `kickoff_date` and
 * raises otherwise. A form that always offered "leave it blank" would therefore promise a fallback
 * that does not exist for a program with no kickoff recorded, and the Start button would fail every
 * time it was pressed. Asking the server and reading the error is not enough: the operator should
 * not have to press a dead control to discover the date is needed.
 */
export function anchorRequirement(option, kickoffDate) {
  const anchor = option?.defaultAnchor || "anchor";
  const label = `${anchor} date`;
  if (anchor === "kickoff" && kickoffDate) {
    return {
      required: false, label,
      hint: `Leave blank to use the program's recorded kickoff date, ${kickoffDate}.`,
    };
  }
  if (anchor === "kickoff") {
    return {
      required: true, label,
      hint: "This program has no kickoff date recorded, so the plan needs one here.",
    };
  }
  // Every other anchor is supplied by hand; the server has nothing to fall back to.
  return { required: true, label, hint: `The ${anchor} date the plan is measured from.` };
}

/** The highest version per key, which is the one a fresh start should default to. */
export function latestPerKey(versions) {
  const best = new Map();
  for (const v of versions || []) {
    const seen = best.get(v.key);
    if (!seen || v.version > seen.version) best.set(v.key, v);
  }
  return [...best.values()];
}

/**
 * Active plans sitting on a version lower than the highest published one.
 *
 * This reports a fact and offers no action beyond opening the preview. An upgrade that applied
 * itself would move due dates under an operator who never saw the diff.
 */
export function upgradeOffers(payload, library) {
  const highest = new Map();
  for (const p of library?.playbooks || []) {
    const seen = highest.get(p.key);
    if (seen === undefined || p.version > seen) highest.set(p.key, p.version);
  }
  return (payload?.plans || [])
    .filter((p) => p.status === "active")
    .map((p) => {
      const top = highest.get(p.playbook_key);
      if (top === undefined || top <= p.playbook_version) return null;
      return {
        planId: p.id,
        playbookKey: p.playbook_key,
        // The plan's *own* scope, not the scope currently selected in the account header. At
        // "All programs" the plan list returns program-scoped plans too, and `preview_upgrade`
        // resolves a null program_id as the account scope strictly — so passing the selection
        // would ask to upgrade a plan that does not exist and the preview would never load.
        programId: p.program_id || null,
        fromVersion: p.playbook_version,
        toVersion: top,
        text: `On v${p.playbook_version}; v${top} is published.`,
      };
    })
    .filter(Boolean);
}

/**
 * Legacy checklist items that no plan instance covers (§13.5.6).
 *
 * The server already filters these down to the unmapped ones — a checklist item whose template key
 * is in the mapping is dropped before it reaches us — so everything here is, by construction, the
 * seam between the two standard-work systems: an item the onboarding template seeded that no
 * playbook requirement maps to. Reporting the count is the point; a compatibility run that silently
 * covered some and dropped the rest would read as a complete migration.
 *
 * They arrive with `state`, `freshness`, and `applicability` explicitly null. Nothing here fills
 * those in: a synthesised state would be the weaker second source §13.5.6 refuses to create.
 */
export function unmappedLegacy(payload) {
  const items = payload?.legacy_items || [];
  const open = items.filter((i) => i.status !== "done");
  return { items, open, total: items.length, openCount: open.length };
}

/**
 * Read a compatibility report into the lines a panel shows, asserting nothing it did not compute.
 *
 * `dry_run` returns the same shape as the real run by design (§13.5), so the same phrasing serves
 * both and a preview can never describe a different outcome from the run.
 *
 * The three qualifying counts are returned as their own lines rather than folded into the headline.
 * A report that said only "mapped 12 items" would read as a finished migration while unmatched,
 * ambiguous, and evidence-missing rows sat unreported underneath it — and `evidence_missing` is the
 * §13.5.7 case that matters most: a legacy tick the projection does not agree with.
 */
export function compatibilityReport(report) {
  if (!report) return null;
  const c = report.counts || {};
  const dry = !!report.dry_run;
  const n = (x) => x || 0;
  const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

  const notes = [];
  if (n(c.unmatched)) {
    notes.push({
      key: "unmatched", tone: "neutral",
      text: `${plural(n(c.unmatched), "item")} ${dry ? "would be" : "were"} left as they are — no requirement matches their template key.`,
    });
  }
  // Its own line, because it is its own population. Counted inside `unmatched` it borrowed that
  // sentence's reason, and the reason was wrong twice over: these carry no template key to match,
  // and they were not left as they are — they are migrated instances still holding a carried tick.
  if (n(c.orphaned)) {
    const one = n(c.orphaned) === 1;
    notes.push({
      key: "orphaned", tone: "warn",
      text: `${plural(n(c.orphaned), "migrated requirement")} no longer ${one ? "has the checklist item it came from" : "have the checklist items they came from"}. ${one ? "It is" : "They are"} kept rather than deleted — removing ${one ? "it" : "them"} would remove the only trace that the tick was ever carried.`,
    });
  }
  if (n(c.ambiguous)) {
    notes.push({
      key: "ambiguous", tone: "warn",
      text: `${plural(n(c.ambiguous), "item")} map to a requirement another item already claims, so ${dry ? "they would be" : "they were"} left unmapped rather than resolved by guess.`,
    });
  }
  const evidenceMissing = (report.evidence_missing || []).length;
  if (evidenceMissing) {
    notes.push({
      key: "evidence_missing", tone: "warn",
      text: `${plural(evidenceMissing, "item")} carried a completed tick that readiness does not report as met. The tick is recorded as a planning fact and is not treated as evidence.`,
    });
  }

  return {
    dryRun: dry,
    // "across the account", stated in the number's own sentence. The route takes no program and
    // maps every checklist item on the account into each item's own scope, while the list this
    // panel sits under is filtered to the selected program. Without the qualifier the two counts
    // read as the same population and the larger one looks like a bug in the smaller.
    headline: `${dry ? "Would map" : "Mapped"} ${plural(n(c.mapped), "checklist item")} of ${n(c.checklist_items)} across the account onto plan requirements.`,
    notes,
    counts: c,
    complete: notes.length === 0,
  };
}
