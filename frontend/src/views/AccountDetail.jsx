import { useEffect, useState } from "react";
import { api } from "../api";
import { PhaseBadge, Empty, useToast, fmtDate } from "../ui";

export default function AccountDetail({ accountId, onOpenProgram, onQuickEntry, reloadKey }) {
  const toast = useToast();
  const [acct, setAcct] = useState(null);
  const [addingProgram, setAddingProgram] = useState(false);
  const [pname, setPname] = useState("");
  const [pphase, setPphase] = useState("foundation");

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

  if (!acct) return <div className="subtle">Loading…</div>;

  return (
    <div>
      {/* Account header — v0.1 subset. Delivery/commercial statuses arrive in v0.3;
          renewal countdown needs contracts (v1). Not shown, not faked. */}
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>{acct.name}</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => onQuickEntry(acct.id)}>Log interaction</button>
      </div>
      <div className="subtle" style={{ marginBottom: 6 }}>{acct.short_context}</div>
      {acct.incumbent_note && <div className="rowmeta" style={{ marginBottom: 6 }}>Incumbent: {acct.incumbent_note}</div>}
      <div className="rowmeta">
        Delivery &amp; commercial status arrive in v0.3 · renewal countdown needs contracts (v1)
      </div>

      <div className="two-col" style={{ marginTop: 18 }}>
        <div>
          <div className="card">
            <div className="card-h">
              <h3>Programs</h3>
              <div className="spacer" />
              <button className="btn small" onClick={() => setAddingProgram((v) => !v)}>New program</button>
            </div>
            {addingProgram && (
              <div style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
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
                        {it.program_id ? null : <span className="tag-internal" style={{borderColor:'var(--text-3)',color:'var(--text-3)'}}>account-level</span>}
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
          <div className="card-h"><h3>People</h3></div>
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
    </div>
  );
}
