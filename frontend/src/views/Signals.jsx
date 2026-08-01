import { useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, SegTabs, SlideOver, useToast } from "../ui";

const STATES = [["active", "Active"], ["closed", "History"]];

export default function Signals({ accountId, reloadKey }) {
  const toast = useToast();
  const [episodes, setEpisodes] = useState(null);
  const [tab, setTab] = useState("active");
  const [tick, setTick] = useState(0);
  const [dismiss, setDismiss] = useState(null);

  const load = () => api.signalEpisodes({ accountId }).then((r) => setEpisodes(r.episodes))
    .catch((e) => toast(e.message, "err"));
  useEffect(() => { if (accountId) load(); }, [accountId, reloadKey, tick]);

  const evaluate = async () => {
    try { const r = await api.evaluateSignals(); toast(`${r.opened} new · ${r.refreshed} refreshed`); setTick((x) => x + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  const draft = async (ep) => {
    try { await api.draftSignalOpportunity(ep.id); toast("Opportunity drafted"); setTick((x) => x + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  const shown = (episodes || []).filter((e) => tab === "active" ? ["open", "held"].includes(e.status) : !["open", "held"].includes(e.status));

  return <div>
    <div className="actions" style={{ marginBottom: "var(--sp-5)" }}>
      <div>
        <h2 style={{ margin: 0 }}>Expansion signals</h2>
        <div className="rowmeta">Episodes recur only after the condition clears; customer pull outranks vendor push.</div>
      </div>
      <div className="spacer" />
      <button className="btn small primary" onClick={evaluate}>Evaluate now</button>
    </div>
    <div style={{ marginBottom: "var(--sp-4)" }}><SegTabs tabs={STATES} value={tab} onChange={setTab} kind="chip" /></div>
    {!episodes ? <div className="subtle">Loading…</div> : shown.length === 0
      ? <Empty title={tab === "active" ? "No active signals" : "No signal history"}>Run evaluation after syncing mock sources.</Empty>
      : <div className="card"><table>
        <thead><tr><th>Signal</th><th>Cell</th><th>State</th><th></th></tr></thead>
        <tbody>{shown.map((e) => <tr key={e.id}>
          <td><strong>{e.kind.replace(/_/g, " ")}</strong><div className="rowmeta">{e.explanation}</div>
            <div className="rowmeta">opened <AgeChip date={e.opened_at} />{e.freshness_as_of ? ` · evidence through ${e.freshness_as_of}` : ""}</div></td>
          <td>{e.population ? <>{e.population}<div className="rowmeta">{e.use_case}</div></> : <span className="rowmeta">account-level</span>}</td>
          <td><span className="badge" style={e.status === "held" ? { color: "var(--status-warn)", borderColor: "var(--status-warn)" } : {}}>{e.status}</span>
            {e.held_reason && <div className="rowmeta">{e.held_reason}</div>}</td>
          <td>{["open", "held"].includes(e.status) && <div className="actions">
            {e.status === "open" && e.cell_id && <button className="btn small primary" onClick={() => draft(e)}>Draft opportunity</button>}
            <button className="btn small ghost" onClick={() => setDismiss(e)}>Dismiss</button>
          </div>}</td>
        </tr>)}</tbody>
      </table></div>}
    {dismiss && <DismissSignal episode={dismiss} onClose={() => setDismiss(null)} onSaved={() => { setDismiss(null); setTick((x) => x + 1); }} />}
  </div>;
}

function DismissSignal({ episode, onClose, onSaved }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const save = async () => {
    if (!reason.trim()) { toast("Say why this signal is not actionable", "err"); return; }
    try { await api.dismissSignal(episode.id, reason); toast("Dismissed with cooldown"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  };
  return <SlideOver title="Dismiss signal episode" onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Dismiss</button></>}>
    <p className="subtle">Dismissal is recorded and suppresses this condition during the account cooldown. A later recurrence opens a new episode.</p>
    <div className="field"><label>Reason</label><textarea autoFocus value={reason} onChange={(e) => setReason(e.target.value)} /></div>
  </SlideOver>;
}
