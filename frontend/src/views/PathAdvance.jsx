/**
 * Account Path Slice 5 surfaces (ACCOUNT-PATH-SPEC.md §15.8).
 *
 * Five things this file renders, and the rule each one exists to keep:
 *
 * - `AdvancementVerdict` — `Ready to advance`, `Blocked`, or `Evidence missing`, always with the
 *   reasons. The word comes from the server; nothing here computes a verdict.
 * - `PhaseAdvanceDialog` — the exact consequences before anything moves, and on an override the
 *   list of conditions being accepted. It sends the readiness stamp it was rendered from, so an
 *   advance is checked against the answer the operator actually read.
 * - `RequirementLinks` — linked actions and attached evidence, with the governed writes. No
 *   control here writes a readiness state; there is nowhere to write one.
 * - `ActionPathContext` — the inverse read on an action's own detail: the requirement, milestone,
 *   or gate it advances, and the plain statement that closing it settles the action only.
 * - `DependencyLines` — explicit milestone/action relations, rendered secondary. Nothing is
 *   inferred from a shared date, a shared owner, or matching text.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Empty, SlideOver, useToast } from "../ui";
import {
  actionAdvances, actionLinkGroups, advancementVerdict, dependencyLines, evidenceRows,
  overrideConsequences, unblocksReason,
} from "../pathLinks";

/** §15.8 third bullet. The verdict word, its shape, and every reason behind it. */
export function AdvancementVerdict({ payload, onAdvance, onPropose }) {
  if (!payload) return null;
  const v = advancementVerdict(payload);
  return (
    <Card className={`path-verdict tone-${v.tone}`}>
      <div className="card-h">
        <div>
          <div className="page-eyebrow">GATE FOR {String(payload.current_phase_label || "")
            .toUpperCase()}</div>
          <h3>
            <span className={`state-mark ${v.mark}`} aria-hidden="true" />
            <span className="path-verdict-symbol" aria-hidden="true">{v.symbol}</span>
            {v.label}
          </h3>
        </div>
        <div className="spacer" />
        {payload.proposed_next_phase && (
          <div className="actions">
            {/* Offered whatever the verdict says. Proposing records the intent without moving
                anything, which is exactly what a blocked team wants on the record. */}
            <button className="btn ghost" onClick={onPropose}>Record intent to advance</button>
            <button className="btn primary" onClick={onAdvance}>
              Advance to {payload.proposed_next_phase_label || payload.proposed_next_phase}
            </button>
          </div>
        )}
      </div>
      <p className="path-verdict-summary">{v.summary}</p>
      <div className="rowmeta">{v.caveat}</div>
      {v.reasons.length > 0 && (
        <ul className="path-verdict-reasons">
          {v.reasons.map((reason) => (
            <li key={reason.key} className={`is-${reason.key}`}>
              <strong>{reason.text}</strong>
              <ul>{reason.items.map((item, i) => <li key={`${reason.key}:${i}`}>{item}</li>)}</ul>
            </li>
          ))}
        </ul>
      )}
      <div className="rowmeta path-verdict-foot">
        Read {payload.as_of}. Reading this moved nothing — the phase changes only when someone
        advances it.
      </div>
    </Card>
  );
}

/**
 * §15.8 fourth bullet. Every required condition and the exact consequences, before the move.
 *
 * The override branch is deliberately not a checkbox with a tooltip: ticking it re-renders the
 * consequence list into the three sentences that say what an override does *not* do, so the
 * operator reads them in the same place they confirm.
 */
