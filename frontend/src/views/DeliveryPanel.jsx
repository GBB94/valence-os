import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast, fmtDate } from "../ui";

const LANES = ["it_security", "legal_dpo", "works_council", "channel_setup", "localization_qa", "trust_comms", "hr_boundary"];
const LANE_LABEL = { it_security: "IT security", legal_dpo: "Legal / DPO", works_council: "Works council", channel_setup: "Channel setup", localization_qa: "Localization QA", trust_comms: "Trust comms", hr_boundary: "HR boundary" };
const C_STATUS = ["not_started", "in_progress", "complete", "blocked", "not_applicable"];
const C_DOT = { not_started: "", in_progress: "warn", complete: "ok", blocked: "risk", not_applicable: "" };
const MOMENT_TYPES = ["talent_calendar", "manager_workflow", "business_event", "proactive_coaching", "comms_campaign"];

export default function DeliveryPanel({ programId, people, reloadKey }) {
  const toast = useToast();
  const [d, setD] = useState(null);
  const [tick, setTick] = useState(0);
  const [adding, setAdding] = useState(null); // 'gate'|'compliance'|'moment'|'scope'
  const [waiving, setWaiving] = useState(null);

  async function load() {
    try { setD(await api.programDelivery(programId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [programId, reloadKey, tick]);
  const bump = () => setTick((t) => t + 1);

  async function toggleItem(id, complete) {
    try { await api.toggleGateItem(id, { complete }); bump(); } catch (e) { toast(e.message, "err"); }
  }
  async function waive(gate, reason) {
    try { await api.waiveGate(gate.id, { waiver_reason: reason }); toast("Gate waived"); bump(); } catch (e) { toast(e.message, "err"); }
  }
  async function setCompliance(item, status) {
    try { await api.patchCompliance(item.id, { status }); bump(); } catch (e) { toast(e.message, "err"); }
  }

  if (!d) return null;

  return (
    <>
      <div className="card">
        <div className="card-h"><h3>Phase gates</h3><div className="spacer" /><button className="btn small" onClick={() => setAdding("gate")}>Add gate</button></div>
        {d.phase_gates.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No gates.</div> :
          d.phase_gates.map((g) => (
            <div key={g.id} style={{ padding: "8px 12px", borderBottom: "1px solid var(--line-hairline)" }}>
              <div className="actions">
                <strong>{g.name}</strong>
                <span className={"badge"} style={badge(g.status)}>{g.status}</span>
                {g.gates_phase && <span className="rowmeta">gates {g.gates_phase}</span>}
                <div className="spacer" />
                {g.status === "open" && <button className="btn small ghost" onClick={() => setWaiving(g)}>Waive</button>}
              </div>
              {g.waiver_reason && <div className="rowmeta">waived: {g.waiver_reason}</div>}
              <div style={{ marginTop: 6 }}>
                {g.items.map((it) => (
                  <label key={it.id} className="checkline" style={{ marginBottom: 3 }}>
                    <input type="checkbox" checked={it.complete} disabled={g.status !== "open"} onChange={(e) => toggleItem(it.id, e.target.checked)} />
                    <span style={{ textDecoration: it.complete ? "line-through" : "none", color: it.complete ? "var(--ink-tertiary)" : "inherit" }}>{it.description}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
      </div>

      <div className="card">
        <div className="card-h"><h3>Compliance & readiness</h3><div className="spacer" /><button className="btn small" onClick={() => setAdding("compliance")}>Add lane</button></div>
        {d.compliance_items.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No lanes tracked.</div> : (
          <table>
            <tbody>
              {d.compliance_items.map((c) => (
                <tr key={c.id}>
                  <td>{LANE_LABEL[c.lane] || c.lane}{c.region ? <span className="rowmeta"> · {c.region}</span> : ""}{c.notes ? <div className="rowmeta">{c.notes}</div> : null}</td>
                  <td style={{ width: 150 }}>
                    <span className={"dot " + C_DOT[c.status]} />{" "}
                    <select value={c.status} onChange={(e) => setCompliance(c, e.target.value)} style={{ border: "1px solid var(--line-hairline)", borderRadius: 4, padding: "1px 4px" }}>
                      {C_STATUS.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-h"><h3>Deployment moments</h3><div className="spacer" /><button className="btn small" onClick={() => setAdding("moment")}>Add moment</button></div>
        {d.deployment_moments.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None.</div> : (
          <table><tbody>
            {d.deployment_moments.map((m) => (
              <tr key={m.id}><td>{m.name}<div className="rowmeta">{m.type.replace(/_/g, " ")}{m.event_date ? ` · ${m.event_date}` : ""}{m.comms_hook ? ` · ${m.comms_hook}` : ""}</div></td>
                <td style={{ width: 110 }}><span className={"badge"}>{m.integration_status.replace(/_/g, " ")}</span></td></tr>
            ))}
          </tbody></table>
        )}
      </div>

      <div className="card">
        <div className="card-h"><h3>Scope changes</h3><div className="spacer" /><button className="btn small" onClick={() => setAdding("scope")}>Log change</button></div>
        {d.scope_changes.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None logged.</div> : (
          <table><tbody>
            {d.scope_changes.map((s) => (
              <tr key={s.id}><td>{s.description}<div className="rowmeta">{s.agreed_by_name ? `agreed: ${s.agreed_by_name}` : ""}{s.changed_on ? ` · ${s.changed_on}` : ""}</div></td></tr>
            ))}
          </tbody></table>
        )}
      </div>

      {adding && <AddPanel kind={adding} programId={programId} people={people} onClose={() => setAdding(null)} onSaved={() => { setAdding(null); bump(); }} />}
      {waiving && <WaivePanel gate={waiving} onClose={() => setWaiving(null)} onSaved={(reason) => { waive(waiving, reason); setWaiving(null); }} />}
    </>
  );
}

function WaivePanel({ gate, onClose, onSaved }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const save = () => reason.trim() ? onSaved(reason.trim()) : toast("Waiver reason is required", "err");
  return <SlideOver title={`Waive gate · ${gate.name}`} onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn danger" onClick={save}>Waive gate</button></>}>
    <div className="field"><label>Waiver reason</label><textarea autoFocus value={reason} onChange={(e) => setReason(e.target.value)} /></div>
    <div className="hint">This reason is recorded in the delivery history.</div>
  </SlideOver>;
}

function badge(status) {
  if (status === "passed") return { borderColor: "var(--status-ok)", color: "var(--status-ok)" };
  if (status === "waived") return { borderColor: "var(--status-warn)", color: "var(--status-warn)" };
  return {};
}

function AddPanel({ kind, programId, people, onClose, onSaved }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [items, setItems] = useState("");
  const [lane, setLane] = useState("it_security");
  const [mtype, setMtype] = useState("talent_calendar");
  async function save() {
    try {
      if (kind === "gate") {
        if (!text.trim()) return toast("Name required", "err");
        await api.createGate({ program_id: programId, name: text.trim(), items: items.split("\n").map((s) => s.trim()).filter(Boolean) });
      } else if (kind === "compliance") {
        await api.createCompliance({ program_id: programId, lane, notes: text || null });
      } else if (kind === "moment") {
        if (!text.trim()) return toast("Name required", "err");
        await api.createMoment({ program_id: programId, name: text.trim(), type: mtype });
      } else if (kind === "scope") {
        if (!text.trim()) return toast("Description required", "err");
        await api.createScopeChange({ program_id: programId, description: text.trim() });
      }
      toast("Added"); onSaved();
    } catch (e) { toast(e.message, "err"); }
  }
  const titles = { gate: "Add phase gate", compliance: "Add compliance lane", moment: "Add deployment moment", scope: "Log scope change" };
  const actions = { gate: "Add gate", compliance: "Add lane", moment: "Add moment", scope: "Log change" };
  return (
    <SlideOver title={titles[kind]} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>{actions[kind]}</button></>}>
      {kind === "gate" && <>
        <div className="field"><label>Gate name</label><input value={text} onChange={(e) => setText(e.target.value)} autoFocus /></div>
        <div className="field"><label>Checklist items (one per line)</label><textarea value={items} onChange={(e) => setItems(e.target.value)} rows={5} /></div>
      </>}
      {kind === "compliance" && <>
        <div className="field"><label>Lane</label><select value={lane} onChange={(e) => setLane(e.target.value)}>{LANES.map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}</select></div>
        <div className="field"><label>Notes</label><input value={text} onChange={(e) => setText(e.target.value)} /></div>
      </>}
      {kind === "moment" && <>
        <div className="field"><label>Name</label><input value={text} onChange={(e) => setText(e.target.value)} autoFocus /></div>
        <div className="field"><label>Type</label><select value={mtype} onChange={(e) => setMtype(e.target.value)}>{MOMENT_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select></div>
      </>}
      {kind === "scope" && <div className="field"><label>What changed</label><textarea value={text} onChange={(e) => setText(e.target.value)} autoFocus /></div>}
    </SlideOver>
  );
}
