/**
 * Requirement detail and the Account essentials gaps card (ACCOUNT-PATH-SPEC.md §13.6–§13.8).
 *
 * The panel reads a requirement and offers three writes, none of which is a state:
 *
 * - `Add evidence` navigates to the native record the evaluator reads.
 * - `Create action` opens a prefilled native Task or Commitment form, every field editable, and
 *   records an `advances` link to the condition on save (§13.8, §15.2). The link is a
 *   relationship, not evidence: closing the action settles the action and nothing else.
 * - `Mark not applicable` / `Waive` records a governed decision with an actor and a reason.
 *
 * There is deliberately no status control. Readiness is a projection with nothing for one to
 * write to, and a dropdown that appeared to set a state would be the stored second source of
 * truth `RELATIONSHIP-READINESS-SPEC.md` §2 forbids. `requirementControls` in
 * `../requirementDetail.js` enumerates the writes so a test can assert that absence.
 */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Empty, SlideOver, fmtDate, rowActivation, useToast } from "../ui";
import { RequirementLinks } from "./PathAdvance";
import { EvidenceItem } from "./Readiness";
import {
  dueRuleText, essentialsGaps, exceptionHistoryRows, linkedRecords, planStatus,
  recordedCompleteNote, requirementAxes, requirementControls, suppressedRequirements,
  trackedRequirements,
} from "../requirementDetail";

