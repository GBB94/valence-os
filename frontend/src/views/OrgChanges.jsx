import { useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, Loading, SlideOver, useToast } from "../ui";

export default function OrgChanges({ accountId, reloadKey }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [tick, setTick] = useState(0);
  const [dismissing, setDismissing] = useState(null);
  const load = () => api.orgChanges(accountId).then(setData).catch((e) => toast(e.message, "err"));
  useEffect(() => { if (accountId) load(); }, [accountId, reloadKey, tick]);
  const sync = async () => {
    try { const r = await api.syncOrgChanges(); toast(`${r.result?.created || 0} proposals synced`); setTick((x) => x + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  const confirm = async (id) => {
    try { await api.confirmOrgChange(id); toast("Change confirmed and follow-up created"); setTick((x) => x + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  if (!data) return <Loading what="org changes" />;
  return <div>
    <div className="actions" style={{ marginBottom: "var(--sp-4)" }}><div><h1 style={{ margin: 0 }}>Org changes</h1>
      <div className="rowmeta">Adapter findings are proposals. Nothing edits a person until you confirm it.</div></div>
      <div className="spacer" /><button className="btn small" onClick={sync}>Sync mock enrichment</button></div>
    <div className="card">
      {data.flags.length === 0 ? <Empty title="No change proposals">Sync the mock fixture to exercise confirmation.</Empty>
        : <table><thead><tr><th scope="col">Change</th><th scope="col">State</th><th scope="col">Actions</th></tr></thead>
          <tbody>{data.flags.map((f) => <tr key={f.id}>
            <td><strong>{f.kind.replace(/_/g, " ")}</strong> · {f.summary}
              <div className="rowmeta">{f.occurred_on ? <AgeChip date={f.occurred_on} /> : "date unknown"}</div></td>
            <td><span className="badge">{f.status}</span></td>
            <td>{f.status === "proposed" && <div className="actions"><button className="btn small" onClick={() => confirm(f.id)}>Confirm change</button>
              <button className="btn small ghost" onClick={() => setDismissing(f)}>Dismiss</button></div>}</td>
          </tr>)}</tbody></table>}
    </div>
    {data.successions.length > 0 && <div className="card" style={{ marginTop: 10 }}><div className="card-h"><h3>Succession</h3></div>
      <table><tbody>{data.successions.map((s) => <tr key={s.id}><td>Successor search<div className="rowmeta">Relationship snapshot retained · {s.departed_to ? `departed to ${s.departed_to}` : "destination unknown"}</div></td><td><span className="badge">{s.status}</span></td></tr>)}</tbody></table></div>}
    {dismissing && <DismissChange flag={dismissing} onClose={() => setDismissing(null)} onSaved={() => { setDismissing(null); setTick((x) => x + 1); }} />}
  </div>;
}

function DismissChange({ flag, onClose, onSaved }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const save = async () => {
    if (!reason.trim()) { toast("A dismissal reason is required", "err"); return; }
    try { await api.dismissOrgChange(flag.id, reason); toast("Proposal dismissed"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  };
  return <SlideOver title="Dismiss org-change proposal" onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Dismiss</button></>}>
    <p className="subtle">{flag.summary}</p>
    <div className="field"><label>Reason</label><textarea autoFocus value={reason} onChange={(e) => setReason(e.target.value)} /></div>
  </SlideOver>;
}
