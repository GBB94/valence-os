import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast } from "../ui";

// Convert an inbox item into one execution object — no retype.
const TARGETS = ["commitment", "risk", "task", "issue", "decision"];

export default function ConvertPanel({ item, onClose, onConverted }) {
  const toast = useToast();
  const account = item.interaction?.account_id;
  const [detail, setDetail] = useState(null);
  const [target, setTarget] = useState("commitment");
  const [programId, setProgramId] = useState(item.interaction?.program_id || "");
  const [desc, setDesc] = useState(item.raw_text);
  const [saving, setSaving] = useState(false);

  // commitment / task fields
  const [responsible, setResponsible] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  // risk / issue
  const [severity, setSeverity] = useState("medium");
  const [blocker, setBlocker] = useState(false);
  // decision
  const [rationale, setRationale] = useState("");

  useEffect(() => {
    if (account) api.account(account).then(setDetail).catch((e) => toast(e.message, "err"));
  }, [account]);

  const people = detail?.people ?? [];
  const valence = people.filter((p) => p.affiliation === "valence");
  const programs = detail?.programs ?? [];
  const accountLevel = !item.interaction?.program_id;

  async function save() {
    setSaving(true);
    try {
      const payload = { description: desc };
      if (accountLevel) {
        if (!programId) throw new Error("Pick a program — this note came from an account-level interaction.");
        payload.program_id = programId;
      }
      if (target === "commitment") {
        if (!responsible || !owner || !due) throw new Error("Commitment needs a responsible party, internal owner, and due date.");
        Object.assign(payload, { responsible_party_id: responsible, internal_owner_id: owner, due_date: due });
      } else if (target === "task") {
        if (owner) payload.internal_owner_id = owner;
        if (due) payload.due_date = due;
      } else if (target === "risk") {
        Object.assign(payload, { severity, is_blocker: blocker });
      } else if (target === "issue") {
        payload.is_blocker = blocker;
      } else if (target === "decision") {
        if (rationale) payload.rationale = rationale;
      }
      const res = await api.convertInbox(item.id, { target_type: target, payload });
      toast(`Converted to ${target}`);
      onConverted?.(res);
      onClose();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlideOver
      title="Convert inbox note"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Converting…" : `Create ${target}`}</button>
        </>
      }
    >
      <div className="field">
        <label>Convert to</label>
        <div className="chips">
          {TARGETS.map((t) => (
            <button key={t} className={"btn small" + (target === t ? " selected" : "")} aria-pressed={target === t} onClick={() => setTarget(t)}>{t}</button>
          ))}
        </div>
      </div>

      {accountLevel && (
        <div className="field">
          <label>Program <span className="req">*</span></label>
          <select value={programId} onChange={(e) => setProgramId(e.target.value)}>
            <option value="">— pick a program —</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div className="hint">The source interaction is account-level, so a program is required.</div>
        </div>
      )}

      <div className="field">
        <label>Description</label>
        <textarea value={desc} onChange={(e) => setDesc(e.target.value)} />
        <div className="hint">Pre-filled from the note. Edit if needed — nothing is retyped from scratch.</div>
      </div>

      {target === "commitment" && (
        <>
          <div className="field">
            <label>Responsible party <span className="req">*</span> <span className="hint" style={{textTransform:'none'}}>— who performs it (often client)</span></label>
            <select value={responsible} onChange={(e) => setResponsible(e.target.value)}>
              <option value="">— select —</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.affiliation === "valence" ? " (Valence)" : ""}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Internal owner <span className="req">*</span> <span className="hint" style={{textTransform:'none'}}>— Valence follow-up owner</span></label>
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">— select —</option>
              {valence.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Due date <span className="req">*</span></label>
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        </>
      )}

      {target === "task" && (
        <div className="grid2">
          <div className="field">
            <label>Owner</label>
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">— unassigned —</option>
              {valence.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Due date</label>
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        </div>
      )}

      {(target === "risk" || target === "issue") && (
        <div className="grid2">
          {target === "risk" && (
            <div className="field">
              <label>Severity</label>
              <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                {["low", "medium", "high"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          )}
          <div className="field checkline" style={{ marginTop: 22 }}>
            <input id="blk" type="checkbox" checked={blocker} onChange={(e) => setBlocker(e.target.checked)} />
            <label htmlFor="blk" style={{ margin: 0 }}>Active blocker</label>
          </div>
        </div>
      )}

      {target === "decision" && (
        <div className="field">
          <label>Rationale</label>
          <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Why this was decided" />
        </div>
      )}
    </SlideOver>
  );
}