/** The four axes side by side. Four readings, four words, never one badge (§13.7). */
export function AxisReadings({ row, coverage }) {
  return (
    <dl className="req-axes">
      {requirementAxes(row, coverage).map((axis) => (
        <div key={axis.axis} className="req-axis">
          <dt>{axis.title}</dt>
          <dd>
            <span className={`state-mark ${axis.mark}`} aria-hidden="true" />
            {axis.label}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function PlanLine({ row, today }) {
  const status = planStatus(row, today);
  const rule = dueRuleText(row);
  return (
    <div className={`req-plan tone-${status.tone}`}>
      <span className={`state-mark ${status.tone === "risk" ? "risk" : "neutral"}`}
        aria-hidden="true" />
      <span>{status.text}</span>
      {/* The rule is kept beside the resolved date so a re-anchor is legible rather than
          looking like somebody hand-edited a date. */}
      {rule && <span className="rowmeta req-plan-rule">{rule}</span>}
    </div>
  );
}

/** A compact row for Account essentials. Opens the panel; it never edits in place. */
export function RequirementRow({ row, today, onOpen }) {
  const axes = requirementAxes(row);
  const status = planStatus(row, today);
  return (
    <div className="readiness-row clickable req-row" {...rowActivation(() => onOpen(row))}>
      <div className="readiness-row-head">
        <strong>{row.label || row.requirement_key}</strong>
        <span className="rowmeta">{row.pillar_label}</span>
        <div className="spacer" />
        <span className="state-badge">
          <span className={`state-mark ${axes[0].mark}`} aria-hidden="true" />{axes[0].label}
        </span>
      </div>
      <div className="rowmeta readiness-reason">{row.reason || "No assessment recorded."}</div>
      <div className="req-row-meta">
        <span className="rowmeta">{row.scope_label}{row.program_name ? ` · ${row.program_name}` : ""}</span>
        {/* Freshness stays visible next to state rather than folded into it. */}
        <span className="rowmeta">Freshness: {axes[1].label}</span>
        {status.due && (
          <span className={`path-urgency tone-${status.tone}`}>
            <span className={`state-mark ${status.tone === "risk" ? "risk" : "neutral"}`}
              aria-hidden="true" />
            {status.due_label}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * §13.6. At most three current-phase gaps in the order the server ranked them, with the route to
 * the full in-scope set. The cap is a presentation choice, so the remainder is always counted.
 */
export function AccountEssentialsGaps({ requirements, today, onOpenRequirement }) {
  const [expanded, setExpanded] = useState(false);
  if (!requirements) {
    return (
      <Card spotlight className="command-section command-tone-quiet path-group">
        <div className="card-h"><h3>Required now</h3></div>
        <Empty title="Requirements unavailable">
          The plan layer could not be read, so no requirement is shown. Nothing here should be
          taken as complete.
        </Empty>
      </Card>
    );
  }
  // The cap is presentation, so the remainder expands in place. Nothing mounts a full requirement
  // list yet, and routing "View all" at a tab that holds none of them would be a promise the app
  // cannot keep.
  const { shown, remaining } = essentialsGaps(requirements,
    expanded ? Number.MAX_SAFE_INTEGER : undefined);
  const hidden = essentialsGaps(requirements).remaining;
  const suppressed = suppressedRequirements(requirements);
  const tracked = trackedRequirements(requirements);
  const counts = requirements.counts || {};
  return (
    <Card spotlight className="command-section command-tone-quiet path-group req-essentials">
      <div className="card-h">
        <div>
          <h3>Required now</h3>
          <div className="rowmeta command-section-meta">
            Conditions this phase requires that are not yet evidenced. Not due and not applicable
            conditions are excluded — they are not chores.
          </div>
        </div>
        <div className="spacer" />
        {hidden > 0 && (
          <button className="btn small ghost" aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show fewer" : `View all ${shown.length + remaining}`}
          </button>
        )}
      </div>
      {shown.length === 0
        ? <Empty title="No current-phase gaps">
          Every condition this phase requires is evidenced, not yet due, or recorded as not
          applicable. Open a requirement for the evidence behind it.
        </Empty>
        : <div className="readiness-list">
          {shown.map((row) => (
            <RequirementRow key={row.id} row={row} today={today} onOpen={onOpenRequirement} />
          ))}
        </div>}
      {/* A tracked requirement is correctly absent from the gaps above — the work belongs to the
          linked record — but the gap list is the only thing that opens the requirement panel, and
          the panel is where evidence and gate links are managed. Without this disclosure, linking
          an action would hide the condition from the one surface that can unlink it. */}
      {tracked.length > 0 && (
        <details className="req-tracked">
          <summary className="rowmeta">
            Tracked by a linked action ({tracked.length}) — the action carries the work, not this
            list
          </summary>
          <div className="readiness-list">
            {tracked.map((row) => (
              <RequirementRow key={row.id} row={row} today={today} onOpen={onOpenRequirement} />
            ))}
          </div>
        </details>
      )}
      {/* A suppressed requirement is correctly absent from the gaps above, which would leave the
          decision that silenced it unreadable and un-revocable — a count is not a report. The
          disclosure is the only route to those rows, so it lists them rather than tallying them. */}
      {suppressed.length > 0 && (
        <details className="req-suppressed">
          <summary className="rowmeta">
            Not applicable and waived ({suppressed.length}) — suppressed, not evidenced
          </summary>
          <div className="readiness-list">
            {suppressed.map((row) => (
              <RequirementRow key={row.id} row={row} today={today} onOpen={onOpenRequirement} />
            ))}
          </div>
        </details>
      )}
      <div className="rowmeta readiness-foot">
        {counts.stale_but_met > 0 && (
          // A met condition with stale evidence is not a gap and is not listed as one. Saying so
          // keeps the staleness visible without inventing work (§13.6).
          <>{counts.stale_but_met} met condition{counts.stale_but_met === 1 ? " has" : "s have"}
            {" "}stale evidence — visible in the full list, not counted as a gap. </>
        )}
        Independent conditions, no combined score.
      </div>
    </Card>
  );
}

/** §13.7 — the governed suppression flow. A reason and an actor, or nothing is recorded. */
function ExceptionForm({ row, accountId, onClose, onDone }) {
  const toast = useToast();
  const [kind, setKind] = useState("not_applicable");
  const [reason, setReason] = useState("");
  const [expires, setExpires] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api.setReadinessException(accountId, {
        requirement_key: row.requirement_key, kind, reason: reason.trim(),
        program_id: row.program_id || null,
        expires_on: kind === "waiver" ? (expires || null) : null,
      });
      toast(kind === "waiver" ? "Waiver recorded" : "Marked not applicable");
      onDone();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlideOver title="Record a decision" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>Record decision</button>
    </>}>
      <div className="subtle" style={{ marginBottom: "var(--sp-5)" }}>
        {row.label || row.requirement_key}
      </div>
      <div className="field">
        <label htmlFor="req-exception-kind">Decision</label>
        <select id="req-exception-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="not_applicable">Not applicable — this condition does not apply here</option>
          <option value="waiver">Waive — the gap is real and accepted for now</option>
        </select>
        <div className="hint">
          {kind === "not_applicable"
            ? "Removes the question. The requirement is reported as not applicable and is excluded "
              + "from its pillar, and no evidence or state changes."
            : "Keeps the state exactly as the evidence found it and only stops asking. A waiver is "
              + "not a substitute for the condition being met."}
        </div>
      </div>
      <div className="field">
        <label htmlFor="req-exception-reason">Reason</label>
        <textarea id="req-exception-reason" rows={3} value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why this condition does not apply, or why the gap is accepted" />
        <div className="hint">At least ten characters. It is stored with your name and the date.</div>
      </div>
      {kind === "waiver" && (
        <div className="field">
          <label htmlFor="req-exception-expiry">Expires on</label>
          <input id="req-exception-expiry" type="date" value={expires}
            onChange={(e) => setExpires(e.target.value)} />
          <div className="hint">
            Required. A waiver with no end date is a permanent gap wearing a temporary label.
          </div>
        </div>
      )}
    </SlideOver>
  );
}

function RevokeForm({ row, decision, onClose, onDone }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await api.revokeReadinessException(decision.id, { reason: reason.trim() });
      toast("Decision revoked");
      onDone();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }
  return (
    <SlideOver title="Revoke decision" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>Revoke</button>
    </>}>
      <div className="subtle" style={{ marginBottom: "var(--sp-5)" }}>
        {row.label || row.requirement_key}
      </div>
      <div className="field">
        <label htmlFor="req-revoke-reason">Reason</label>
        <textarea id="req-revoke-reason" rows={3} value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="What changed that makes this condition apply again" />
        <div className="hint">
          The original decision stays in the history with its own reason; this records why it
          stopped applying.
        </div>
      </div>
    </SlideOver>
  );
}

/**
 * §13.8. A prefilled native form, every field editable. The record it creates is an ordinary Task
 * or Commitment — Account Path does not own a parallel action type — and the panel does not claim
 * a durable requirement link, because the table that stores one lands in Slice 5.
 */
function CreateActionForm({ row, accountId, onClose, onDone }) {
  const toast = useToast();
  const prefill = row.create_action_prefill || {};
  const [detail, setDetail] = useState(null);
  const [type, setType] = useState(prefill.record_type === "commitment" ? "commitment" : "task");
  const [description, setDescription] = useState(prefill.title || "");
  const [programId, setProgramId] = useState(prefill.program_id || row.program_id || "");
  const [owner, setOwner] = useState("");
  const [responsible, setResponsible] = useState("");
  const [due, setDue] = useState(prefill.due_date || "");
  const [saving, setSaving] = useState(false);

  // Two calls, because they answer two different questions. The account detail supplies the
  // programs; the roster supplies the people. Internal colleagues are global records with a null
  // `account_id`, so the account's own people list contains none of them — reading owners from it
  // left the internal-owner select permanently empty while a commitment cannot be saved without
  // one. `api.persons` is the endpoint that already unions the account with the Valence roster.
  useEffect(() => {
    let live = true;
    Promise.all([api.account(accountId), api.persons(accountId)])
      .then(([account, roster]) => { if (live) setDetail({ ...account, people: roster }); })
      .catch((e) => { if (live) toast(e.message, "err"); });
    return () => { live = false; };
  }, [accountId]);

  const people = detail?.people || [];
  const internal = people.filter((p) => p.affiliation === "valence");
  const customer = people.filter((p) => p.affiliation !== "valence");
  const programs = detail?.programs || [];

  // §17.5 question 5 wants to know whether the app's suggestion is what the operator created, so
  // the measured fact is whether the prefilled wording survived — not whether one was offered.
  const fromSuggestion = Boolean(prefill.title) && description.trim() === prefill.title;

  async function save() {
    setSaving(true);
    try {
      if (!programId) throw new Error("Pick a program — a task is recorded against one.");
      if (!description.trim()) throw new Error("Give the action a description.");
      let created;
      if (type === "commitment") {
        if (!responsible || !owner || !due) {
          throw new Error("A commitment needs a responsible party, an internal owner, and a due date.");
        }
        created = await api.createCommitment({
          program_id: programId, description: description.trim(),
          responsible_party_id: responsible, internal_owner_id: owner, due_date: due,
        });
      } else {
        created = await api.createTask({
          program_id: programId, description: description.trim(),
          internal_owner_id: owner || null, due_date: due || null,
        });
      }
      // Slice 5 gave this form somewhere to record the relationship, so it records one. The link
      // is attempted separately and reported separately: the record exists either way, and
      // claiming a link that failed would be worse than saying it did not happen.
      if (row.instance_id && created?.id) {
        try {
          await api.linkRequirementAction(row.instance_id, {
            [type === "commitment" ? "commitment_id" : "task_id"]: created.id,
            relation: "advances", origin: "operator",
            note: "Created from the requirement panel.",
          });
        } catch (linkError) {
          toast(`Created, but the link failed: ${linkError.message}`, "err");
          onDone({ actionType: type, fromSuggestion });
          return;
        }
      }
      toast(`${type === "commitment" ? "Commitment" : "Task"} created and linked`);
      onDone({ actionType: type, fromSuggestion });
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlideOver title="Create action" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={saving}>
        Create {type === "commitment" ? "commitment" : "task"}
      </button>
    </>}>
      <div className="callout req-link-note" role="status">
        This creates an ordinary {type === "commitment" ? "commitment" : "task"} and links it to
        this condition as <em>advances</em>. The link is a relationship, not evidence: closing the
        action settles the action, and readiness still reads the condition from the records.
      </div>
      <div className="field">
        <label htmlFor="req-action-type">Record</label>
        <select id="req-action-type" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="task">Task — internal work</option>
          <option value="commitment">Commitment — the customer performs it</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="req-action-desc">Description</label>
        <textarea id="req-action-desc" rows={2} value={description}
          onChange={(e) => setDescription(e.target.value)} />
        {prefill.detail && <div className="hint">{prefill.detail}</div>}
      </div>
      <div className="field">
        <label htmlFor="req-action-program">Program</label>
        <select id="req-action-program" value={programId}
          onChange={(e) => setProgramId(e.target.value)}>
          <option value="">Select a program…</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {!row.program_id && (
          <div className="hint">
            This requirement is account-wide; the action it produces is recorded against one program.
          </div>
        )}
      </div>
      <div className="field">
        <label htmlFor="req-action-owner">Internal owner</label>
        <select id="req-action-owner" value={owner} onChange={(e) => setOwner(e.target.value)}>
          <option value="">Unassigned</option>
          {internal.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      {type === "commitment" && (
        <div className="field">
          <label htmlFor="req-action-responsible">Responsible party</label>
          <select id="req-action-responsible" value={responsible}
            onChange={(e) => setResponsible(e.target.value)}>
            <option value="">Select…</option>
            {customer.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
      <div className="field">
        <label htmlFor="req-action-due">Due date</label>
        <input id="req-action-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        {prefill.due_date && (
          <div className="hint">Prefilled from the plan's expected date. Editable.</div>
        )}
      </div>
    </SlideOver>
  );
}

/**
 * §13.7. The whole panel. Every section is a fact the requirement already carries; nothing here
 * derives a new judgement, and no control writes a state.
 */
export function RequirementPanel({ row, accountId, coverage, today, onClose, onOpenTarget,
                                   onChanged, track }) {
  const [history, setHistory] = useState(null);
  const [flow, setFlow] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setHistory(null);
    api.readinessExceptions(accountId, row.requirement_key, row.program_id || null)
      .then((r) => { if (live) setHistory(r.history || []); })
      .catch(() => { if (live) setHistory([]); });
    return () => { live = false; };
  }, [accountId, row.requirement_key, row.program_id, nonce]);

  const live = row.applicability_override || row.waiver;
  const decisions = exceptionHistoryRows(history);
  // The suppression on the row is what actually silences the requirement, so it — not the
  // separately fetched history — decides whether a revocation is offered. The history only
  // supplies the identifier when the row carries no `exception_id`.
  const revokeTarget = live?.exception_id
    ? { id: live.exception_id }
    : decisions.find((d) => d.live);
  const note = recordedCompleteNote(row);
  const links = linkedRecords(row);

  function afterWrite(result) {
    // §17.3 `requirement_action_created`. Only the create flow reports one: an exception and a
    // revocation are governed decisions, not actions, and folding them in here would make the
    // count answer a question nobody asked.
    if (result?.actionType) {
      track?.("requirement_action_created", {
        pillar: row.pillar_key || null, action_type: result.actionType,
        from_suggestion: Boolean(result.fromSuggestion),
      });
    }
    setFlow(null);
    setNonce((n) => n + 1);
    onChanged?.();
  }

  return (
    <SlideOver title={row.label || row.requirement_key} onClose={onClose}>
      <div className="req-detail">
        <div className="rowmeta">
          {row.pillar_label} · {row.scope_label}
          {row.program_name ? ` · ${row.program_name}` : ""}
          {row.requirement_version ? ` · definition v${row.requirement_version}` : ""}
        </div>

        <AxisReadings row={row} coverage={coverage} />
        <p className="detail-title">{row.reason || "No assessment recorded."}</p>

        {row.necessity && (
          <div className="rowmeta">
            {row.necessity === "required"
              ? "The playbook marks this required for the phase."
              : "The playbook marks this optional; it is listed but never counted as a gap."}
          </div>
        )}

        <PlanLine row={row} today={today} />

        {row.definition_of_done && (
          <div className="rowmeta readiness-dod">Definition of done: {row.definition_of_done}</div>
        )}

        {note && (
          <div className={`callout ${note.tone === "warn" ? "warn" : ""} req-recorded`} role="status">
            {note.text} {note.caveat}
          </div>
        )}

        {live && (
          <div className="callout warn req-suppression" role="status">
            {row.waiver
              ? `Waived until ${row.waiver.expires_on || "no end date recorded"}: ${row.waiver.reason}`
              : `Marked not applicable: ${row.applicability_override.reason}`}
            {" "}
            <span className="rowmeta">
              Recorded by {live.actor_name || live.actor_id || "an operator"} on{" "}
              {fmtDate(live.decided_on)}. This suppresses the requirement; it does not evidence it.
            </span>
          </div>
        )}

        <h4 className="req-h">Accepted evidence</h4>
        {row.evidence?.length > 0
          ? <ul className="readiness-evidence">
            {row.evidence.map((e) => (
              <EvidenceItem key={`${e.type}:${e.id}`} evidence={e} onOpenTarget={onOpenTarget} />
            ))}
          </ul>
          : <div className="rowmeta">No accepted record evidences this condition yet.</div>}

        <h4 className="req-h">Missing evidence</h4>
        {row.missing?.length > 0
          ? <ul className="readiness-missing">{row.missing.map((m) => <li key={m}>{m}</li>)}</ul>
          : <div className="rowmeta">
            {live ? "Nothing outstanding is being asked while the decision above is in force."
              : "Nothing outstanding."}
          </div>}

        {links.length > 0 && (
          <>
            <h4 className="req-h">Linked records</h4>
            <ul className="readiness-evidence">
              {links.map((l) => (
                <li key={l.id}>
                  <span className="rowmeta">{l.kindLabel}</span>{" "}
                  {l.native_target
                    ? <button className="path-gate-link"
                      onClick={() => onOpenTarget(l.native_target)}>{l.label}</button>
                    // No tab knows how to show this kind, so it reads as a line rather than as a
                    // control that does nothing when clicked.
                    : <span>{l.label}</span>}
                </li>
              ))}
            </ul>
          </>
        )}

        {/* Slice 5's durable relationships. The instance id is what the link tables key on, so a
            requirement with no plan instance — an unscheduled condition — has nothing to link to
            and correctly shows no section rather than an empty one. */}
        {row.instance_id && (
          <RequirementLinks planInstanceId={row.instance_id} accountId={accountId}
            onOpenTarget={onOpenTarget} onChanged={onChanged} />
        )}

        {row.suggested_action && (
          // Visually distinct from the linked records above on purpose (§13.9): a suggestion is a
          // proposal until an operator accepts it, and must not read as work already on a list.
          <div className="readiness-suggestion req-suggestion">
            <span className="rowmeta">Suggested — not created, not assigned to anyone</span>
            <div>{row.suggested_action.title}</div>
            {row.suggested_action.detail && (
              <div className="rowmeta">{row.suggested_action.detail}</div>
            )}
          </div>
        )}

        <h4 className="req-h">Applicability and waiver history</h4>
        {history === null
          ? <div className="rowmeta">Loading…</div>
          : decisions.length === 0
            ? <div className="rowmeta">No decision has been recorded for this requirement.</div>
            : <ul className="req-history">
              {decisions.map((d) => (
                <li key={d.id} className={d.live ? "is-live" : ""}>
                  <span className="state-badge">
                    <span className={`state-mark ${d.live ? "warn" : "neutral"}`} aria-hidden="true" />
                    {d.kindLabel} · {d.statusLabel}
                  </span>
                  <div className="rowmeta">
                    {fmtDate(d.decided_on)} · {d.actor_name || d.actor_id || "operator"}
                    {d.expires_on ? ` · expires ${fmtDate(d.expires_on)}` : ""}
                  </div>
                  <div>{d.reason}</div>
                  {d.revoked_reason && (
                    <div className="rowmeta">Revoked: {d.revoked_reason}</div>
                  )}
                </li>
              ))}
            </ul>}

        {/* Rendered from `requirementControls` rather than hand-written here, so the list a test
            asserts writes no state is the same list that ships. */}
        <div className="actions req-actions">
          {requirementControls(row).map((control) => (
            <button key={control.key} title={control.hint}
              className={control.kind === "governed" ? "btn ghost" : "btn"}
              onClick={() => {
                if (control.key === "add_evidence") onOpenTarget({ tab: "ledger" });
                else if (control.key === "create_action") setFlow("create");
                else if (control.key === "revoke_exception") setFlow("revoke");
                else setFlow("exception");
              }}>
              {control.label}
            </button>
          ))}
        </div>
        <div className="rowmeta req-no-status">
          There is no status control here. The state above is derived from records, so it is
          changed by recording evidence — never by setting it.
        </div>
      </div>

      {flow === "exception" && (
        <ExceptionForm row={row} accountId={accountId} onClose={() => setFlow(null)}
          onDone={afterWrite} />
      )}
      {flow === "revoke" && revokeTarget && (
        <RevokeForm row={row} decision={revokeTarget} onClose={() => setFlow(null)}
          onDone={afterWrite} />
      )}
      {flow === "create" && (
        <CreateActionForm row={row} accountId={accountId} onClose={() => setFlow(null)}
          onDone={afterWrite} />
      )}
    </SlideOver>
  );
}

export default RequirementPanel;
