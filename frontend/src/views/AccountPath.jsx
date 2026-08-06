/**
 * Account Path — the Operate orientation band and execution groups (ACCOUNT-PATH-SPEC.md §11).
 *
 * Every component here is presentational. The order of rows arrives already ranked by the server's
 * deterministic bands (§10.5) and is rendered as given: a second ranking in the client could
 * disagree with the reason sentence each row displays. Rules that decide wording, caps, and lane
 * order live in `../accountPath.js` so they are testable without a DOM.
 *
 * Nothing here closes or completes a record. Snooze goes to the existing queue suppression
 * endpoint, and everything else navigates to a native record — Account Path never closes,
 * completes, or edits anything (§7.1). The one write it hosts is Slice 5's governed phase
 * advance, which moves the canonical program phase and no record's state (§15.6).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Card, Empty, Loading, SlideOver, useToast } from "../ui";
import { AccountEssentialsGaps, RequirementPanel } from "./RequirementDetail";
import PhaseGateReadiness from "./PathAdvance";
import {
  GROUP_CAP, LANE_CAP, SUPPLEMENT_CAP, UPCOMING_CAP,
  capped, coverageNotice, emptyStateCopy, laneOrder, ownerLabel, phaseAria, phaseState,
  primaryActionLabel, sourceLabel, urgencyLabel, waitingLabel, withoutNextMove,
} from "../accountPath";
import {
  markMoveSnoozed, rememberOpenedMove, takeMoveThatLeft, useMeasure,
} from "../measure";
import {
  departureProperties, groupProperties, moveProperties, pathViewProperties, requirementProperties,
  retryProperties, snoozeDays,
} from "../telemetry";

/** §6.5. Deliberately not styled like the readiness `provenance` chip: they mean different things. */
export function SourceLabelChip({ provenance }) {
  const label = sourceLabel(provenance);
  if (!label) return null;
  return <span className="path-source">{label}</span>;
}

function UrgencyChip({ candidate, today }) {
  const { text, tone } = urgencyLabel(candidate, today);
  return (
    <span className={`path-urgency tone-${tone}`}>
      <span className={`state-mark ${tone === "risk" ? "risk" : tone === "warn" ? "warn" : "neutral"}`}
        aria-hidden="true" />
      {text}
    </span>
  );
}

/**
 * §6.4. Reason, owner, due state, program, and source label are all facts the row states outright.
 * An absent owner or date renders as "Unassigned"/"No due date" rather than disappearing.
 */
export function ExecutionRow({ item, today, waiting = false, onOpenTarget, onSnooze,
                              track, group = "you_own" }) {
  // §17.3 `execution_native_target_opened`. The measured fields are the row's source type and the
  // tab it hands off to — never its title, and never the record's identifier.
  function open() {
    track?.("execution_native_target_opened", {
      source_type: item.source_type, target_tab: item.native_target?.tab || null,
      from_surface: group,
    });
    onOpenTarget(item.native_target);
  }
  return (
    <article className="path-row">
      <div className="path-row-body">
        <div className="path-row-title">{item.title}</div>
        <div className="path-row-reason">{item.reason}</div>
        <div className="path-row-meta">
          <UrgencyChip candidate={item} today={today} />
          <span>{waiting ? waitingLabel(item) : ownerLabel(item)}</span>
          {waiting && item.owner && <span>Follow-up: {item.owner.name}</span>}
          {item.program_name && <span>{item.program_name}</span>}
          <SourceLabelChip provenance={item.provenance} />
        </div>
      </div>
      <div className="path-row-actions">
        <button className="btn small" onClick={open}>{primaryActionLabel(item)}</button>
        {item.snooze_key
          ? <button className="btn small ghost" onClick={() => onSnooze(item)}>Snooze</button>
          : <button className="btn small ghost" onClick={open}>Open source</button>}
      </div>
    </article>
  );
}

/**
 * §11.5. Five rows by default; `View all` hands off to the native view rather than expanding
 * without limit, because Overview is an orientation surface and the Ledger is the list.
 */
