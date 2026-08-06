import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast, fmtDate, AgeChip } from "../ui";

// Plays trigger engine (v4). Definitions fire runs against current state; each run
// records an effectiveness note so the playbook improves, not just automates.
const TRIGGERS = [
  "renewal_window", "overdue_commitment", "stale_stakeholder", "active_blocker",
  "checklist_overdue", "unanswered_email", "unidentified_placeholder", "cadence_overdue",
  "no_second_champion", "champion_gone_quiet", "stalled_cohort", "expansion_signal",
  "org_change_confirmed", "calendar_moment", "land_and_leave",
];
const EFF = ["effective", "unclear", "ineffective"];

export default function Plays({ reloadKey, onChanged }) {
  const toast = useToast();
  const [plays, setPlays] = useState([]);
  const [runs, setRuns] = useState([]);
  const [adding, setAdding] = useState(false);
  const [completing, setCompleting] = useState(null);
  const [tick, setTick] = useState(0);

  async function load() {
    try { const [p, r] = await Promise.all([api.plays(), api.playRuns()]); setPlays(p); setRuns(r); }
    catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [reloadKey, tick]);

  async function evaluate() {
    try { const r = await api.evaluatePlays(); toast(`${r.count} play(s) fired`); setTick((t) => t + 1); onChanged?.(); }
    catch (e) { toast(e.message, "err"); }
  }

  const fired = runs.filter((r) => r.status === "fired");
  const completed = runs.filter((r) => r.status === "completed");

  return (
    <div className="card-stack">
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Plays</h1>
        <div className="spacer" />
        <button className="btn" onClick={() => setAdding(true)}>New play</button>
        <button className="btn primary" onClick={evaluate}>Evaluate now</button>
      </div>

      <div className="card">
        <div className="card-h"><h3>Definitions</h3></div>
        {plays.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No plays defined.</div> : (
          <table><thead><tr><th scope="col">Play</th><th scope="col" style={{ width: 180 }}>Trigger</th><th scope="col">Action</th></tr></thead>
            <tbody>{plays.map((p) => (
              <tr key={p.id}><td>{p.name}</td><td className="rowmeta">{p.trigger_kind.replace(/_/g, " ")}</td><td className="rowmeta">{p.action_template}</td></tr>
            ))}</tbody></table>
        )}
      </div>

      <div className="card">
        <div className="card-h"><h3>Fired — awaiting completion</h3><div className="spacer" /><span className="rowmeta">{fired.length}</span></div>
        {fired.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None. Click “Evaluate now”.</div> : (
          <table><tbody>{fired.map((r) => (
            <tr key={r.id}><td>{r.action_text}<div className="rowmeta">{r.play_name} · {r.trigger_context} · fired <AgeChip date={r.fired_at} /></div></td>
              <td style={{ width: 110 }}><button className="btn small" onClick={() => setCompleting(r)}>Complete</button></td></tr>
          ))}</tbody></table>
        )}
      </div>

      {completed.length > 0 && (
        <div className="card">
          <div className="card-h"><h3>Completed — effectiveness</h3></div>
          <table><tbody>{completed.map((r) => (
            <tr key={r.id}><td>{r.action_text}<div className="rowmeta">{r.play_name}</div></td>
              <td style={{ width: 150 }}><span className="badge" style={r.effectiveness === "effective" ? { borderColor: "var(--status-ok)", color: "var(--status-ok)" } : r.effectiveness === "ineffective" ? { borderColor: "var(--status-risk)", color: "var(--status-risk)" } : {}}>{r.effectiveness}</span></td></tr>
          ))}</tbody></table>
        </div>
      )}

      {adding && <AddPlay onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setTick((t) => t + 1); }} />}
      {completing && <CompleteRun run={completing} onClose={() => setCompleting(null)} onSaved={() => { setCompleting(null); setTick((t) => t + 1); onChanged?.(); }} />}
    </div>
  );
}

function AddPlay({ onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", trigger_kind: "renewal_window", action_template: "" });
  async function save() {
    if (!f.name.trim() || !f.action_template.trim()) { toast("Name and action required", "err"); return; }
    try { await api.createPlay(f); toast("Play created"); onSaved(); } catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="New play" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Create play</button></>}>
      <div className="field"><label>Name</label><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoFocus /></div>
      <div className="field"><label>Trigger</label><select value={f.trigger_kind} onChange={(e) => setF({ ...f, trigger_kind: e.target.value })}>{TRIGGERS.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select></div>
      <div className="field"><label>Action template</label><textarea value={f.action_template} onChange={(e) => setF({ ...f, action_template: e.target.value })} placeholder="Use {title} and {because} placeholders" /></div>
    </SlideOver>
  );
}

function CompleteRun({ run, onClose, onSaved }) {
  const toast = useToast();
  const [eff, setEff] = useState("effective");
  const [note, setNote] = useState("");
  async function save() {
    try { await api.completePlayRun(run.id, { effectiveness: eff, effectiveness_note: note || null }); toast("Recorded"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="Complete play run" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Record play run</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{run.action_text}</div>
      <div className="field"><label>Effectiveness</label><select value={eff} onChange={(e) => setEff(e.target.value)}>{EFF.map((x) => <option key={x} value={x}>{x}</option>)}</select></div>
      <div className="field"><label>Note</label><textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What happened — so the playbook learns" /></div>
    </SlideOver>
  );
}
