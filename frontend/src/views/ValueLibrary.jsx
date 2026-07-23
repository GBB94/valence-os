import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast } from "../ui";

const TIERS = ["anecdote", "client_quote", "measured_operational", "correlated_business"];
const VIS = ["internal", "client_working", "qbr_exec", "externally_referenceable"];
const VIS_LABEL = { internal: "internal only", client_working: "client working", qbr_exec: "QBR / exec", externally_referenceable: "external" };

export default function ValueLibrary({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [stories, setStories] = useState(null);
  const [adding, setAdding] = useState(false);
  const [tick, setTick] = useState(0);

  async function load() {
    if (!accountId) return;
    try { setStories(await api.valueStories(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);

  if (!accounts.length) return <div className="subtle">Create an account first.</div>;
  const positive = (stories || []).filter((s) => !s.is_negative);
  const negative = (stories || []).filter((s) => s.is_negative);

  return (
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Value &amp; story library</h1>
        <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setAdding(true)}>Add story</button>
      </div>

      <div className="card">
        <div className="card-h"><h3>Value stories</h3></div>
        {!stories ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> :
          positive.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No value stories yet.</div> : (
          <table>
            <thead><tr><th>Outcome</th><th style={{ width: 150 }}>Evidence tier</th><th style={{ width: 130 }}>Visibility</th></tr></thead>
            <tbody>
              {positive.map((s) => (
                <tr key={s.id}>
                  <td>{s.outcome}{s.tags ? <div className="rowmeta">{s.tags}</div> : null}</td>
                  <td className="rowmeta">{s.evidence_tier.replace(/_/g, " ")}</td>
                  <td><span className="badge" style={["qbr_exec", "externally_referenceable"].includes(s.visibility_class) ? { borderColor: "var(--ok)", color: "var(--ok)" } : {}}>{VIS_LABEL[s.visibility_class]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-h"><h3>Negative evidence</h3><div className="spacer" /><span className="rowmeta">guards against optimism bias · never client-facing</span></div>
        {negative.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None recorded.</div> : (
          <table>
            <tbody>
              {negative.map((s) => (
                <tr key={s.id}><td><span className="dot risk" /> {s.outcome}{s.tags ? <span className="rowmeta"> · {s.tags}</span> : null}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {adding && <AddStory accountId={accountId} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setTick((t) => t + 1); }} />}
    </div>
  );
}

function AddStory({ accountId, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ outcome: "", tags: "", evidence_tier: "anecdote", visibility_class: "internal", is_negative: false });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    if (!f.outcome.trim()) { toast("Outcome required", "err"); return; }
    try {
      await api.createValueStory({ account_id: accountId, outcome: f.outcome.trim(), tags: f.tags || null,
        evidence_tier: f.evidence_tier, visibility_class: f.visibility_class, is_negative: f.is_negative });
      toast("Story added"); onSaved();
    } catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="Add value story" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Add</button></>}>
      <div className="field"><label>Outcome <span className="req">*</span></label><textarea value={f.outcome} onChange={set("outcome")} autoFocus /></div>
      <div className="field"><label>Tags</label><input value={f.tags} onChange={set("tags")} placeholder="comma,separated" /></div>
      <div className="grid2">
        <div className="field"><label>Evidence tier</label><select value={f.evidence_tier} onChange={set("evidence_tier")}>{TIERS.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select></div>
        <div className="field"><label>Visibility</label><select value={f.visibility_class} onChange={set("visibility_class")}>{VIS.map((v) => <option key={v} value={v}>{VIS_LABEL[v]}</option>)}</select></div>
      </div>
      <div className="field checkline"><input id="neg" type="checkbox" checked={f.is_negative} onChange={(e) => setF({ ...f, is_negative: e.target.checked })} /><label htmlFor="neg" style={{ margin: 0 }}>Negative evidence (objection / friction / failed intervention)</label></div>
      <div className="hint">Default visibility is internal-only. Client-facing generators include only affirmatively promoted, non-negative stories.</div>
    </SlideOver>
  );
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