export function ExecutionGroup({ title, meta, items, today, waiting, emptyTitle, emptyBody,
                                viewAllTab, onOpenTarget, onSnooze, tone = "neutral",
                                track, group = "you_own" }) {
  const { shown, remaining } = capped(items, GROUP_CAP);
  // §17.3 `execution_group_opened` is the hand-off to the full list, not the render: every group
  // is on screen from the moment the page loads, so firing on render would measure the page, not
  // a decision. `group` is the lane's stable key, never the heading it happens to display.
  function openAll() {
    track?.("execution_group_opened", groupProperties(group, items));
    onOpenTarget({ tab: viewAllTab });
  }
  return (
    <Card spotlight className={`command-section command-tone-${tone} path-group`}>
      <div className="card-h">
        <div>
          <h3>{title}</h3>
          {meta && <div className="rowmeta command-section-meta">{meta}</div>}
        </div>
        <div className="spacer" />
        {remaining > 0 && viewAllTab && (
          <button className="btn small ghost" onClick={openAll}>View all {items.length}</button>
        )}
      </div>
      {shown.length === 0
        ? <Empty title={emptyTitle}>{emptyBody}</Empty>
        : <div className="path-rows">
          {shown.map((item) => (
            <ExecutionRow key={item.id} item={item} today={today} waiting={waiting}
              onOpenTarget={onOpenTarget} onSnooze={onSnooze} track={track} group={group} />
          ))}
        </div>}
      {remaining > 0 && (
        <div className="rowmeta path-group-foot">
          {remaining} more not shown here. Open the full list to see {remaining === 1 ? "it" : "them"}.
        </div>
      )}
    </Card>
  );
}

/**
 * §6.2. An ordered list of real buttons. State is carried by a word, a shape, and a colour class
 * together; a blocked phase always names its reason.
 */
export function ProgramPath({ path, selectedPhase, onSelectPhase, onOpenTarget, compact = false }) {
  return (
    <div className={`path-rail${compact ? " is-compact" : ""}`}>
      <div className="path-rail-head">
        <strong>{path.program_name}</strong>
        {path.next_gate && (
          <button className="path-gate-link" onClick={() => onOpenTarget(path.next_gate.native_target)}>
            {path.next_gate.name}
            {path.next_gate.missing_count > 0
              ? ` · ${path.next_gate.missing_count} incomplete`
              : " · all items complete"}
          </button>
        )}
      </div>
      <ol className="path-steps">
        {path.steps.map((step) => {
          const state = phaseState(step.state);
          const selected = selectedPhase === step.key;
          // The state word is hidden in a compact lane (§6.3), so it would fall out of the
          // accessible name if the button relied on its visible text. `title` is only a tooltip
          // fallback; the label is what carries the state and its reason to a screen reader.
          const label = phaseAria(step);
          return (
            <li key={step.key} className={`path-step is-${state.mark}${selected ? " is-selected" : ""}`}>
              <button type="button" onClick={() => onSelectPhase(selected ? null : step.key)}
                aria-current={step.state === "current" ? "step" : undefined}
                aria-pressed={selected}
                aria-label={label} title={label}>
                <span className="path-step-mark" aria-hidden="true">{state.symbol}</span>
                <span className="path-step-label">{step.label}</span>
                <span className="path-step-state">{state.label}</span>
              </button>
              {step.blocking_reason && (
                <div className="path-step-reason">{step.blocking_reason}</div>
              )}
            </li>
          );
        })}
      </ol>
      {path.next_milestone && (
        <button className="path-milestone" onClick={() => onOpenTarget(path.next_milestone.native_target)}>
          Next milestone: {path.next_milestone.name}
          {path.next_milestone.target_date ? ` · ${path.next_milestone.target_date}` : " · no target date"}
          {path.next_milestone.at_risk ? " · flagged at risk" : ""}
        </button>
      )}
    </div>
  );
}

