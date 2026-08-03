import { useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, Loading, SegTabs, SlideOver, useToast } from "../ui";

const STATES = [["active", "Active"], ["closed", "History"]];

export default function Signals({ accountId, reloadKey }) {
  const toast = useToast();
  const [episodes, setEpisodes] = useState(null);
  const [tab, setTab] = useState("active");
  const [tick, setTick] = useState(0);
  const [dismiss, setDismiss] = useState(null);
  const [propose, setPropose] = useState(null);

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
    {!episodes ? <Loading what="signals" /> : shown.length === 0
      ? <Empty title={tab === "active" ? "No active signals" : "No signal history"}>Run evaluation after syncing mock sources.</Empty>
      : <div className="card"><table>
        <thead><tr><th scope="col">Signal</th><th scope="col">Cell</th><th scope="col">State</th><th scope="col">Actions</th></tr></thead>
        <tbody>{shown.map((e) => <tr key={e.id}>
          <td><strong>{e.kind.replace(/_/g, " ")}</strong><div className="rowmeta">{e.explanation}</div>
            <div className="rowmeta">opened <AgeChip date={e.opened_at} />{e.freshness_as_of ? ` · evidence through ${e.freshness_as_of}` : ""}</div></td>
          <td>{e.population ? <>{e.population}<div className="rowmeta">{e.use_case}</div></> : <span className="rowmeta">account-level</span>}</td>
          <td><span className="badge" style={e.status === "held" ? { color: "var(--status-warn)", borderColor: "var(--status-warn)" } : {}}>{e.status}</span>
            {e.held_reason && <div className="rowmeta">{e.held_reason}</div>}</td>
          <td>{["open", "held"].includes(e.status) && <div className="actions">
            {e.status === "open" && e.cell_id && <button className="btn small" onClick={() => draft(e)}>Draft opportunity</button>}
            {e.status === "open" && !e.adoption_campaign_id &&
              <button className="btn small" onClick={() => setPropose(e)}>Propose campaign</button>}
            {e.adoption_campaign_id && <span className="rowmeta">campaign drafted</span>}
            <button className="btn small ghost" onClick={() => setDismiss(e)}>Dismiss</button>
          </div>}</td>
        </tr>)}</tbody>
      </table></div>}
    {dismiss && <DismissSignal episode={dismiss} onClose={() => setDismiss(null)} onSaved={() => { setDismiss(null); setTick((x) => x + 1); }} />}
    {propose && <ProposeCampaign episode={propose} accountId={accountId} onClose={() => setPropose(null)}
                                 onSaved={() => { setPropose(null); setTick((x) => x + 1); }} />}
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


/* §7.1 — a signal proposes a DRAFT campaign, never a running one. The operator still has to
   diagnose the barrier, name the intervention and lock a baseline before it can go anywhere.
   The design defaults to comparator because this campaign was selected on a declining reading,
   and a comparator is what absorbs that selection effect. */
function ProposeCampaign({ episode, accountId, onClose, onSaved }) {
  const toast = useToast();
  const [people, setPeople] = useState([]);
  const [f, setF] = useState({
    internal_owner_person_id: "", planned_start_on: "", planned_end_on: "",
    evaluation_on: "", evaluation_design: "comparator",
  });

  useEffect(() => {
    api.account(accountId)
      .then((a) => setPeople((a.people || []).filter((p) => p.affiliation === "valence")))
      .catch(() => {});
  }, [accountId]);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <SlideOver title="Propose a campaign" onClose={onClose}>
      <div className="rowmeta" style={{ marginBottom: 12 }}>
        {episode.explanation}
      </div>
      <div className="rowmeta" style={{ marginBottom: 12 }}>
        This creates a <strong>draft</strong>. It cannot start until you diagnose a barrier, link a
        real intervention and lock a baseline.
      </div>
      <form onSubmit={async (ev) => {
        ev.preventDefault();
        try {
          await api.proposeCampaignFromSignal(episode.id, {
            ...f, evaluation_on: f.evaluation_on || null,
          });
          toast("Draft campaign created");
          onSaved();
        } catch (err) { toast(err.message, "err"); }
      }}>
        <label style={pcLbl}>Internal owner
          <select value={f.internal_owner_person_id} onChange={set("internal_owner_person_id")}
                  required style={pcInput}>
            <option value="">choose…</option>
            {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...pcLbl, flex: 1 }}>Starts
            <input type="date" value={f.planned_start_on} onChange={set("planned_start_on")}
                   required style={pcInput} /></label>
          <label style={{ ...pcLbl, flex: 1 }}>Ends
            <input type="date" value={f.planned_end_on} onChange={set("planned_end_on")}
                   required style={pcInput} /></label>
        </div>
        <label style={pcLbl}>Evaluate on
          <input type="date" value={f.evaluation_on} onChange={set("evaluation_on")} style={pcInput} /></label>
        <label style={pcLbl}>Evaluation design
          <select value={f.evaluation_design} onChange={set("evaluation_design")} style={pcInput}>
            <option value="comparator">Comparator (recommended for signal-triggered)</option>
            <option value="pre_post">Pre/post</option>
            <option value="descriptive">Descriptive</option>
          </select>
        </label>
        {f.evaluation_design === "pre_post" && (
          <div className="rowmeta" style={{ marginBottom: 12, color: "var(--ink-secondary)" }}>
            ▲ This cohort was selected because its reading fell, so some rebound is expected
            without intervention. A comparator absorbs that; pre/post will carry the caution.
          </div>
        )}
        <button className="btn small primary" type="submit">Create draft</button>
      </form>
    </SlideOver>
  );
}

const pcLbl = { display: "flex", flexDirection: "column", gap: 4, marginBottom: 12, fontSize: "var(--t-body)" };
const pcInput = {
  padding: "6px 8px", borderRadius: "var(--r-sm)",
  border: "1px solid var(--line-hairline)", background: "var(--bg-surface)",
  color: "var(--ink-primary)",
};
