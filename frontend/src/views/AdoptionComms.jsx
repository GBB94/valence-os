import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, SlideOver, fmtDate, useToast } from "../ui";

const CHANNELS = ["email", "teams", "slack", "web", "mobile", "other"];
const SESSION_TYPES = ["webinar", "office_hours"];

export default function AdoptionComms({ accountId, programId, reloadKey }) {
  const toast = useToast();
  const [sequences, setSequences] = useState([]);
  const [populations, setPopulations] = useState([]);
  const [panel, setPanel] = useState(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    try {
      const [sequenceResult, partition, views] = await Promise.all([
        api.commsSequences(accountId),
        api.partition(accountId).catch(() => ({ segments: [] })),
        api.populationViews(accountId).catch(() => []),
      ]);
      setSequences(sequenceResult.sequences);
      setPopulations([
        ...(partition.segments || []).map((p) => ({ ...p, kind: "segment" })),
        ...(views || []).map((p) => ({ ...p, kind: "view" })),
      ]);
    } catch (e) { toast(e.message, "err"); }
  }, [accountId, toast]);
  useEffect(() => { if (accountId) load(); }, [accountId, reloadKey, tick, load]);
  const visible = useMemo(
    () => programId ? sequences.filter((s) => s.program_id === programId) : sequences,
    [sequences, programId],
  );
  const saved = () => { setPanel(null); setTick((n) => n + 1); };

  async function markSent(wave) {
    try { await api.markCommsWaveSent(wave.id); toast("Send recorded — no message was transmitted"); setTick((n) => n + 1); }
    catch (e) { toast(e.message, "err"); }
  }
  async function cancelWave(wave) {
    try { await api.cancelCommsWave(wave.id); toast("Wave cancelled"); setTick((n) => n + 1); }
    catch (e) { toast(e.message, "err"); }
  }

  return (
    <div className="card">
      <div className="card-h">
        <div>
          <h3>Adoption communications</h3>
          <div className="rowmeta">Planned waves and session attendance · never auto-sent</div>
        </div>
        <div className="spacer" />
        <button className="btn small" disabled={!programId}
          title={programId ? "Create a planned sequence" : "Select a program first"}
          onClick={() => setPanel({ kind: "sequence" })}>New sequence</button>
      </div>
      {visible.length === 0 ? (
        <Empty title="No communication sequences">
          {programId ? "Plan a launch, reinforcement, or live-session sequence." : "Select a program to plan communication waves."}
        </Empty>
      ) : visible.map((sequence) => (
        <section key={sequence.id} className="comms-sequence">
          <div className="actions comms-sequence-head">
            <Status status={sequence.status} />
            <div><strong>{sequence.name}</strong>{sequence.purpose && <div className="rowmeta">{sequence.purpose}</div>}</div>
            <div className="spacer" />
            {sequence.status !== "cancelled" && <>
              <button className="btn small ghost" onClick={() => setPanel({ kind: "session", sequence })}>Add session</button>
              <button className="btn small" onClick={() => setPanel({ kind: "wave", sequence })}>Add wave</button>
              <button className="btn small ghost" onClick={() => setPanel({ kind: "sequenceCancel", sequence })}>Cancel sequence</button>
            </>}
          </div>
          <WaveTable sequence={sequence} onSent={markSent} onCancel={cancelWave} />
          <SessionTable sequence={sequence} onAttendee={(event) => setPanel({ kind: "attendee", event })} />
        </section>
      ))}
      {panel && <Editor panel={panel} programId={programId} populations={populations}
        onClose={() => setPanel(null)} onSaved={saved} />}
    </div>
  );
}

function Status({ status }) {
  const cls = status === "complete" ? "ok" : status === "running" ? "warn" : status === "cancelled" ? "risk" : "";
  return <span className="badge"><span className={`dot ${cls}`} /> {status}</span>;
}

