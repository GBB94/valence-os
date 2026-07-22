import { useEffect, useState } from "react";
import { api } from "../api";
import { PhaseBadge, StanceLabel, Empty, useToast, fmtDate, ROLE_LABELS } from "../ui";

export default function ProgramDetail({ programId, onQuickEntry, reloadKey }) {
  const toast = useToast();
  const [prog, setProg] = useState(null);

  async function load() {
    try { setProg(await api.program(programId)); }
    catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [programId, reloadKey]);

  if (!prog) return <div className="subtle">Loading…</div>;

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
        <button className="btn primary" onClick={() => onQuickEntry(prog.account_id, prog.id)}>Log interaction</button>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>
        {[prog.region, prog.audience, prog.use_case].filter(Boolean).join(" · ") || "—"}
      </div>

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
    </div>
  );
}