/** §6.3. One compact lane per program; an account never gets an invented aggregate phase. */
export function ProgramPathLane({ path, selectedPhase, onSelectPhase, onOpenTarget }) {
  return <ProgramPath path={path} selectedPhase={selectedPhase} onSelectPhase={onSelectPhase}
    onOpenTarget={onOpenTarget} compact />;
}

/**
 * §6.1. One dominant item, its deterministic reason, and at most two controls. No sparkle
 * treatment: selection is rules-based and must not read as a prediction.
 */
export function NextBestMove({ move, emptyState, today, onOpenTarget, onSnooze, track,
                              scope = null }) {
  // §17.3 `next_move_opened` — §17.5 question 2, whether the recommendation is the thing the
  // operator actually acts on. The row is also remembered so a later response can tell whether it
  // was closed; `measure.js` explains why that memory cannot live in component state.
  function open() {
    if (move) {
      track?.("next_move_opened", moveProperties(move));
      rememberOpenedMove({
        id: move.id, accountId: scope?.account_id || null, programId: scope?.program_id || null,
        properties: departureProperties(move, today),
      });
    }
    onOpenTarget(move.native_target);
  }
  if (!move) {
    const copy = emptyStateCopy(emptyState);
    if (!copy) return null;
    return (
      <div className="path-move is-empty">
        <div className="page-eyebrow">NEXT BEST MOVE</div>
        <h2>{copy.title}</h2>
        <p className="path-move-reason">{copy.message}</p>
        {copy.requirement && (
          <div className="path-move-requirement">
            <strong>{copy.requirement.label || copy.requirement.key}</strong>
            <div className="rowmeta">{copy.requirement.reason}</div>
            <div className="rowmeta">
              This is a suggestion, not an action on anyone's list. Open Relationship readiness for
              the evidence behind it.
            </div>
          </div>
        )}
        {copy.action && (
          <button className="btn" onClick={() => onOpenTarget({ tab: copy.action.tab })}>
            {copy.action.label}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="path-move">
      <div className="page-eyebrow">NEXT BEST MOVE</div>
      <h2>{move.title}</h2>
      {/* §15.8's `Unblocks the Launch gate` clause is already part of the server's reason string,
          appended there only where an accepted `advances` link reaches a gate that is open and
          gates the current phase. It is not re-derived here: a second implementation in the client
          could disagree with the sentence the reader is looking at. */}
      <p className="path-move-reason">{move.reason}</p>
      <div className="path-row-meta path-move-meta">
        <UrgencyChip candidate={move} today={today} />
        <span>{ownerLabel(move)}</span>
        {move.program_name && <span>{move.program_name}</span>}
        <SourceLabelChip provenance={move.provenance} />
      </div>
      <div className="path-move-actions">
        <button className="btn primary" onClick={open}>{primaryActionLabel(move)}</button>
        {move.snooze_key
          ? <button className="btn" onClick={() => onSnooze(move)}>Snooze</button>
          : <button className="btn" onClick={open}>Open source</button>}
      </div>
    </div>
  );
}

/** §11.3. Next best move and the path share one surface so the band reads as a single orientation. */
export function AccountPathOrientation({ data, today, selectedPhase, onSelectPhase,
                                        onOpenTarget, onSnooze, track }) {
  const lanes = laneOrder(data.program_paths);
  const [showAllLanes, setShowAllLanes] = useState(false);
  const single = data.scope.mode === "program";
  const { shown, remaining } = capped(lanes, showAllLanes ? lanes.length : LANE_CAP);
  return (
    <Card spotlight className="path-orientation">
      <div className="path-orientation-move">
        <NextBestMove move={data.next_move} emptyState={data.empty_state} today={today}
          onOpenTarget={onOpenTarget} onSnooze={onSnooze} track={track} scope={data.scope} />
      </div>
      <div className="path-orientation-rail">
        {lanes.length === 0
          ? <Empty title="No program recorded">
            The path is derived from programs and their gates. Record a program in Plan to see one.
          </Empty>
          : shown.map((path) => (
            single
              ? <ProgramPath key={path.program_id} path={path} selectedPhase={selectedPhase}
                onSelectPhase={onSelectPhase} onOpenTarget={onOpenTarget} />
              : <ProgramPathLane key={path.program_id} path={path} selectedPhase={selectedPhase}
                onSelectPhase={onSelectPhase} onOpenTarget={onOpenTarget} />
          ))}
        {remaining > 0 && (
          <button className="path-more" onClick={() => setShowAllLanes(true)}>
            View all {lanes.length} programs
          </button>
        )}
      </div>
    </Card>
  );
}

/** §11.10. Named, never silent, and never rendered as caught up. */
export function ExecutionCoverageNotice({ coverage }) {
  const notice = coverageNotice(coverage);
  if (!notice) return null;
  // A withheld row is not a failure, so it gets no status hue — it is a quiet sentence saying the
  // list is shorter than the account. An unreadable source keeps the callout it earned, and lists
  // the same warnings underneath rather than dropping them for having arrived beside worse news.
  if (notice.status === "complete") {
    return (
      <div className="rowmeta path-coverage" role="status">{notice.warnings.join(" · ")}</div>
    );
  }
  return (
    <div className={`callout ${notice.status === "unavailable" ? "risk" : "warn"} path-coverage`}
      role="status">
      {notice.message}
      {notice.warnings.length > 0 && <div className="rowmeta">{notice.warnings.join(" · ")}</div>}
    </div>
  );
}

/**
 * The queue's own snooze prompt, reused verbatim (§6.1). `attention_state` refuses a snooze with
 * neither a return date nor a resurfacing condition, so there is no bare snooze here either.
 */
function PathSnooze({ item, onClose, onDone, today = null }) {
  const toast = useToast();
  const [until, setUntil] = useState("");
  const [cond, setCond] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    if (!until && !cond.trim()) { toast("Give a return date or a resurfacing condition.", "err"); return; }
    setSaving(true);
    try {
      await api.snoozeQueue({
        item_key: item.snooze_key, snooze_until: until || null,
        resurface_condition: cond.trim() || null,
      });
      toast("Snoozed");
      onDone({ snoozeDays: snoozeDays(today, until || null) });
    } catch (error) {
      toast(error.message, "err");
    } finally {
      setSaving(false);
    }
  }
  return (
    <SlideOver title="Snooze item" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>Snooze</button>
    </>}>
      <div className="subtle" style={{ marginBottom: "var(--sp-5)" }}>{item.title}</div>
      <div className="field"><label>Return date</label>
        <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></div>
      <div className="path-snooze-or">or</div>
      <div className="field"><label>Resurfacing condition</label>
        <input value={cond} onChange={(e) => setCond(e.target.value)}
          placeholder="e.g. if the gate review isn't scheduled by next week" />
        <div className="hint">
          Snoozing hides this row. It does not close, cancel, or edit the underlying record, and the
          item returns automatically if that record changes.
        </div>
      </div>
    </SlideOver>
  );
}

/**
 * §11.2. Loads independently of the account activity request, so a failure here shows a compact
 * error with Retry instead of blanking the account.
 */
function useExecutionPath(accountId, programId, reloadKey) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    api.executionPath(accountId, { programId: programId || "" })
      .then((result) => { if (live) setData(result); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [accountId, programId, reloadKey, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  // `nonce` is the retry count for this scope, which is what `execution_path_retry` reports as
  // `attempt`: one failure retried four times and four separate failures are different problems.
  return { data, error, reload, attempt: nonce };
}

/**
 * The whole Account Path region: orientation band, coverage notice, and the execution groups the
 * Operate lens orders around its existing activity sections.
 */
export default function AccountPath({ accountId, programId, reloadKey, onOpenTarget, onSaved,
                                     mainSlot, sideSlot }) {
  const { data, error, reload, attempt } = useExecutionPath(accountId, programId, reloadKey);
  const [selectedPhase, setSelectedPhase] = useState(null);
  const [snoozing, setSnoozing] = useState(null);
  const [requirement, setRequirement] = useState(null);
  // §17.6 step 7. The ruleset the response was actually ordered by rides on every event, so a
  // later review can tell which ordering the operator was looking at.
  const track = useMeasure({
    accountId, programId: programId || null,
    rankingRuleVersion: data?.ranking_rules?.version || null,
  });
  const viewedRef = useRef(null);

  // Scope changes invalidate a phase selection: the phase key means something different under a
  // different program, and carrying it across would filter by a phase the reader did not pick.
  useEffect(() => { setSelectedPhase(null); setRequirement(null); }, [accountId, programId]);

  // §17.3 `account_path_viewed`, once per response rather than once per render, and after the
  // response arrives rather than on mount — the interesting part of the event is what the page
  // was able to say, which is not known until it has said it.
  useEffect(() => {
    if (!data) return;
    const stamp = data.stamp?.generated_at;
    if (viewedRef.current === stamp) return;
    viewedRef.current = stamp;
    track("account_path_viewed", pathViewProperties(data));
    // A recommendation that was opened and has since left the response. That is all this observes
    // — the row may have been closed, cancelled, archived or aged out of its band, and Account
    // Path never sees which. `takeMoveThatLeft` holds every reason the absence can mean nothing.
    const left = takeMoveThatLeft(data);
    if (left) track("next_move_left_list", left);
  }, [data, track]);

  // An open requirement panel re-reads itself from each fresh response rather than holding the
  // row it was opened with. After a governed decision the state and the suppression notice both
  // change, and a stale copy would keep showing the answer from before the decision.
  useEffect(() => {
    if (!requirement) return;
    const rows = data?.work?.account_essentials?.requirements?.requirements;
    if (!rows) return;
    const fresh = rows.find((r) => r.id === requirement.id);
    if (fresh && fresh !== requirement) setRequirement(fresh);
  }, [data]);

  if (error) {
    return (
      <Card className="path-error">
        <Empty title="Account Path unavailable">{error}</Empty>
        <div className="actions">
          <button className="btn" onClick={() => {
            // The request never returned, so there is no coverage block to name a source; the
            // event says `request_failed` rather than guessing which adapter was at fault.
            track("execution_path_retry", retryProperties(null, attempt + 1));
            reload();
          }}>Retry</button>
          <button className="btn ghost" onClick={() => onOpenTarget({ tab: "plan" })}>Open Plan</button>
          <button className="btn ghost" onClick={() => onOpenTarget({ tab: "ledger" })}>Open Ledger</button>
        </div>
      </Card>
    );
  }
  if (!data) return <Loading what="account path" />;

  const today = (data.stamp.data_current_through || "").slice(0, 10);
  const move = data.next_move;
  // Only a gate item genuinely belongs to a phase (`phase` is null on everything else), so a
  // phase filter narrows to those and says plainly that other work is not phase-attributed.
  const phaseFilter = (items) => (selectedPhase
    ? items.filter((item) => item.phase === selectedPhase)
    : items);
  const waiting = phaseFilter(data.work.waiting_on_customer);
  const supplements = capped(data.work.account_essentials.checklist_supplements, SUPPLEMENT_CAP);
  const upcoming = capped(data.work.upcoming_gates, UPCOMING_CAP);
  // The accepted-action list names ids; the full candidates are already in `work`, carrying their
  // own owner, reason, and snooze key. Re-using them avoids rendering an owned action as
  // `Unassigned` just because the summary list does not repeat the owner.
  const byId = new Map([...data.work.you_own, ...data.work.waiting_on_customer]
    .map((item) => [item.id, item]));
  const accepted = withoutNextMove((data.latest_interaction?.accepted_actions || [])
    .map((action) => byId.get(action.id))
    .filter(Boolean), move);
  // §7.3: one action, one place. An item promoted into the interaction group is not repeated in
  // You own, and neither is the item already shown as the next move.
  const acceptedIds = new Set(accepted.map((item) => item.id));
  const youOwn = phaseFilter(withoutNextMove(data.work.you_own, move)
    .filter((item) => !acceptedIds.has(item.id)));

  function afterSnooze(result) {
    // §17.3 `next_move_snoozed` covers the recommendation only, because that is the question
    // §17.5 asks. A snooze on any other row is a queue suppression the queue already owns, and
    // giving it this event would make the funnel's denominator mean two different things.
    if (snoozing && move && snoozing.id === move.id) {
      track("next_move_snoozed", {
        source_type: move.source_type, reason_code: move.reason_code,
        snooze_days: result?.snoozeDays ?? null, snooze_key_present: Boolean(move.snooze_key),
      });
    }
    if (snoozing) markMoveSnoozed(snoozing.id);
    setSnoozing(null);
    reload();
    onSaved?.();
  }

  // §17.3 `program_path_filtered`. `result_count` is what the filter left visible, which is the
  // point of the event: a phase selection that empties both lanes is the interesting case.
  function selectPhase(phase) {
    const rows = [...data.work.you_own, ...data.work.waiting_on_customer];
    track("program_path_filtered", {
      filter: phase ? "phase" : "cleared",
      phase: phase || null,
      result_count: phase ? rows.filter((row) => row.phase === phase).length : rows.length,
    });
    setSelectedPhase(phase);
  }

  function openRequirement(row) {
    track("requirement_opened", requirementProperties(row, data.coverage?.readiness));
    setRequirement(row);
  }

  return (
    <>
      <AccountPathOrientation data={data} today={today} selectedPhase={selectedPhase}
        onSelectPhase={selectPhase} onOpenTarget={onOpenTarget} onSnooze={setSnoozing}
        track={track} />
      <ExecutionCoverageNotice coverage={data.coverage} />
      {selectedPhase && (
        <div className="callout path-phase-filter" role="status">
          Filtered to the {selectedPhase.replace(/_/g, " ")} phase. Only gate items belong to a
          phase; tasks, commitments, and dates are recorded against the program, so they are hidden
          rather than reassigned.
          <button className="btn small ghost" onClick={() => selectPhase(null)}>Clear filter</button>
        </div>
      )}

      <div className="command-grid">
        <div className="command-main stack">
          {/* §15.8 — the gate verdict and the governed advance, and only when one program is in
              scope. An account with several programs has several gates, and picking one of them
              to show would be an arbitrary answer to a question the reader did not ask. */}
          {data.scope.mode === "program" && programId && (
            <PhaseGateReadiness programId={programId} track={track}
              onChanged={() => { reload(); onSaved?.(); }} />
          )}
          {data.latest_interaction && accepted.length > 0 && (
            <ExecutionGroup title="From the latest interaction" tone="accent"
              meta={`${data.latest_interaction.title} · ${data.latest_interaction.occurred_on}`}
              items={phaseFilter(accepted)}
              today={today} emptyTitle="No accepted actions"
              emptyBody="No open record is linked to the latest interaction."
              viewAllTab="ledger" onOpenTarget={onOpenTarget} onSnooze={setSnoozing}
              track={track} group="latest_interaction" />
          )}
          <ExecutionGroup title="You own" tone="neutral"
            meta="Operator-owned work, ranked by the same deterministic rules as the move above"
            items={youOwn} today={today}
            emptyTitle={selectedPhase ? "No gate items in this phase" : "Nothing else on your list"}
            emptyBody={selectedPhase
              ? "This phase has no incomplete gate item in scope."
              : "No other operator-owned action is open for this scope."}
            viewAllTab="ledger" onOpenTarget={onOpenTarget} onSnooze={setSnoozing}
            track={track} group="you_own" />
          {mainSlot}
        </div>
        <aside className="command-side stack">
          <ExecutionGroup title="Waiting on customer" tone="quiet"
            meta="Customer responsibilities with their internal follow-up owner"
            items={waiting} today={today} waiting
            emptyTitle="No open customer wait"
            emptyBody="No customer responsibility is open for this scope."
            viewAllTab="ledger" onOpenTarget={onOpenTarget} onSnooze={setSnoozing}
            track={track} group="waiting_on_customer" />
          <AccountEssentialsGaps requirements={data.work.account_essentials.requirements}
            today={today} onOpenRequirement={openRequirement} />
          {sideSlot}
          {supplements.shown.length > 0 && (
            <Card spotlight className="command-section command-tone-quiet path-group">
              <div className="card-h">
                <div>
                  <h3>Standard onboarding requirements</h3>
                  {/* Kept beside readiness, not merged into it: a checklist section is time from
                      kickoff, not a phase, and a checkbox is not evidence. */}
                  <div className="rowmeta command-section-meta">
                    Open checklist items. These are a supplement to readiness, not readiness
                    evidence, and their sections are time from kickoff rather than program phase.
                  </div>
                </div>
              </div>
              <div className="path-rows">
                {supplements.shown.map((item) => (
                  <article className="path-row" key={item.id}>
                    <div className="path-row-body">
                      <div className="path-row-title">{item.title}</div>
                      {item.detail && <div className="path-row-reason">{item.detail}</div>}
                      <div className="path-row-meta">
                        <span>{item.section.replace(/_/g, " ")}</span>
                        <span>{item.scope_label}</span>
                        {item.overdue && (
                          <span className="path-urgency tone-risk">
                            <span className="state-mark risk" aria-hidden="true" />Past its date
                          </span>
                        )}
                        <span className="path-source">{item.source_label}</span>
                      </div>
                    </div>
                    <div className="path-row-actions">
                      <button className="btn small" onClick={() => onOpenTarget(item.native_target)}>
                        Open requirement
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              {supplements.remaining > 0 && (
                <button className="command-more" onClick={() => onOpenTarget({ tab: "onboarding" })}>
                  View all {data.work.account_essentials.checklist_supplements.length}
                </button>
              )}
            </Card>
          )}
          <Card spotlight className="command-section command-tone-quiet path-group">
            <div className="card-h">
              <div>
                <h3>Upcoming gates and dates</h3>
                <div className="rowmeta command-section-meta">Open gates for each program in scope</div>
              </div>
            </div>
            {upcoming.shown.length === 0
              ? <Empty title="No open gate">No program in scope has an open phase gate.</Empty>
              : <div className="path-rows">
                {upcoming.shown.map((gate) => (
                  <article className="path-row" key={gate.gate_id}>
                    <div className="path-row-body">
                      <div className="path-row-title">{gate.name}</div>
                      <div className="path-row-reason">
                        {gate.missing_count > 0
                          ? `${gate.missing_count} item${gate.missing_count === 1 ? "" : "s"} incomplete`
                          : "All items complete"}
                        {gate.is_current_phase ? " · current phase" : ""}
                      </div>
                      <div className="path-row-meta">
                        <span>{gate.program_name}</span>
                        <span>{gate.phase.replace(/_/g, " ")}</span>
                      </div>
                    </div>
                    <div className="path-row-actions">
                      <button className="btn small" onClick={() => onOpenTarget(gate.native_target)}>
                        Open gate
                      </button>
                    </div>
                  </article>
                ))}
              </div>}
            {upcoming.remaining > 0 && (
              <button className="command-more" onClick={() => onOpenTarget({ tab: "plan" })}>
                View all {data.work.upcoming_gates.length}
              </button>
            )}
          </Card>
        </aside>
      </div>

      {snoozing && <PathSnooze item={snoozing} today={today}
        onClose={() => setSnoozing(null)} onDone={afterSnooze} />}
      {requirement && (
        <RequirementPanel row={requirement} accountId={accountId} today={today}
          coverage={data.coverage.readiness} onClose={() => setRequirement(null)}
          onOpenTarget={(target) => { setRequirement(null); onOpenTarget(target); }}
          onChanged={() => { reload(); onSaved?.(); }} track={track} />
      )}
    </>
  );
}