export function PhaseAdvanceDialog({ payload, programId, onClose, onDone }) {
  const toast = useToast();
  const [override, setOverride] = useState(false);
  const [reason, setReason] = useState("");
  const [target, setTarget] = useState(payload.proposed_next_phase || "");
  const [saving, setSaving] = useState(false);
  const satisfied = payload.readiness === "ready" || payload.readiness === "passed";
  const consequences = overrideConsequences(payload, { override });
  const adjacent = target === payload.proposed_next_phase;
  const needsReason = override || !adjacent;

  async function save() {
    setSaving(true);
    try {
      await api.createPhaseTransition(programId, {
        outcome: "completed",
        expected_current_phase: payload.current_phase,
        requested_next_phase: target,
        // The stamp of the answer on screen. If anything changed underneath, the server refuses
        // rather than advancing against conditions nobody read.
        readiness_stamp: payload.readiness_stamp,
        override, reason: reason.trim() || null,
      });
      toast(override ? "Phase advanced with an override" : "Phase advanced");
      onDone({ advanced: true, toPhase: target, override });
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlideOver title={consequences.heading} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className={`btn ${override ? "" : "primary"}`} onClick={save}
        disabled={saving || (needsReason && reason.trim().length < 10)}>
        {override ? "Override and advance" : "Advance"}
      </button>
    </>}>
      <div className="field">
        <label htmlFor="advance-target">Move to</label>
        <select id="advance-target" value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value={payload.proposed_next_phase}>
            {payload.proposed_next_phase_label || payload.proposed_next_phase} — the next phase
          </option>
          {(payload.phase_options || []).filter((p) => p.key !== payload.proposed_next_phase
            && p.key !== payload.current_phase).map((p) => (
            <option key={p.key} value={p.key}>{p.label} — not the next phase</option>
          ))}
        </select>
        {!adjacent && (
          <div className="hint">
            A non-adjacent move is an override and needs a reason, whatever the gate says.
          </div>
        )}
      </div>

      {!satisfied && !override && (
        <div className="callout risk" role="status">
          This gate is not satisfied, so the phase cannot advance normally. Recording an override
          below is the only way through, and it accepts the gap rather than closing it.
        </div>
      )}

      <h4 className="req-h">What this does</h4>
      <ul className="path-consequences">
        {consequences.consequences.map((c) => (
          <li key={c.key} className={`tone-${c.tone}`}>
            <span className={`state-mark ${c.tone === "risk" ? "risk" : "neutral"}`}
              aria-hidden="true" />
            {c.text}
          </li>
        ))}
      </ul>

      <div className="field">
        <label className="check">
          <input type="checkbox" checked={override}
            onChange={(e) => { setOverride(e.target.checked); }} />
          Override — advance even though the conditions are not satisfied
        </label>
        <div className="hint">
          An override is recorded permanently with your reason and the conditions as they read now.
        </div>
      </div>

      {override && (
        <>
          <h4 className="req-h">Conditions this override accepts</h4>
          {consequences.unmet.length === 0
            ? <div className="rowmeta">
              Nothing is outstanding. An override here only records that the move was made
              deliberately outside the normal path.
            </div>
            : <ul className="path-unmet">
              {consequences.unmet.map((u) => (
                <li key={u.key}>
                  <span className="state-mark risk" aria-hidden="true" />
                  <strong>{u.label}</strong>
                  {u.detail && <span className="rowmeta"> — {u.detail}</span>}
                </li>
              ))}
            </ul>}
        </>
      )}

      {needsReason && (
        <div className="field">
          <label htmlFor="advance-reason">Reason</label>
          <textarea id="advance-reason" rows={3} value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why the program is moving on with these conditions outstanding" />
          <div className="hint">At least ten characters. Stored with your name, permanently.</div>
        </div>
      )}
    </SlideOver>
  );
}

/** Recording the intent without moving anything — the honest submit when the gate is blocked. */
export function ProposeAdvanceDialog({ payload, programId, onClose, onDone }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await api.createPhaseTransition(programId, {
        outcome: "proposed", requested_next_phase: payload.proposed_next_phase,
        note: note.trim() || null,
      });
      toast("Intent recorded. The phase did not change.");
      onDone();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }
  return (
    <SlideOver title="Record intent to advance" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>Record intent</button>
    </>}>
      <div className="callout" role="status">
        This changes nothing. It appends to the phase history that the team expected to reach{" "}
        {payload.proposed_next_phase_label || payload.proposed_next_phase} now, together with the
        conditions as they read today — so a later review can see when the expectation was set and
        what was in the way.
      </div>
      <div className="field">
        <label htmlFor="propose-note">Note</label>
        <textarea id="propose-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Optional — what the team is waiting on" />
      </div>
    </SlideOver>
  );
}

