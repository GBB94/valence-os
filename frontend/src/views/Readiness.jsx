/**
 * Relationship readiness (RELATIONSHIP-READINESS-SPEC.md §8).
 *
 * One data contract, two presentation modes. Overview gets `compact` — at most three current-phase
 * gaps — so readiness stays a prompt rather than becoming a scorecard. `all` shows every pillar in
 * the detail view. There is no composite grade, no completion percentage, and no "n of m" count:
 * the six pillars are independent, and any tally of them is the score the spec forbids (§2.2).
 *
 * State and freshness render as separate signals (§3.4). Each state pairs a colour with both a
 * shape and a word, so no state is carried by colour alone.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, Loading, SlideOver, fmtDate, rowActivation } from "../ui";

const STATE = {
  met: { label: "Met", mark: "ok" },
  thin: { label: "Thin", mark: "warn" },
  unknown: { label: "Unknown", mark: "unknown" },
  conflicted: { label: "Conflicted", mark: "conflict" },
  not_applicable: { label: "Not applicable", mark: "na" },
};

const FRESHNESS_LABEL = {
  current: "current", stale: "stale", mixed: "mixed dates", undated: "undated",
  not_applicable: null,
};

const PROVENANCE_LABEL = {
  confirmed_source: "confirmed source",
  operator_recorded: "operator recorded",
  unsupported: "unsupported",
};

// A gap the operator can act on now. `not_due` and `not_applicable` are deliberately excluded:
// surfacing them as gaps would turn "this phase does not need it yet" into a chore.
const GAP_ORDER = { conflicted: 0, unknown: 1, thin: 2 };

function isGap(pillar) {
  return pillar.applicability === "required" && GAP_ORDER[pillar.state] !== undefined;
}

function flatten(result) {
  const rows = (result.pillars || []).map((p) => ({ ...p, program_name: null, program_id: null }));
  for (const entry of result.programs || []) {
    for (const p of entry.pillars || []) {
      rows.push({ ...p, program_name: entry.program_name, program_id: entry.program_id });
    }
  }
  return rows;
}

export function StateBadge({ state, applicability }) {
  if (applicability === "not_due") {
    return (
      <span className="state-badge">
        <span className="state-mark na" aria-hidden="true" />Not due yet
      </span>
    );
  }
  const s = STATE[state] || STATE.unknown;
  return (
    <span className="state-badge">
      <span className={"state-mark " + s.mark} aria-hidden="true" />{s.label}
    </span>
  );
}

export function FreshnessChip({ freshness, date }) {
  const label = FRESHNESS_LABEL[freshness];
  if (!label) return null;
  const cls = freshness === "current" ? "age-fresh" : freshness === "stale" ? "age-stale" : "age-aging";
  return (
    <span className={"age " + cls} title={date ? `assessed through ${fmtDate(date)}` : undefined}>
      {label}{date ? ` · ${fmtDate(date)}` : ""}
    </span>
  );
}

function PillarRow({ pillar, onOpen }) {
  return (
    <div className="readiness-row clickable" {...rowActivation(() => onOpen(pillar))}>
      <div className="readiness-row-head">
        <strong>{pillar.label}</strong>
        {pillar.program_name && <span className="rowmeta">{pillar.program_name}</span>}
        <div className="spacer" />
        <StateBadge state={pillar.state} applicability={pillar.applicability} />
      </div>
      <div className="rowmeta readiness-reason">{pillar.reason || "No assessment recorded."}</div>
      <FreshnessChip freshness={pillar.freshness} />
    </div>
  );
}

/**
 * `mode="compact"` — Overview and Account essentials. `mode="all"` — the focused detail view.
 */
