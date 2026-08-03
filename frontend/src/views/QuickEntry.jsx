import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast } from "../ui";

// Interaction quick entry — the 30-second capture path.
// Required: account, date, type. Everything else optional; ambiguous notes go
// straight to the inbox with no classification.
export default function QuickEntry({ accounts, preAccount, preProgram, onClose, onSaved }) {
  const toast = useToast();
  const [accountId, setAccountId] = useState(preAccount || (accounts[0]?.id ?? ""));
  const [detail, setDetail] = useState(null); // account detail: programs + people
  const [programId, setProgramId] = useState(preProgram || "");
  const [type, setType] = useState("call");
  const [occurredOn, setOccurredOn] = useState(new Date().toISOString().slice(0, 10));
  const [summary, setSummary] = useState("");
  const [rawNotes, setRawNotes] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [meaningful, setMeaningful] = useState(true);
  const [participants, setParticipants] = useState([]);
  const [inboxLines, setInboxLines] = useState([""]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!accountId) return;
    setDetail(null);
    api.account(accountId).then(setDetail).catch((e) => toast(e.message, "err"));
  }, [accountId]);

  const people = detail?.people ?? [];
  const programs = detail?.programs ?? [];

  const toggleParticipant = (id) =>
    setParticipants((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const setLine = (i, v) => setInboxLines((l) => l.map((x, j) => (j === i ? v : x)));
  const addLine = () => setInboxLines((l) => [...l, ""]);
  const removeLine = (i) => setInboxLines((l) => l.filter((_, j) => j !== i));

  async function save() {
    if (!accountId) return;
    setSaving(true);
    try {
      const inter = await api.createInteraction({
        account_id: accountId,
        program_id: programId || null,
        occurred_on: occurredOn,
        type,
        summary: summary || null,
        raw_notes: rawNotes || null,
        meaningful_touch: meaningful,
        participant_ids: participants,
        inbox_notes: inboxLines.map((s) => s.trim()).filter(Boolean),
      });
      const n = inter.inbox_items.length;
      toast(`Interaction logged${n ? ` · ${n} to inbox` : ""}`);
      onSaved?.(inter);
      onClose();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlideOver
      title="Log interaction"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={saving || !accountId}>
            {saving ? "Logging…" : "Log interaction"}
          </button>
        </>
      }
    >
      <div className="grid2">
        <div className="field">
          <label>Account <span className="req">*</span></label>
          <select value={accountId} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); setParticipants([]); }}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Program</label>
          <select value={programId} onChange={(e) => setProgramId(e.target.value)}>
            <option value="">— account-level (no program) —</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      <div className="grid2">
        <div className="field">
          <label>Type <span className="req">*</span></label>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {["call", "meeting", "email", "workshop", "message", "other"].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Date <span className="req">*</span></label>
          <input type="date" value={occurredOn} onChange={(e) => setOccurredOn(e.target.value)} />
        </div>
      </div>

      <div className="field">
        <label>Participants</label>
        <div className="chips" style={{ marginBottom: 8 }}>
          {participants.length === 0 && <span className="rowmeta">none selected</span>}
          {participants.map((id) => {
            const p = people.find((x) => x.id === id);
            return (
              <span className="chip" key={id}>
                {p?.name ?? id}
                <button onClick={() => toggleParticipant(id)} aria-label="remove">×</button>
              </span>
            );
          })}
        </div>
        <select value="" onChange={(e) => e.target.value && toggleParticipant(e.target.value)}>
          <option value="">+ add participant…</option>
          {people.filter((p) => !participants.includes(p.id)).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}{p.affiliation === "valence" ? " (Valence)" : ""}{p.title ? ` — ${p.title}` : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Summary</label>
        <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What moved, in a line" />
      </div>

      <div className="field">
        <label>Notes <span className="tag-internal">internal only</span></label>
        <textarea value={rawNotes} onChange={(e) => setRawNotes(e.target.value)} placeholder="Rough notes; never shown in client-facing output" />
      </div>

      <div className="field checkline">
        <input id="mt" type="checkbox" checked={meaningful} onChange={(e) => setMeaningful(e.target.checked)} />
        <label htmlFor="mt" style={{ margin: 0 }}>Meaningful touch (counts toward last-touch & coverage)</label>
      </div>

      <div className="field">
        <label>To inbox — triage later, no classification now</label>
        {inboxLines.map((line, i) => (
          <div className="inbox-line" key={i}>
            <input value={line} onChange={(e) => setLine(i, e.target.value)} placeholder='e.g. "Sofie to secure DPO sign-off before activation"' />
            {inboxLines.length > 1 && <button className="btn small" onClick={() => removeLine(i)}>×</button>}
          </div>
        ))}
        <button className="btn small ghost" onClick={addLine}>+ another note</button>
        <div className="hint">Conversion to a commitment / risk / task arrives in v0.2.</div>
      </div>
    </SlideOver>
  );
}