function WaveTable({ sequence, onSent, onCancel }) {
  if (!sequence.waves.length) return <div className="rowmeta comms-empty-row">No waves yet.</div>;
  return (
    <table className="comms-table">
      <thead><tr><th>Wave</th><th>Audience and message</th><th>Expected</th><th>State</th><th>Actions</th></tr></thead>
      <tbody>{sequence.waves.map((wave) => (
        <tr key={wave.id}>
          <td><strong>{wave.wave_number}</strong>{wave.channel && <div className="rowmeta">{wave.channel}</div>}</td>
          <td>{wave.message}<div className="rowmeta">{wave.population || wave.audience || "Audience not modeled"}</div></td>
          <td>{wave.expected_send_on ? fmtDate(wave.expected_send_on) : <span className="unknown-fill">unknown</span>}
            {wave.date_provisional && <div className="rowmeta">provisional · follows prior send</div>}</td>
          <td><Status status={wave.status} />{wave.sent_at && <div><AgeChip date={wave.sent_at} /></div>}</td>
          <td className="actions-cell">{wave.status === "planned" && <>
            <button className="btn small primary" onClick={() => onSent(wave)}>Record sent</button>
            <button className="btn small ghost" onClick={() => onCancel(wave)}>Cancel</button>
          </>}</td>
        </tr>
      ))}</tbody>
    </table>
  );
}

