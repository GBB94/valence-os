import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast, fmtDate } from "../ui";

export default function CalendarPanel({ accountId, reloadKey, programId }) {
  const toast = useToast();
  const [events, setEvents] = useState(null);
  const [tick, setTick] = useState(0);
  const [adding, setAdding] = useState(false);
  const load = () => api.calendarEvents(accountId).then((r) => setEvents(r.events)).catch((e) => toast(e.message, "err"));
  useEffect(() => { if (accountId) load(); }, [accountId, reloadKey, tick]);
  const sync = async () => {
    try { const r = await api.syncCalendar(); toast(`${r.result?.created || 0} calendar events synced`); setTick((x) => x + 1); }
    catch (e) { toast(e.message, "err"); }
  };
  return <div className="card">
    <div className="card-h"><h3>Calendar</h3><div className="spacer" />
      <button className="btn small ghost" onClick={sync}>Sync mock .ics</button>
      <button className="btn small" onClick={() => setAdding(true)}>Schedule</button></div>
    {!events ? <div className="subtle" style={{ padding: "var(--sp-5)" }}>Loading…</div> : events.length === 0
      ? <Empty title="No calendar entries">Sync the mock fixture or schedule a kickoff, governance meeting, or value review.</Empty>
      : <table><thead><tr><th>Moment</th><th>When</th><th>Attendance facts</th><th>Source</th></tr></thead>
        <tbody>{events.map((e) => <tr key={e.id}>
          <td>{e.title}<div className="rowmeta">{e.purpose.replace(/_/g, " ")}{e.location ? ` · ${e.location}` : ""}</div></td>
          <td className="rowmeta">{fmtDate(e.starts_at)}</td>
          <td className="rowmeta">{e.attendees.length ? e.attendees.map((a) => `${a.person_name || a.name || a.email}: ${a.attendance_status}`).join(" · ") : "none recorded"}</td>
          <td><span className="badge">{e.direction === "read" ? "mock read" : "local write"}</span></td>
        </tr>)}</tbody></table>}
    {adding && <AddEvent accountId={accountId} programId={programId} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setTick((x) => x + 1); }} />}
  </div>;
}

function AddEvent({ accountId, programId, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ purpose: "governance", title: "", starts_at: "" });
  const save = async () => {
    if (!f.title.trim() || !f.starts_at) { toast("Title and date/time are required", "err"); return; }
    try { await api.createCalendarEvent({ account_id: accountId, program_id: programId || null, ...f }); toast("Local calendar entry saved"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  };
  return <SlideOver title="Schedule a calendar moment" onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Schedule</button></>}>
    <div className="field"><label>Purpose</label><select value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })}>
      {["kickoff", "governance", "qbr", "deployment_moment", "other"].map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}</select></div>
    <div className="field"><label>Title</label><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
    <div className="field"><label>Starts</label><input type="datetime-local" value={f.starts_at} onChange={(e) => setF({ ...f, starts_at: e.target.value })} /></div>
  </SlideOver>;
}
