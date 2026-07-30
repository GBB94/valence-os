import { useEffect, useState } from "react";
import { api } from "../api";
import { PhaseBadge, Empty, SlideOver, useToast, fmtDate } from "../ui";

const STATUS_LABEL = { on_track: "on track", at_risk: "at risk", off_track: "off track", unknown: "unknown" };
const STATUS_DOT = { on_track: "ok", at_risk: "warn", off_track: "risk", unknown: "" };

function daysSince(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

export default function AccountDetail({ accountId, onOpenProgram, onQuickEntry, reloadKey }) {
  const toast = useToast();
  const [acct, setAcct] = useState(null);
  const [addingProgram, setAddingProgram] = useState(false);
  const [pname, setPname] = useState("");
  const [pphase, setPphase] = useState("foundation");
  const [editStatus, setEditStatus] = useState(null); // 'delivery' | 'commercial'

  async function load() {
    try {
      setAcct(await api.account(accountId));
    } catch (e) {
      toast(e.message, "err");
    }
  }
  useEffect(() => { load(); }, [accountId, reloadKey]);

  async function createProgram() {
    if (!pname.trim()) return;
    try {
      await api.createProgram({ account_id: accountId, name: pname.trim(), phase: pphase });
      toast("Program created");
      setPname(""); setPphase("foundation"); setAddingProgram(false);
      load();
    } catch (e) {
      toast(e.message, "err");
    }
  }

  async function exportAccount() {
    try {
      const bundle = await api.exportAccount(accountId);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${acct.name.replace(/[^\w.-]+/g, "_")}.valence-export.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast("Account exported");
    } catch (e) { toast(e.message, "err"); }
  }

  if (!acct) return <div className="subtle">Loading…</div>;

  return (
    <div>
      {/* Account header — v0.1 subset. Delivery/commercial statuses arrive in v0.3;
          renewal countdown needs contracts (v1). Not shown, not faked. */}
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>{acct.name}</h1>
        <div className="spacer" />
        <button className="btn" onClick={exportAccount}>Export</button>
        <button className="btn primary" onClick={() => onQuickEntry(acct.id)}>Log interaction</button>
      </div>
      <div className="subtle" style={{ marginBottom: 10 }}>{acct.short_context}</div>

      <div className="two-col" style={{ gridTemplateColumns: "1fr 1fr", gap: 10, maxWidth: 720 }}>
        <StatusCard dim="delivery" label="Delivery / value" acct={acct} onEdit={() => setEditStatus("delivery")} />
        <StatusCard dim="commercial" label="Commercial" acct={acct} onEdit={() => setEditStatus("commercial")} />
      </div>
      {acct.incumbent_note && <div className="rowmeta" style={{ marginTop: 8 }}>Incumbent: {acct.incumbent_note}</div>}
      <div className="rowmeta" style={{ marginTop: 4 }}>Two independent hand-judged statuses — no composite score. Renewal countdown needs contracts (v1).</div>

      <div className="two-col" style={{ marginTop: 18 }}>
        <div>
          <div className="card">
            <div className="card-h">
              <h3>Programs</h3>
              <div className="spacer" />
              <button className="btn small" onClick={() => setAddingProgram((v) => !v)}>New program</button>
            </div>
            {addingProgram && (
              <div style={{ padding: 12, borderBottom: "1px solid var(--line-hairline)" }}>
                <div className="grid2">
                  <div className="field">
                    <label>Name <span className="req">*</span></label>
                    <input value={pname} onChange={(e) => setPname(e.target.value)} autoFocus />
                  </div>
                  <div className="field">
                    <label>Phase</label>
                    <select value={pphase} onChange={(e) => setPphase(e.target.value)}>
                      {["foundation","launch","programmatic","expansion","renewal","closed"].map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="actions">
                  <button className="btn primary small" onClick={createProgram}>Create</button>
                  <button className="btn small" onClick={() => setAddingProgram(false)}>Cancel</button>
                </div>
              </div>
            )}
            {acct.programs.length === 0 ? (
              <Empty title="No programs yet">Add the first deployment or commercial motion.</Empty>
            ) : (
              <table>
                <thead><tr><th>Program</th><th style={{width:130}}>Phase</th><th style={{width:110}}>Region</th></tr></thead>
                <tbody>
                  {acct.programs.map((p) => (
                    <tr key={p.id} className="clickable" onClick={() => onOpenProgram(p.id)}>
                      <td><strong>{p.name}</strong>{p.expansion_hypothesis ? <div className="rowmeta">{p.expansion_hypothesis}</div> : null}</td>
                      <td><PhaseBadge phase={p.phase} /></td>
                      <td className="rowmeta">{p.region || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <div className="card-h"><h3>Recent interactions</h3></div>
            {acct.interactions.length === 0 ? (
              <Empty title="No interactions logged">Use “Log interaction” to capture your first call.</Empty>
            ) : (
              <table>
                <thead><tr><th style={{width:96}}>Date</th><th style={{width:80}}>Type</th><th>Summary</th></tr></thead>
                <tbody>
                  {acct.interactions.map((it) => (
                    <tr key={it.id}>
                      <td className="rowmeta">{fmtDate(it.occurred_on)}</td>
                      <td><span className="badge">{it.type}</span></td>
                      <td>{it.summary || <span className="rowmeta">—</span>}
                        {it.program_id ? null : <span className="tag-internal" style={{borderColor:'var(--ink-tertiary)',color:'var(--ink-tertiary)'}}>account-level</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="rowmeta" style={{ padding: "8px 12px" }}>Full history timeline arrives in v0.4.</div>
          </div>
        </div>

        <div className="card">
          <div className="card-h"><h3>People</h3></div>{/* people table below */}
          {acct.people.length === 0 ? (
            <Empty title="No people yet">People are added per program with a role.</Empty>
          ) : (
            <table>
              <thead><tr><th>Name</th><th>Title</th></tr></thead>
              <tbody>
                {acct.people.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td className="rowmeta">{p.title || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {editStatus && (
        <StatusEditor
          dim={editStatus}
          acct={acct}
          onClose={() => setEditStatus(null)}
          onSaved={() => { setEditStatus(null); load(); }}
        />
      )}
    </div>
  );
}

function StatusCard({ dim, label, acct, onEdit }) {
  const value = acct[`${dim}_status`];
  const assessedOn = acct[`${dim}_status_assessed_on`];
  const rationale = acct[`${dim}_status_rationale`];
  const age = daysSince(assessedOn);
  const stale = age != null && age > 30;
  return (
    <div className="card" style={{ padding: 12 }}>
      <div className="actions" style={{ marginBottom: 4 }}>
        <span className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</span>
        <div className="spacer" />
        <button className="btn small ghost" onClick={onEdit}>Edit</button>
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 2 }}>
        <span className={"dot " + STATUS_DOT[value]} /> {STATUS_LABEL[value]}
      </div>
      {rationale && <div className="rowmeta">{rationale}</div>}
      <div className="rowmeta" style={{ marginTop: 4 }}>
        {assessedOn ? `assessed ${assessedOn}` : "not assessed"}
        {stale && <span className="badge" style={{ marginLeft: 6, borderColor: "var(--status-warn)", color: "var(--status-warn)" }}>reassess ({age}d)</span>}
      </div>
    </div>
  );
}

function StatusEditor({ dim, acct, onClose, onSaved }) {
  const toast = useToast();
  const [value, setValue] = useState(acct[`${dim}_status`] || "unknown");
  const [rationale, setRationale] = useState(acct[`${dim}_status_rationale`] || "");
  const [cond, setCond] = useState(acct[`${dim}_status_change_condition`] || "");
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await api.setStatus(acct.id, { dimension: dim, value, rationale: rationale || null, change_condition: cond || null });
      toast("Status updated"); onSaved();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }
  return (
    <SlideOver title={`${dim === "delivery" ? "Delivery / value" : "Commercial"} status`} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={saving}>Save assessment</button></>}>
      <div className="field"><label>Status</label>
        <select value={value} onChange={(e) => setValue(e.target.value)}>
          {["on_track", "at_risk", "off_track", "unknown"].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
      </div>
      <div className="field"><label>Rationale</label>
        <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Why this judgment" />
      </div>
      <div className="field"><label>What would change it</label>
        <textarea value={cond} onChange={(e) => setCond(e.target.value)} placeholder="The condition that would move this status" />
      </div>
      <div className="hint">Saving stamps today as the assessment date. The two statuses are independent — good delivery can coexist with weak commercial.</div>
    </SlideOver>
  );
}