function SessionTable({ sequence, onAttendee }) {
  if (!sequence.sessions.length) return null;
  return (
    <div className="comms-sessions">
      <div className="band-head">Sessions</div>
      <table className="comms-table">
        <thead><tr><th>Session</th><th>When</th><th>Attendance</th><th>Actions</th></tr></thead>
        <tbody>{sequence.sessions.map((event) => (
          <tr key={event.id}>
            <td><strong>{event.title}</strong><div className="rowmeta">{event.purpose.replace(/_/g, " ")}</div></td>
            <td>{fmtDate(event.starts_at)} <AgeChip date={event.starts_at} /></td>
            <td><Attendance value={event.attendance} /></td>
            <td className="actions-cell"><button className="btn small" onClick={() => onAttendee(event)}>Record attendee</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Attendance({ value }) {
  if (value.state === "known") return <span>{value.attended} of {value.invited} attended<div className="rowmeta">{value.no_show} no-show · {value.unknown} unknown</div></span>;
  if (value.state === "suppressed") return <span className="unknown-fill">suppressed<div className="rowmeta">{value.reason}</div></span>;
  if (value.state === "incomplete") return <span className="unknown-fill">incomplete<div className="rowmeta">{value.reason}</div></span>;
  return <span className="unknown-fill">unknown<div className="rowmeta">{value.reason}</div></span>;
}

function Editor({ panel, programId, populations, onClose, onSaved }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(() => initial(panel));
  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  async function save() {
    setBusy(true);
    try {
      if (panel.kind === "sequence") await api.createCommsSequence({ program_id: programId, name: form.name, purpose: form.purpose || null });
      if (panel.kind === "wave") {
        const pop = populations.find((p) => `${p.kind}:${p.id}` === form.population);
        const previous = form.follows_entry_id || null;
        await api.createCommsWave(panel.sequence.id, {
          message: form.message, audience: form.audience || null, channel: form.channel,
          send_date: form.send_date || null, wave_number: Number(form.wave_number),
          follows_entry_id: previous, offset_days: previous ? Number(form.offset_days) : null,
          segment_id: pop?.kind === "segment" ? pop.id : null,
          view_id: pop?.kind === "view" ? pop.id : null,
        });
      }
      if (panel.kind === "session") await api.createCommsSession({
        comms_sequence_id: panel.sequence.id, invited_by_entry_id: form.invited_by_entry_id || null,
        purpose: form.purpose, title: form.title, starts_at: new Date(form.starts_at).toISOString(),
        location: form.location || null,
      });
      if (panel.kind === "attendee") await api.recordSessionAttendee(panel.event.id, {
        name: form.name || null, email: form.email, attendance_scope: form.attendance_scope,
        attendance_status: form.attendance_status, response_status: "unknown",
      });
      if (panel.kind === "sequenceCancel") await api.cancelCommsSequence(panel.sequence.id, form.reason);
      toast(panel.kind === "attendee" ? "Attendance fact recorded" : "Plan updated"); onSaved();
    } catch (e) { toast(e.message, "err"); }
    setBusy(false);
  }
  const titles = { sequence: "New communication sequence", wave: "Add planned wave", session: "Add live session", attendee: "Record attendee", sequenceCancel: "Cancel communication sequence" };
  return (
    <SlideOver title={titles[panel.kind]} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy} onClick={save}>Save</button></>}>
      {panel.kind === "sequence" && <>
        <Field label="Sequence name"><input autoFocus value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Purpose"><textarea value={form.purpose} onChange={(e) => set("purpose", e.target.value)} /></Field>
        <p className="rowmeta">This creates a plan only. It cannot send or schedule a message.</p>
      </>}
      {panel.kind === "wave" && <>
        <Field label="Wave number"><input type="number" min="1" value={form.wave_number} onChange={(e) => set("wave_number", e.target.value)} /></Field>
        <Field label="Message"><textarea autoFocus value={form.message} onChange={(e) => set("message", e.target.value)} /></Field>
        <Field label="Audience label"><input value={form.audience} onChange={(e) => set("audience", e.target.value)} /></Field>
        <Field label="Modeled cohort"><select value={form.population} onChange={(e) => set("population", e.target.value)}><option value="">none — attendance unavailable</option>{populations.map((p) => <option key={`${p.kind}:${p.id}`} value={`${p.kind}:${p.id}`}>{p.name} ({p.kind})</option>)}</select></Field>
        <Field label="Channel"><select value={form.channel} onChange={(e) => set("channel", e.target.value)}>{CHANNELS.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="Planned send date"><input type="date" value={form.send_date} onChange={(e) => set("send_date", e.target.value)} /></Field>
        {panel.sequence.waves.length > 0 && <>
          <Field label="Follows"><select value={form.follows_entry_id} onChange={(e) => set("follows_entry_id", e.target.value)}><option value="">independent date</option>{panel.sequence.waves.filter((w) => w.status !== "cancelled").map((w) => <option key={w.id} value={w.id}>Wave {w.wave_number}</option>)}</select></Field>
          {form.follows_entry_id && <Field label="Days after prior send"><input type="number" min="0" value={form.offset_days} onChange={(e) => set("offset_days", e.target.value)} /></Field>}
        </>}
      </>}
      {panel.kind === "session" && <>
        <Field label="Session type"><select value={form.purpose} onChange={(e) => set("purpose", e.target.value)}>{SESSION_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select></Field>
        <Field label="Title"><input autoFocus value={form.title} onChange={(e) => set("title", e.target.value)} /></Field>
        <Field label="Starts"><input type="datetime-local" value={form.starts_at} onChange={(e) => set("starts_at", e.target.value)} /></Field>
        <Field label="Invitation wave"><select value={form.invited_by_entry_id} onChange={(e) => set("invited_by_entry_id", e.target.value)}><option value="">none — attendance unavailable</option>{panel.sequence.waves.map((w) => <option key={w.id} value={w.id}>Wave {w.wave_number} · {w.population || w.audience || "unmodeled"}</option>)}</select></Field>
        <Field label="Location"><input value={form.location} onChange={(e) => set("location", e.target.value)} /></Field>
      </>}
      {panel.kind === "attendee" && <>
        <Field label="Name"><input value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Email"><input autoFocus type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Session role"><select value={form.attendance_scope} onChange={(e) => set("attendance_scope", e.target.value)}>{["audience", "facilitator", "observer", "unknown"].map((s) => <option key={s}>{s}</option>)}</select></Field>
        <Field label="Attendance"><select value={form.attendance_status} onChange={(e) => set("attendance_status", e.target.value)}>{["attended", "no_show", "invited", "unknown"].map((s) => <option key={s}>{s.replace(/_/g, " ")}</option>)}</select></Field>
        <p className="rowmeta">Attendance is meeting engagement only. It is never joined to product usage.</p>
      </>}
      {panel.kind === "sequenceCancel" && <>
        <Field label="Cancellation reason"><textarea autoFocus value={form.reason} onChange={(e) => set("reason", e.target.value)} /></Field>
        <p className="rowmeta">Cancelling stops the plan. It does not transmit or recall any message.</p>
      </>}
    </SlideOver>
  );
}

function initial(panel) {
  if (panel.kind === "sequence") return { name: "", purpose: "" };
  if (panel.kind === "wave") return { message: "", audience: "", channel: "email", send_date: "", population: "", wave_number: panel.sequence.waves.length + 1, follows_entry_id: "", offset_days: 3 };
  if (panel.kind === "session") return { purpose: "webinar", title: "", starts_at: "", invited_by_entry_id: "", location: "" };
  if (panel.kind === "sequenceCancel") return { reason: "" };
  return { name: "", email: "", attendance_scope: "audience", attendance_status: "attended" };
}

function Field({ label, children }) { return <div className="field"><label>{label}</label>{children}</div>; }
