import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast } from "../ui";

export default function PlaybookLibrary({ reloadKey }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [capture, setCapture] = useState(null);
  const [tick, setTick] = useState(0);
  const load = () => api.playbookEntries().then(setData).catch((e) => toast(e.message, "err"));
  useEffect(() => { load(); }, [reloadKey, tick]);
  const refresh = () => { setCapture(null); setTick((n) => n + 1); };
  async function promotePlay(entry) {
    const name = window.prompt("Play name", entry.motion_run);
    if (!name) return;
    const action = window.prompt("Action template", `Run the learned motion: ${entry.motion_run}`);
    if (!action) return;
    try { const r = await api.promotePlaybookPlay(entry.id, { name, action_template: action });
      toast(`Play promoted from ${r.evidence_count} successful entries`); refresh(); }
    catch (e) { toast(e.message, "err"); }
  }
  async function promoteMessage(entry) {
    try { await api.promotePlaybookMessage(entry.id, {}); toast("Message promoted to the messaging library"); refresh(); }
    catch (e) { toast(e.message, "err"); }
  }
  return <div style={{ marginTop: 18 }}>
    <div className="actions" style={{ marginBottom: 10 }}><div>
      <h2 style={{ margin: 0 }}>Expansion playbook</h2>
      <div className="rowmeta">Structured learning from Proven, Penetrated, and Declined transitions.</div>
    </div><div className="spacer" />{data && <span className="rowmeta">{data.pending.length} prompts waiting</span>}</div>

    {data?.pending.length > 0 && <div className="card" style={{ marginBottom: 14 }}>
      <div className="card-h"><h3>Capture the transition</h3></div>
      <table><thead><tr><th>Shape</th><th>Transition</th><th>When</th><th></th></tr></thead><tbody>
        {data.pending.map((row) => <tr key={row.id}>
          <td>{row.population_name} · {row.use_case_name}
            <div className="rowmeta">{row.cross_account_eligible ? "global shape" : "account-specific · excluded cross-account"}</div></td>
          <td>{row.derived_state_before} → {row.derived_state_after}</td><td>{row.changed_on}</td>
          <td><button className="btn small primary" onClick={() => setCapture(row)}>Capture learning</button></td>
        </tr>)}
      </tbody></table>
    </div>}

    <div className="card">
      <div className="card-h"><h3>Learned motions</h3><div className="spacer" />
        <span className="rowmeta">exact shape → tag overlap → use case</span></div>
      {!data ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> : data.entries.length === 0 ?
        <Empty title="No playbook entries yet">Move a whitespace cell to Proven, Penetrated, or Declined, then capture what carried the transition.</Empty> :
        <table><thead><tr><th>Shape and motion</th><th>Outcome</th><th>Message / learning</th><th>Promoted</th></tr></thead><tbody>
          {data.entries.map((entry) => <tr key={entry.id}>
            <td><strong>{entry.use_case}</strong>{entry.audience_tags.length ? ` · ${entry.audience_tags.map((t) => t.name).join(", ")}` : ""}
              <div className="rowmeta">{entry.account_name} · {entry.motion_run}</div></td>
            <td>{entry.transition_to}<div className="rowmeta">{entry.duration_days == null ? "duration unknown" : `${entry.duration_days} days`} · {entry.transitioned_on}</div></td>
            <td>{entry.message_summary || entry.what_worked || "—"}<div className="rowmeta">{entry.what_differently || ""}</div></td>
            <td className="rowmeta"><div className="actions" style={{ flexWrap: "wrap" }}>
              {entry.play_definition_id ? <span className="badge">play</span> : entry.transition_to !== "declined" &&
                <button className="btn small ghost" onClick={() => promotePlay(entry)}>Promote play</button>}
              {entry.messaging_entry_id ? <span className="badge">message</span> : entry.transition_to !== "declined" && entry.message_summary &&
                <button className="btn small ghost" onClick={() => promoteMessage(entry)}>Promote message</button>}
            </div></td>
          </tr>)}
        </tbody></table>}
    </div>
    {capture && <CaptureEntry transition={capture} onClose={() => setCapture(null)} onSaved={refresh} />}
  </div>;
}

function CaptureEntry({ transition, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ motion_run: "", evidence_summary: "", message_summary: "",
    message_layer: "", motion_started_on: "", what_worked: "", what_differently: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    if (!f.motion_run.trim()) { toast("Motion is required", "err"); return; }
    try {
      await api.createPlaybookEntry({ ...f, transition_history_id: transition.id,
        motion_run: f.motion_run.trim(), message_layer: f.message_layer || null,
        motion_started_on: f.motion_started_on || null });
      toast("Playbook learning captured"); onSaved();
    } catch (e) { toast(e.message, "err"); }
  }
  return <SlideOver title="Capture expansion learning" onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save entry</button></>}>
    <div className="rowmeta" style={{ marginBottom: 12 }}>{transition.population_name} · {transition.use_case_name} · {transition.derived_state_after}</div>
    <div className="field"><label>Motion run <span className="req">*</span></label><input value={f.motion_run} onChange={set("motion_run")} placeholder="e.g. sponsor-led manager pilot" autoFocus /></div>
    <div className="field"><label>Motion started</label><input type="date" max={transition.changed_on} value={f.motion_started_on} onChange={set("motion_started_on")} /></div>
    <div className="field"><label>Evidence that carried it</label><textarea value={f.evidence_summary} onChange={set("evidence_summary")} /></div>
    <div className="field"><label>Message that landed</label><textarea value={f.message_summary} onChange={set("message_summary")} /></div>
    <div className="field"><label>Layer</label><select value={f.message_layer} onChange={set("message_layer")}><option value="">—</option>
      {["executive","economic","operational","technical_gating","user_advocate"].map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}</select></div>
    <div className="field"><label>What worked</label><textarea value={f.what_worked} onChange={set("what_worked")} /></div>
    <div className="field"><label>What would you do differently?</label><textarea value={f.what_differently} onChange={set("what_differently")} /></div>
    <div className="field"><label>Shape snapshot</label>
      <div className="rowmeta">{transition.audience_tags?.length
        ? transition.audience_tags.map((tag) => tag.name).join(", ")
        : "No global audience tags on this cell; matching will use the global use case only."}</div>
    </div>
  </SlideOver>;
}