/** The append-only history. Every proposal, completion, waiver, override, and refusal. */
export function PhaseHistory({ events }) {
  if (!events?.length) {
    return <div className="rowmeta">No phase transition has been recorded for this program.</div>;
  }
  const LABEL = { completed: "Advanced", proposed: "Proposed", waived: "Gate waived",
    rejected: "Refused" };
  return (
    <ul className="path-history">
      {events.map((e) => (
        <li key={e.id} className={e.is_override ? "is-override" : ""}>
          <span className="state-badge">
            <span className={`state-mark ${e.is_override ? "warn"
              : e.outcome === "rejected" ? "risk" : "neutral"}`} aria-hidden="true" />
            {LABEL[e.outcome] || e.outcome}
            {e.is_override ? " · override" : ""}
          </span>
          <div className="rowmeta">
            {e.from_phase} → {e.to_phase} · {String(e.created_at || "").slice(0, 10)}
            {e.actor_id ? ` · ${e.actor_id}` : ""}
          </div>
          {e.reason && <div>{e.reason}</div>}
          {/* Named as a snapshot of a decision, never as a status. Readiness recomputes these
              conditions on every read and is the only thing that says what is true now. */}
          {e.unmet_at_transition?.length > 0 && (
            <details>
              <summary className="rowmeta">
                {e.unmet_at_transition.length} condition
                {e.unmet_at_transition.length === 1 ? " was" : "s were"} outstanding at the time
              </summary>
              <ul>
                {e.unmet_at_transition.map((u, i) => (
                  <li key={i}>{u.label}{u.state ? ` — ${u.state}` : ""}</li>
                ))}
              </ul>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

// --- requirement relationships -------------------------------------------------------------------

/** §15.8 first bullet. Linked actions, attached evidence, and the gates that depend on this. */
export function RequirementLinks({ planInstanceId, accountId, onOpenTarget, onChanged }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [flow, setFlow] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setData(null);
    api.requirementLinks(planInstanceId)
      .then((r) => { if (live) setData(r); })
      .catch(() => { if (live) setData({ actions: [], evidence: [], gates: [], failed: true }); });
    return () => { live = false; };
  }, [planInstanceId, nonce]);

  function reload() {
    setFlow(null);
    setNonce((n) => n + 1);
    onChanged?.();
  }

  if (!data) return <div className="rowmeta">Loading linked records…</div>;
  if (data.failed) {
    return (
      <div className="callout warn" role="status">
        Linked records could not be read. Nothing here should be taken to mean this requirement has
        no links.
      </div>
    );
  }

  const groups = actionLinkGroups(data.actions);
  const evidence = evidenceRows(data.evidence);

  return (
    <div className="req-links">
      <h4 className="req-h">
        Linked actions
        <button className="btn small ghost" onClick={() => setFlow({ kind: "link" })}>
          Link an action
        </button>
      </h4>
      {groups.length === 0
        ? <div className="rowmeta">
          No Task or Commitment is linked to this condition. A link is an explicit decision —
          nothing is matched by wording.
        </div>
        : groups.map((group) => (
          <div key={group.relation} className="req-link-group">
            <div className="rowmeta">{group.label}</div>
            <ul className="readiness-evidence">
              {group.items.map((l) => (
                <li key={l.id} className={l.closed ? "is-closed" : ""}>
                  <button className="path-gate-link"
                    onClick={() => onOpenTarget({ tab: l.action.type === "task" ? "delivery" : "delivery",
                      focus: { type: l.action.type, id: l.action.id } })}>
                    {l.action.description || l.action.id}
                  </button>
                  <span className="rowmeta"> · {l.originLabel}
                    {l.closed ? " · closed" : ""}</span>
                  {l.note && <div className="rowmeta">{l.note}</div>}
                  <button className="btn small ghost"
                    onClick={() => setFlow({ kind: "unlink_action", link: l })}>Unlink</button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      {groups.some((g) => g.items.some((i) => i.closed)) && (
        <div className="rowmeta">
          A closed action stays listed. Closing settles the action; the condition is still whatever
          the records say it is.
        </div>
      )}

      <h4 className="req-h">
        Attached evidence
        <button className="btn small ghost" onClick={() => setFlow({ kind: "attach" })}>
          Attach evidence
        </button>
      </h4>
      {evidence.length === 0
        ? <div className="rowmeta">Nothing is attached to this condition yet.</div>
        : <ul className="readiness-evidence req-evidence">
          {evidence.map((e) => (
            <li key={e.id} className={e.retracted ? "is-retracted" : ""}>
              <span className={`state-mark ${e.mark}`} aria-hidden="true" />
              <span className="rowmeta">{e.typeLabel}</span> {e.label || e.evidence_id}
              <div className="rowmeta" title={e.supportingHint}>
                {e.supportingLabel} · {e.reviewLabel}
              </div>
              {!e.supporting && !e.retracted && (
                // The whole point of the flag. Attached and visible, and unable to move the state.
                <div className="rowmeta">{e.supportingHint}</div>
              )}
              {(e.canReview || e.canRetract) && (
                <div className="actions">
                  {e.canReview && (
                    <button className="btn small ghost"
                      onClick={() => setFlow({ kind: "review", link: e })}>Record a review</button>
                  )}
                  {e.canRetract && (
                    <button className="btn small ghost"
                      onClick={() => setFlow({ kind: "retract", link: e })}>Retract</button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>}

      <h4 className="req-h">Gates that depend on this</h4>
      {data.gates.length === 0
        ? <div className="rowmeta">No phase gate lists this condition.</div>
        : <ul className="readiness-evidence">
          {data.gates.map((g) => (
            <li key={g.id}>
              <strong>{g.gate_name}</strong>
              <span className="rowmeta"> · {g.gates_phase} · {g.necessity} · {g.gate_status}</span>
              {g.necessity !== "required" && (
                <div className="rowmeta">Optional here, so this gate does not wait on it.</div>
              )}
            </li>
          ))}
        </ul>}

      {flow?.kind === "link" && (
        <LinkActionForm planInstanceId={planInstanceId} accountId={accountId}
          onClose={() => setFlow(null)} onDone={reload} />
      )}
      {flow?.kind === "attach" && (
        <AttachEvidenceForm planInstanceId={planInstanceId} onClose={() => setFlow(null)}
          onDone={reload} />
      )}
      {flow?.kind === "review" && (
        <ReasonForm title="Record a review" label="Reviewed on" dated
          hint="A review is a dated statement that somebody looked at this record and still
                accepts it. It does not change the requirement's state."
          onClose={() => setFlow(null)}
          onSubmit={(body) => api.reviewRequirementEvidence(flow.link.id, body).then(reload)} />
      )}
      {flow?.kind === "retract" && (
        <ReasonForm title="Retract evidence"
          hint="The attachment stays in the history with its reason. Readiness stops counting it
                from the next read."
          onClose={() => setFlow(null)}
          onSubmit={(body) => api.retractRequirementEvidence(flow.link.id, body).then(reload)} />
      )}
      {flow?.kind === "unlink_action" && (
        <ReasonForm title="Unlink action"
          hint="The link is archived rather than deleted, because it may already have influenced a
                gate or a transition."
          onClose={() => setFlow(null)}
          onSubmit={(body) => api.archiveRequirementActionLink(flow.link.id, body).then(reload)} />
      )}
    </div>
  );
}

/** A reason (and optionally a date) or nothing is recorded. Used by every archival-style write. */
function ReasonForm({ title, hint, label = "Reason", dated = false, onClose, onSubmit }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [date, setDate] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await onSubmit(dated
        ? { reviewed_on: date, review_note: reason.trim() }
        : { reason: reason.trim() });
      toast(`${title} recorded`);
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }
  return (
    <SlideOver title={title} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save}
        disabled={saving || (dated && !date)}>Record</button>
    </>}>
      <div className="callout" role="status">{hint}</div>
      {dated && (
        <div className="field">
          <label htmlFor="reason-date">{label}</label>
          <input id="reason-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
      )}
      <div className="field">
        <label htmlFor="reason-text">{dated ? "Note" : label}</label>
        <textarea id="reason-text" rows={3} value={reason}
          onChange={(e) => setReason(e.target.value)} />
      </div>
    </SlideOver>
  );
}

/** §15.2 — a link is an explicit operator action against a real record, in scope, chosen by hand. */
function LinkActionForm({ planInstanceId, accountId, onClose, onDone }) {
  const toast = useToast();
  const [options, setOptions] = useState(null);
  const [kind, setKind] = useState("task");
  const [id, setId] = useState("");
  const [relation, setRelation] = useState("advances");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  // One read of the account's whole execution board. Scope is the server's to enforce — it
  // rejects a link that crosses an account or a program — so the picker's job is only to offer
  // real records rather than a free-text id.
  useEffect(() => {
    let live = true;
    api.accountExecution(accountId)
      .then((r) => {
        if (live) setOptions({ task: r.tasks || [], commitment: r.commitments || [] });
      })
      .catch((e) => { if (live) { setOptions({ task: [], commitment: [] }); toast(e.message, "err"); } });
    return () => { live = false; };
  }, [accountId]);

  async function save() {
    setSaving(true);
    try {
      if (!id) throw new Error("Pick the record this link points at.");
      await api.linkRequirementAction(planInstanceId, {
        [kind === "task" ? "task_id" : "commitment_id"]: id,
        relation, origin: "operator", note: note.trim() || null,
      });
      toast("Action linked");
      onDone();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  const list = options?.[kind] || [];
  return (
    <SlideOver title="Link an action" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>Link</button>
    </>}>
      <div className="callout" role="status">
        Linking records that this action relates to the condition. It does not evidence the
        condition — closing the action will not set a state.
      </div>
      <div className="field">
        <label htmlFor="link-kind">Record</label>
        <select id="link-kind" value={kind} onChange={(e) => { setKind(e.target.value); setId(""); }}>
          <option value="task">Task</option>
          <option value="commitment">Commitment</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="link-id">{kind === "task" ? "Task" : "Commitment"}</label>
        <select id="link-id" value={id} onChange={(e) => setId(e.target.value)}>
          <option value="">Select…</option>
          {list.map((r) => (
            <option key={r.id} value={r.id}>
              {r.description}{r.status && r.status !== "open" ? ` (${r.status})` : ""}
            </option>
          ))}
        </select>
        {options && list.length === 0 && (
          <div className="hint">No {kind} is available on this account.</div>
        )}
      </div>
      <div className="field">
        <label htmlFor="link-relation">Relation</label>
        <select id="link-relation" value={relation} onChange={(e) => setRelation(e.target.value)}>
          <option value="advances">Advances — this work moves the condition forward</option>
          <option value="blocks">Blocks — the condition cannot progress until this is settled</option>
          <option value="follow_up_for">Follow-up for — it arose from the condition</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="link-note">Note</label>
        <textarea id="link-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Optional — why these are related" />
      </div>
    </SlideOver>
  );
}

/** §15.3 — the evidence kinds the write path accepts, offered exactly as the server lists them. */
function AttachEvidenceForm({ planInstanceId, onClose, onDone }) {
  const toast = useToast();
  const [types, setTypes] = useState(null);
  const [type, setType] = useState("");
  const [id, setId] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    api.evidenceTypes().then((r) => { if (live) setTypes(r); })
      .catch((e) => { if (live) toast(e.message, "err"); });
    return () => { live = false; };
  }, []);

  async function save() {
    setSaving(true);
    try {
      if (!type || !id.trim()) throw new Error("An evidence type and a record are both required.");
      const r = await api.attachRequirementEvidence(planInstanceId, {
        evidence_type: type, evidence_id: id.trim(), note: note.trim() || null,
      });
      toast(r.evidence?.supporting
        ? "Evidence attached"
        : "Attached as context — this kind cannot change the condition's state.");
      onDone();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlideOver title="Attach evidence" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>Attach</button>
    </>}>
      <div className="callout" role="status">
        Attaching does not set a state. If the requirement's definition accepts this kind of
        record, readiness reads it on the next evaluation; if it does not, the record is kept as
        context and says so.
      </div>
      <div className="field">
        <label htmlFor="ev-type">Evidence type</label>
        <select id="ev-type" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Select…</option>
          {(types?.evidence_types || []).map((t) => (
            <option key={t} value={t}>{String(t).replace(/_/g, " ")}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="ev-id">Record</label>
        <input id="ev-id" value={id} onChange={(e) => setId(e.target.value)}
          placeholder={type.endsWith("_field") ? "Field name" : "Record id"} />
        {type.endsWith("_field") && types && (
          <div className="hint">
            Allowed: {(type === "account_field" ? types.account_fields : types.program_fields || [])
              .join(", ")}
          </div>
        )}
      </div>
      <div className="field">
        <label htmlFor="ev-note">Note</label>
        <textarea id="ev-note" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Optional — what this record shows" />
      </div>
    </SlideOver>
  );
}

// --- the inverse read ----------------------------------------------------------------------------

/**
 * §15.8 second bullet. On a Task's or Commitment's own detail: what it advances.
 *
 * The `Unblocks …` line is rendered only when an explicit required gate relation supports it, and
 * it names the requirement it travels through, so the claim carries its own warrant.
 */
export function ActionPathContext({ actionType, actionId }) {
  const [ctx, setCtx] = useState(null);
  useEffect(() => {
    let live = true;
    setCtx(null);
    api.actionPathContext(actionType, actionId)
      .then((r) => { if (live) setCtx(r); })
      .catch(() => { if (live) setCtx({ failed: true }); });
    return () => { live = false; };
  }, [actionType, actionId]);

  if (!ctx) return <div className="rowmeta">Loading…</div>;
  if (ctx.failed) {
    return <div className="rowmeta">
      What this advances could not be read. Treat the absence as unknown, not as none.
    </div>;
  }
  const rows = actionAdvances(ctx);
  const unblocks = unblocksReason(ctx);
  if (rows.length === 0) {
    return (
      <div className="rowmeta">
        This action is not linked to a requirement, milestone, or gate. Link it from the
        requirement to make the relationship durable.
      </div>
    );
  }
  return (
    <div className="path-action-context">
      {unblocks && (
        <div className="callout" role="status">
          <strong>{unblocks.text}</strong>
          <div className="rowmeta">
            Through the {unblocks.through_requirement} condition, which that gate marks required.
            The claim comes from an accepted link, not from wording.
          </div>
        </div>
      )}
      <ul className="readiness-evidence">
        {rows.map((r) => (
          <li key={`${r.kind}:${r.id}`}>
            <span className="rowmeta">{r.kindLabel} · {r.relationLabel}</span> {r.label}
            {r.detail && <div className="rowmeta">{r.detail}</div>}
            {r.caveat && <div className="rowmeta">{r.caveat}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * §15.8 fifth bullet. Explicit relations only, rendered secondary so a dependency never competes
 * with the milestone it hangs off. An empty result draws nothing rather than inferring a line.
 */
export function DependencyLines({ milestoneId, onOpenTarget }) {
  const [links, setLinks] = useState(null);
  useEffect(() => {
    let live = true;
    setLinks(null);
    api.milestoneActionLinks(milestoneId)
      .then((r) => { if (live) setLinks(r.links || []); })
      .catch(() => { if (live) setLinks([]); });
    return () => { live = false; };
  }, [milestoneId]);

  const lines = dependencyLines(links);
  if (!links || lines.length === 0) return null;
  return (
    <ul className="path-deps">
      {lines.map((line) => (
        <li key={line.id} className={`path-dep is-${line.emphasis}${line.blocking ? " is-blocking" : ""}`}>
          <span className="path-dep-rule" aria-hidden="true" />
          <span className="rowmeta">{line.relationLabel}</span>
          <button className="path-gate-link"
            onClick={() => onOpenTarget?.({ tab: "delivery",
              focus: { type: line.action?.type, id: line.action?.id } })}>
            {line.label}
          </button>
          {line.note && <span className="rowmeta"> — {line.note}</span>}
        </li>
      ))}
    </ul>
  );
}

/** The gate-readiness band for one program: the verdict, both dialogs, and the history. */
export default function PhaseGateReadiness({ programId, onChanged, track }) {
  const [payload, setPayload] = useState(null);
  const [history, setHistory] = useState(null);
  const [flow, setFlow] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setPayload(null);
    Promise.all([api.phaseReadiness(programId), api.phaseTransitions(programId)])
      .then(([r, h]) => { if (live) { setPayload(r); setHistory(h.events || h.history || []); } })
      .catch(() => { if (live) setPayload({ failed: true }); });
    return () => { live = false; };
  }, [programId, nonce]);

  // §17.3 `phase_readiness_opened` — §17.5 question 6, whether gates reach a ready state before
  // their target dates. A failed read reports itself as `unavailable` rather than not reporting:
  // a gate nobody could evaluate is a different answer from a gate with no blockers.
  useEffect(() => {
    if (!payload || !track) return;
    track("phase_readiness_opened", payload.failed
      ? { gate_state: "unavailable", next_phase: null, blocking_count: 0 }
      : {
        gate_state: payload.readiness || "unknown",
        next_phase: payload.proposed_next_phase || null,
        blocking_count: (payload.blocking_records || []).length,
      });
  }, [payload, track]);

  function reload(result) {
    // §17.3 `phase_transition_completed`. Only an actual advance reports one; a *proposal* records
    // an intent and moves nothing, so counting it here would overstate how often phases move.
    if (result?.advanced) {
      track?.("phase_transition_completed", {
        from_phase: payload?.current_phase || null, to_phase: result.toPhase || null,
        waived_count: (payload?.gates || []).filter((g) => g.status === "waived").length,
        override: Boolean(result.override),
      });
    }
    setFlow(null);
    setNonce((n) => n + 1);
    onChanged?.();
  }

  if (!payload) return <Card><div className="rowmeta">Reading the gate…</div></Card>;
  if (payload.failed) {
    return (
      <Card>
        <Empty title="Gate readiness unavailable">
          The gate could not be read, so nothing here should be treated as ready.
        </Empty>
      </Card>
    );
  }

  return (
    <>
      <AdvancementVerdict payload={payload}
        onAdvance={() => setFlow("advance")} onPropose={() => setFlow("propose")} />
      <Card className="path-history-card">
        <div className="card-h"><h3>Phase history</h3></div>
        <PhaseHistory events={history} />
      </Card>
      {flow === "advance" && (
        <PhaseAdvanceDialog payload={payload} programId={programId}
          onClose={() => setFlow(null)} onDone={reload} />
      )}
      {flow === "propose" && (
        <ProposeAdvanceDialog payload={payload} programId={programId}
          onClose={() => setFlow(null)} onDone={reload} />
      )}
    </>
  );
}