export function ReadinessSummary({ accountId, programId = null, mode = "compact", reloadKey,
  onOpenTarget }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);
  const [showingAll, setShowingAll] = useState(false);

  useEffect(() => {
    let live = true;
    setResult(null); setError(null);
    api.readiness(accountId, programId)
      .then((r) => { if (live) setResult(r); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [accountId, programId, reloadKey]);

  if (error) return <div className="callout warn">Readiness unavailable: {error}</div>;
  if (!result) return <Loading what="readiness" />;

  const rows = flatten(result);
  const gaps = rows.filter(isGap).sort((a, b) => GAP_ORDER[a.state] - GAP_ORDER[b.state]);
  const shown = mode === "compact" ? gaps.slice(0, 3) : rows;
  const partial = result.coverage?.status !== "complete";

  return (
    <div className="card readiness-card">
      <div className="card-h">
        <h3>Relationship readiness</h3>
        <div className="spacer" />
        {mode === "compact" && gaps.length > shown.length && (
          // The cap is a presentation choice, not a filter on what exists. Truncating without a
          // way through would hide required gaps behind a number, which is exactly the failure
          // the compact mode is meant to avoid.
          <button className="readiness-more" onClick={() => setShowingAll(true)}>
            {gaps.length - shown.length} more
          </button>
        )}
      </div>

      {partial && (
        <div className="coverage-callout is-warning">
          {result.coverage?.warnings?.join(" ") || "Some conditions could not be evaluated."}
          {result.coverage?.failed_evaluators?.length
            ? ` Unavailable: ${result.coverage.failed_evaluators.join(", ")}.`
            : ""}
        </div>
      )}

      {shown.length === 0 ? (
        mode === "compact" ? (
          // No gap means no row, so there is no pillar to open from here. The old copy pointed at
          // an affordance this branch never renders.
          <Empty title="No current-phase gaps">
            Every required condition for this phase is met or not yet due. The full pillar set and
            its evidence are on the Readiness tab.
          </Empty>
        ) : (
          <Empty title="No readiness definitions">Seed the pillar definitions to evaluate.</Empty>
        )
      ) : (
        <div className="readiness-list">
          {shown.map((p) => (
            <PillarRow key={`${p.program_id || "account"}:${p.key}`} pillar={p} onOpen={setOpen} />
          ))}
        </div>
      )}

      <div className="rowmeta readiness-foot">
        Six independent conditions — no combined score. Each is judged only against accepted
        records{result.as_of ? ` as of ${fmtDate(result.as_of)}` : ""}.
      </div>

      {showingAll && (
        <SlideOver title="Relationship readiness" onClose={() => setShowingAll(false)}>
          <div className="readiness-list">
            {rows.map((p) => (
              <PillarRow key={`${p.program_id || "account"}:${p.key}`} pillar={p}
                onOpen={(pillar) => { setShowingAll(false); setOpen(pillar); }} />
            ))}
          </div>
          <div className="rowmeta readiness-foot">
            Every condition in scope, in definition order — still six independent judgements with
            no combined score.
          </div>
        </SlideOver>
      )}

      {open && (
        <SlideOver title={open.label} onClose={() => setOpen(null)}>
          <ReadinessDetail pillar={open} onOpenTarget={onOpenTarget} />
        </SlideOver>
      )}
    </div>
  );
}

/**
 * The evidence view: what each component decided, on what records, and what would close it.
 */
/**
 * One evidence record (§5.3). It opens the native record when the server routed it, and reads as
 * plain text when it did not — `account_field`, `program_field` and `source_reference` name a
 * column or a provenance pointer rather than a record with a home, and a button that navigates
 * nowhere is a worse answer than a line of text.
 */
export function EvidenceItem({ evidence, onOpenTarget }) {
  const kind = <span className="rowmeta">{evidence.type.replace(/_/g, " ")}</span>;
  const prov = evidence.provenance ? (
    <span className={"prov prov-" + evidence.provenance}>
      {PROVENANCE_LABEL[evidence.provenance]}
    </span>
  ) : null;
  if (!evidence.native_target || !onOpenTarget) {
    return <li>{kind} {evidence.label}{prov}</li>;
  }
  return (
    <li>
      {kind}{" "}
      <button className="linklike" onClick={() => onOpenTarget(evidence.native_target)}>
        {evidence.label}
      </button>
      {prov}
    </li>
  );
}

export function ReadinessDetail({ pillar, onOpenTarget }) {
  return (
    <div className="readiness-detail">
      <div className="detail-head">
        <StateBadge state={pillar.state} applicability={pillar.applicability} />
        <FreshnessChip freshness={pillar.freshness} />
      </div>
      <p className="detail-title">{pillar.reason}</p>
      <div className="rowmeta">{pillar.purpose}</div>
      <div className="rowmeta" style={{ marginTop: 4 }}>
        {pillar.program_name ? `Scope: ${pillar.program_name}` : "Scope: account"} ·
        {" "}definition v{pillar.definition_version} · evaluator v{pillar.evaluator_version} ·
        {" "}{pillar.research_class === "core_hypothesis" ? "core hypothesis" : "supporting hypothesis"}
      </div>

      {(pillar.components || []).map((c) => (
        <div key={c.key} className="readiness-component">
          <div className="readiness-row-head">
            <strong>{c.label || c.key}</strong>
            <div className="spacer" />
            <StateBadge state={c.state} />
          </div>
          <div className="rowmeta">{c.reason}</div>
          <div className="readiness-meta">
            <FreshnessChip freshness={c.freshness} date={c.assessed_through} />
            {c.provenance && (
              <span className={"prov prov-" + c.provenance}>{PROVENANCE_LABEL[c.provenance]}</span>
            )}
          </div>
          {c.definition_of_done && (
            <div className="rowmeta readiness-dod">Definition of done: {c.definition_of_done}</div>
          )}
          {c.evidence?.length > 0 && (
            <ul className="readiness-evidence">
              {c.evidence.map((e) => (
                <EvidenceItem key={e.type + e.id} evidence={e} onOpenTarget={onOpenTarget} />
              ))}
            </ul>
          )}
          {c.missing?.length > 0 && (
            <ul className="readiness-missing">
              {c.missing.map((m) => <li key={m}>{m}</li>)}
            </ul>
          )}
        </div>
      ))}

      {pillar.suggested_action && (
        // Deliberately not a Task: a suggestion is a proposal until an operator accepts it, and
        // it must not look like accepted work already on someone's list.
        <div className="readiness-suggestion">
          <span className="rowmeta">Suggested — not created</span>
          <div>{pillar.suggested_action.title}</div>
        </div>
      )}
    </div>
  );
}

export default ReadinessSummary;
