import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, useToast, fmtDate } from "../ui";

// Program-scoped timeline (Section 6b): milestones as diamonds, deployment moments
// as dots, renewal marker, today line. Limited palette; color for status/key markers only.
export default function Timeline({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [programId, setProgramId] = useState("");
  const [data, setData] = useState(null);
  const [contracts, setContracts] = useState([]);

  useEffect(() => {
    if (!accountId) return;
    api.account(accountId).then((a) => {
      setDetail(a);
      if (a.programs[0]) setProgramId((pid) => pid || a.programs[0].id);
    }).catch((e) => toast(e.message, "err"));
    api.contracts(accountId).then(setContracts).catch(() => {});
  }, [accountId]);

  useEffect(() => {
    if (!programId) return;
    Promise.all([api.program(programId), api.programDelivery(programId)])
      .then(([p, d]) => setData({ program: p, delivery: d }))
      .catch((e) => toast(e.message, "err"));
  }, [programId, reloadKey]);

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;
  const programs = detail?.programs ?? [];

  // gather dated markers
  const markers = [];
  if (data) {
    for (const m of data.program.execution?.milestones ?? [])
      if (m.target_date) markers.push({ date: m.target_date, kind: "milestone", label: m.name, status: m.status });
    for (const mo of data.delivery.deployment_moments ?? [])
      if (mo.event_date) markers.push({ date: mo.event_date, kind: "moment", label: mo.name });
  }
  const current = contracts.find((c) => c.is_current);
  if (current?.renewal_date) markers.push({ date: current.renewal_date, kind: "renewal", label: "Renewal" });

  const today = new Date().toISOString().slice(0, 10);
  const dates = markers.map((m) => m.date).concat(today);
  const min = dates.reduce((a, b) => (a < b ? a : b), today);
  const max = dates.reduce((a, b) => (a > b ? a : b), today);
  const span = Math.max(1, (new Date(max) - new Date(min)) / 86400000);
  const pct = (d) => `${((new Date(d) - new Date(min)) / 86400000 / span) * 100}%`;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Timeline</h1>
        <select value={accountId || ""} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); }} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={sel}>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!data ? <div className="subtle">Loading…</div> : markers.length === 0 ? (
        <div className="placeholder">No dated milestones, moments, or renewal for this program yet.</div>
      ) : (
        <div className="card" style={{ padding: "28px 24px" }}>
          <div style={{ position: "relative", height: 120, marginTop: 10 }}>
            {/* axis */}
            <div style={{ position: "absolute", top: 60, left: 0, right: 0, height: 2, background: "var(--border-strong)" }} />
            {/* today */}
            <div style={{ position: "absolute", top: 30, bottom: 20, left: pct(today), width: 2, background: "var(--accent)" }} title="today">
              <span style={{ position: "absolute", top: -18, left: -14, fontSize: 10, color: "var(--accent)" }}>today</span>
            </div>
            {markers.sort((a, b) => a.date.localeCompare(b.date)).map((m, i) => (
              <div key={i} style={{ position: "absolute", left: pct(m.date), top: 60, transform: "translate(-50%,-50%)" }} title={`${m.label} · ${m.date}`}>
                <Marker kind={m.kind} status={m.status} />
                <div style={{ position: "absolute", top: i % 2 ? 12 : -34, left: "50%", transform: "translateX(-50%)", whiteSpace: "nowrap", fontSize: 11, color: "var(--text-2)" }}>
                  {m.label}<div className="rowmeta" style={{ textAlign: "center" }}>{m.date}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="rowmeta" style={{ marginTop: 20, display: "flex", gap: 16 }}>
            <span><Marker kind="milestone" /> milestone</span>
            <span><Marker kind="moment" /> deployment moment</span>
            <span><Marker kind="renewal" /> renewal</span>
          </div>
        </div>
      )}
      <div className="rowmeta" style={{ marginTop: 8 }}>Two-timescale swimlanes and the full workstream view are refined further in v3; this is the v1 dated skeleton.</div>
    </div>
  );
}

function Marker({ kind, status }) {
  if (kind === "milestone") {
    const c = status === "complete" ? "var(--ok)" : "var(--warn)";
    return <span style={{ display: "inline-block", width: 12, height: 12, background: c, transform: "rotate(45deg)", verticalAlign: "middle" }} />;
  }
  if (kind === "renewal") return <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 2, background: "var(--accent)", verticalAlign: "middle" }} />;
  return <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: "50%", background: "var(--text-2)", verticalAlign: "middle" }} />;
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
