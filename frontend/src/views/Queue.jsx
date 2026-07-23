import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast } from "../ui";

// Portfolio home — the ranked, explainable attention queue (Module A).
export default function Queue({ reloadKey, onOpenAccount, onChanged }) {
  const toast = useToast();
  const [q, setQ] = useState(null);
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [snoozing, setSnoozing] = useState(null); // item
  const [resolving, setResolving] = useState(null); // item

  async function load() {
    try { setQ(await api.queue()); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [reloadKey]);

  const after = () => { setSnoozing(null); setResolving(null); load(); onChanged?.(); };

  if (!q) return <div className="subtle">Loading…</div>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>Portfolio home</h1>
        <div className="spacer" />
        <span className="rowmeta">{q.items.length} to act · as of {q.as_of}</span>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>
        Ranked by rule, and every item explains itself. Snoozing needs a return date or a condition; resolving needs a linked follow-up.
      </div>

      <div className="card">
        {q.items.length === 0 ? (
          <Empty title="Queue clear">Nothing needs attention right now.</Empty>
        ) : (
          <table>
            <thead>
              <tr><th style={{ width: 22 }}></th><th>Item</th><th style={{ width: 92 }}>Age</th><th style={{ width: 150 }}></th></tr>
            </thead>
            <tbody>
              {q.items.map((it) => <QueueRow key={it.key} it={it} onOpenAccount={onOpenAccount} onSnooze={() => setSnoozing(it)} onResolve={() => setResolving(it)} />)}
            </tbody>
          </table>
        )}
      </div>

      {q.snoozed_count > 0 && (
        <div style={{ marginTop: 10 }}>
          <button className="btn small ghost" onClick={() => setShowSnoozed((v) => !v)}>
            {showSnoozed ? "Hide" : "Show"} snoozed ({q.snoozed_count})
          </button>
          {showSnoozed && (
            <div className="card" style={{ marginTop: 8 }}>
              <table>
                <tbody>
                  {q.snoozed.map((it) => (
                    <tr key={it.key}>
                      <td>{it.title}<div className="rowmeta">{it.account_name}{it.program_name ? ` · ${it.program_name}` : ""}</div></td>
                      <td className="rowmeta">{it.snooze_until ? `until ${it.snooze_until}` : it.resurface_condition}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {snoozing && <SnoozePanel item={snoozing} onClose={() => setSnoozing(null)} onDone={after} />}
      {resolving && <ResolvePanel item={resolving} onClose={() => setResolving(null)} onDone={after} />}
    </div>
  );
}

const BAND = { 1: "risk", 2: "risk", 3: "warn", 4: "", 5: "", 6: "" };

function QueueRow({ it, onOpenAccount, onSnooze, onResolve }) {
  return (
    <tr>
      <td><span className={"dot " + BAND[it.priority]} title={`priority ${it.priority}`} /></td>
      <td>
        <div>{it.title}</div>
        <div className="rowmeta">
          <a onClick={() => onOpenAccount(it.account_id)} style={{ cursor: "pointer" }}>{it.account_name}</a>
          {it.program_name ? ` · ${it.program_name}` : ""} — {it.because} <span style={{ color: "var(--accent)" }}>{it.next_action}</span>
        </div>
      </td>
      <td className="rowmeta">{it.age_days}d{it.due_date ? <div>due {it.due_date}</div> : null}</td>
      <td>
        <div className="actions">
          <button className="btn small" onClick={onSnooze}>Snooze</button>
          <button className="btn small ghost" onClick={onResolve}>Resolve</button>
        </div>
      </td>
    </tr>
  );
}

function SnoozePanel({ item, onClose, onDone }) {
  const toast = useToast();
  const [until, setUntil] = useState("");
  const [cond, setCond] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    if (!until && !cond.trim()) { toast("Give a return date or a resurfacing condition.", "err"); return; }
    setSaving(true);
    try {
      await api.snoozeQueue({ item_key: item.key, snooze_until: until || null, resurface_condition: cond.trim() || null });
      toast("Snoozed"); onDone();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }
  return (
    <SlideOver title="Snooze item" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={saving}>Snooze</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{item.title}</div>
      <div className="field"><label>Return date</label><input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></div>
      <div style={{ textAlign: "center", color: "var(--text-3)", margin: "6px 0" }}>or</div>
      <div className="field"><label>Resurfacing condition</label>
        <input value={cond} onChange={(e) => setCond(e.target.value)} placeholder="e.g. if works-council review isn't scheduled by next week" />
        <div className="hint">The item also resurfaces automatically if its underlying facts change.</div>
      </div>
    </SlideOver>
  );
}

function ResolvePanel({ item, onClose, onDone }) {
  const toast = useToast();
  const [desc, setDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const canCreate = !!item.program_id;
  async function save() {
    if (!desc.trim()) { toast("Describe the follow-up action.", "err"); return; }
    setSaving(true);
    try {
      const task = await api.createTask({ program_id: item.program_id, description: desc.trim() });
      await api.resolveQueue({ item_key: item.key, successor_action_type: "task", successor_action_id: task.id });
      toast("Resolved with a follow-up task"); onDone();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }
  return (
    <SlideOver title="Resolve item" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={saving || !canCreate}>Resolve</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{item.title}</div>
      {canCreate ? (
        <div className="field"><label>Link a follow-up task <span className="req">*</span></label>
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Resolving requires a successor action, so risk is never just hidden." />
          <div className="hint">Creates a task in {item.program_name} and marks this item resolved.</div>
        </div>
      ) : (
        <div className="placeholder">This item isn’t tied to a program, so a follow-up task can’t be auto-created here. Convert it or act on it directly.</div>
      )}
    </SlideOver>
  );
}
