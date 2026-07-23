import { useEffect, useState } from "react";
import { api } from "../api";
import { PhaseBadge, StanceLabel, Empty, SlideOver, useToast, fmtDate, ROLE_LABELS } from "../ui";
import DeliveryPanel from "./DeliveryPanel";

export default function ProgramDetail({ programId, onQuickEntry, reloadKey }) {
  const toast = useToast();
  const [prog, setProg] = useState(null);
  const [brief, setBrief] = useState(null);

  async function load() {
    try { setProg(await api.program(programId)); }
    catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [programId, reloadKey]);

  if (!prog) return <div className="subtle">Loading…</div>;

  const ExecutionSummary = ({ ex }) => {
    if (!ex) return null;
    const openCount = (arr, key = "status", open = "open") => arr.filter((x) => x[key] === open).length;
    const line = (label, rows, render) =>
      rows.length ? (
        <div style={{ marginBottom: 8 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</div>
          {rows.map(render)}
        </div>
      ) : null;
    const any = ex.commitments.length + ex.risks.length + ex.issues.length + ex.milestones.length + ex.tasks.length + ex.decisions.length;
    return (
      <div className="card">
        <div className="card-h"><h3>Execution</h3><div className="spacer" /><span className="rowmeta">close items on the Execution board</span></div>
        <div style={{ padding: 12 }}>
          {any === 0 && <span className="rowmeta">Nothing yet. Convert an inbox note or add items from a call.</span>}
          {line("Commitments", ex.commitments, (c) => (
            <div key={c.id}>{c.description} <span className="rowmeta">· due {fmtDate(c.due_date)} · {c.status}{c.overdue ? " · overdue" : ""}</span></div>
          ))}
          {line("Risks", ex.risks, (r) => (
            <div key={r.id}>{r.description} <span className="rowmeta">· {r.severity}{r.is_blocker ? " · blocker" : ""} · {r.status}</span></div>
          ))}
          {line("Issues", ex.issues, (i) => (
            <div key={i.id}>{i.description} <span className="rowmeta">· {i.status}</span></div>
          ))}
          {line("Milestones", ex.milestones, (m) => (
            <div key={m.id}>{m.name} <span className="rowmeta">· {fmtDate(m.target_date)} · {m.status}{m.derived_at_risk ? " · at risk" : ""}</span></div>
          ))}
          {line("Tasks", ex.tasks, (t) => (
            <div key={t.id}>{t.description} <span className="rowmeta">· {t.status}</span></div>
          ))}
          {line("Decisions", ex.decisions, (d) => (
            <div key={d.id}>{d.description} <span className="rowmeta">· {d.status}</span></div>
          ))}
        </div>
      </div>
    );
  };

  const field = (label, value) => value ? (
    <div style={{ marginBottom: 8 }}>
      <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</div>
      <div>{value}</div>
    </div>
  ) : null;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 6 }}>
        <h1>{prog.name}</h1>
        <PhaseBadge phase={prog.phase} />
        <div className="spacer" />
        <button className="btn" onClick={async () => { try { setBrief(await api.brief(prog.id)); } catch (e) { toast(e.message, "err"); } }}>Prep brief</button>
        <button className="btn primary" onClick={() => onQuickEntry(prog.account_id, prog.id)}>Log interaction</button>
      </div>
      <div className="rowmeta" style={{ marginBottom: 4 }}>
        {[prog.region, prog.audience, prog.use_case].filter(Boolean).join(" · ") || "—"}
      </div>
      {(prog.governance_steering || prog.governance_rhythm || prog.next_qbr_date) && (
        <div className="rowmeta" style={{ marginBottom: 14 }}>
          Governance: {[prog.governance_steering, prog.governance_rhythm, prog.next_qbr_date && `next QBR ${prog.next_qbr_date}`].filter(Boolean).join(" · ")}
        </div>
      )}

      <div className="two-col">
        <div>
          <div className="card">
            <div className="card-h"><h3>Scope</h3></div>
            <div style={{ padding: 12 }}>
              {field("Problem", prog.problem_statement)}
              {field("In scope", prog.in_scope_population)}
              {field("Out of scope", prog.out_of_scope_population)}
              {field("Launch definition", prog.launch_definition)}
              {field("Success criteria", prog.success_criteria)}
              {field("Expansion hypothesis", prog.expansion_hypothesis)}
              {field("Explicit exclusions", prog.explicit_exclusions)}
              {!prog.problem_statement && !prog.success_criteria && (
                <span className="rowmeta">No scope captured yet.</span>
              )}
            </div>
          </div>

          <ExecutionSummary ex={prog.execution} />

          <div className="card">
            <div className="card-h"><h3>Interactions</h3></div>
            {prog.interactions.length === 0 ? (
              <Empty title="No interactions yet">Log a call to build the history.</Empty>
            ) : (
              <table>
                <thead><tr><th style={{width:96}}>Date</th><th style={{width:80}}>Type</th><th>Summary</th></tr></thead>
                <tbody>
                  {prog.interactions.map((it) => (
                    <tr key={it.id}>
                      <td className="rowmeta">{fmtDate(it.occurred_on)}</td>
                      <td><span className="badge">{it.type}</span></td>
                      <td>{it.summary || <span className="rowmeta">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-h"><h3>Stakeholders</h3></div>
          {prog.stakeholders.length === 0 ? (
            <Empty title="No stakeholders yet">Add people with a role and dated stance.</Empty>
          ) : (
            <table>
              <thead><tr><th>Person</th><th>Role</th><th>Stance</th></tr></thead>
              <tbody>
                {prog.stakeholders.map((s) => (
                  <tr key={s.id}>
                    <td>{s.person_name}{s.person_title ? <div className="rowmeta">{s.person_title}</div> : null}</td>
                    <td className="rowmeta">{ROLE_LABELS[s.role] || s.role}</td>
                    <td>
                      <StanceLabel stance={s.stance} />
                      {s.stance && <div className="rowmeta">as of {fmtDate(s.stance_assessed_on)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="rowmeta" style={{ padding: "8px 12px" }}>
            Stance judgments are internal only and always dated with evidence.
          </div>
        </div>
      </div>

      <h2>Delivery control</h2>
      <DeliveryPanel programId={prog.id} people={prog.stakeholders?.map((s) => ({ id: s.person_id, name: s.person_name })) || []} reloadKey={reloadKey} />

      {brief && (
        <SlideOver title="Pre-call brief" onClose={() => setBrief(null)}>
          <div className="rowmeta" style={{ marginBottom: 12 }}>{brief.label}</div>
          <h3>Who’s on the call</h3>
          {brief.stakeholders.length === 0 ? <div className="rowmeta">No stakeholders.</div> : brief.stakeholders.map((s, i) => (
            <div key={i} style={{ marginBottom: 6 }}>{s.name} <span className="rowmeta">· {s.role}{s.stance ? ` · ${s.stance}` : ""}</span>{s.cares_about ? <div className="rowmeta">cares about: {s.cares_about}</div> : null}</div>
          ))}
          <h3 style={{ marginTop: 16 }}>Open commitments</h3>
          {brief.open_commitments.length === 0 ? <div className="rowmeta">None.</div> : brief.open_commitments.map((c, i) => (
            <div key={i} className="rowmeta">{c.description} — due {fmtDate(c.due_date)}</div>
          ))}
          <h3 style={{ marginTop: 16 }}>Top risks</h3>
          {brief.top_risks.length === 0 ? <div className="rowmeta">None.</div> : brief.top_risks.map((r, i) => (
            <div key={i} className="rowmeta">{r.is_blocker ? "🚩 " : ""}{r.description} ({r.severity})</div>
          ))}
          {brief.last_interaction && <div className="rowmeta" style={{ marginTop: 16 }}>Last touch: {fmtDate(brief.last_interaction.occurred_on)} — {brief.last_interaction.summary}</div>}
        </SlideOver>
      )}
    </div>
  );
}
