import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, Loading, useToast, fmtDate } from "../ui";
import { DependencyLines } from "./PathAdvance";

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

  // gather dated markers by workstream lane
  const markers = [];
  if (data) {
    for (const m of data.program.execution?.milestones ?? [])
      if (m.target_date) markers.push({ date: m.target_date, kind: "milestone", lane: "Milestones", label: m.name, status: m.status });
    for (const mo of data.delivery.deployment_moments ?? [])
      if (mo.event_date) markers.push({ date: mo.event_date, kind: "moment", lane: "Deployment moments", label: mo.name });
    for (const c of data.delivery.comms_entries ?? [])
      if (c.send_date) markers.push({ date: c.send_date, kind: "comms", lane: "Comms", label: c.message || c.audience || "comms" });
  }
  const current = contracts.find((c) => c.is_current);
  if (current?.renewal_date) markers.push({ date: current.renewal_date, kind: "renewal", lane: "Renewal", label: "Renewal" });
  const LANES = ["Milestones", "Deployment moments", "Comms", "Renewal"].filter((l) => markers.some((m) => m.lane === l));

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

      {!data ? <Loading what="timeline" /> : markers.length === 0 ? (
        <div className="placeholder">No dated milestones, moments, comms, or renewal for this program yet.</div>
      ) : (
        <div className="card" style={{ padding: "16px 24px 24px" }}>
          {/* date axis header */}
          <div style={{ position: "relative", height: 18, marginLeft: 140 }}>
            <span className="rowmeta" style={{ position: "absolute", left: 0 }}>{min}</span>
            <span className="rowmeta" style={{ position: "absolute", right: 0 }}>{max}</span>
          </div>
          {/* one swimlane per workstream */}
          {LANES.map((lane) => (
            <div key={lane} style={{ display: "flex", alignItems: "center", borderTop: "1px solid var(--line-hairline)", minHeight: 46 }}>
              <div className="rowmeta" style={{ width: 140, flex: "none", textTransform: "uppercase", letterSpacing: ".04em" }}>{lane}</div>
              <div style={{ position: "relative", flex: 1, height: 46 }}>
                {/* lane baseline + today marker */}
                <div style={{ position: "absolute", top: 23, left: 0, right: 0, height: 1, background: "var(--line-hairline)" }} />
                <div style={{ position: "absolute", top: 0, bottom: 0, left: pct(today), width: 2, background: "var(--data-1)", opacity: 0.5 }} title="today" />
                {markers.filter((m) => m.lane === lane).sort((a, b) => a.date.localeCompare(b.date)).map((m, i) => (
                  <div key={i} style={{ position: "absolute", left: pct(m.date), top: 23, transform: "translate(-50%,-50%)" }} title={`${m.label} · ${m.date}`}>
                    <Marker kind={m.kind} status={m.status} />
                    <div style={{ position: "absolute", top: 10, left: "50%", transform: "translateX(-50%)", whiteSpace: "nowrap", fontSize: "var(--t-micro)", color: "var(--ink-secondary)" }}>
                      {(m.label || "").slice(0, 22)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {/* §15.8 — dependency lines, and only the explicit ones. Rendered under the chart as a
              secondary band rather than drawn across it: a dependency is real but subordinate to
              the dated marker it hangs off, and nothing here is inferred from a shared date. */}
          <TimelineDependencies milestones={(data.program.execution?.milestones ?? [])
            .filter((m) => m.target_date)} />
          <div className="rowmeta" style={{ marginTop: 16, display: "flex", gap: 16, flexWrap: "wrap" }}>
            <span><Marker kind="milestone" status="complete" /> milestone complete</span>
            <span><Marker kind="milestone" /> milestone due</span>
            <span><Marker kind="moment" /> deployment moment</span>
            <span><Marker kind="comms" /> comms</span>
            <span><Marker kind="renewal" /> renewal</span>
            <span style={{ color: "var(--data-1)" }}>│ today</span>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * One row per milestone that has at least one accepted relation. A milestone with none draws
 * nothing — the absence of a line is the absence of a recorded dependency, not a rendering gap,
 * and inventing one from a shared date or owner is what §15.2 forbids.
 */
function TimelineDependencies({ milestones }) {
  const [links, setLinks] = useState({});
  useEffect(() => {
    let live = true;
    setLinks({});
    Promise.all(milestones.map((m) => api.milestoneActionLinks(m.id)
      .then((r) => [m.id, r.links || []])
      .catch(() => [m.id, []])))
      .then((pairs) => { if (live) setLinks(Object.fromEntries(pairs)); });
    return () => { live = false; };
  }, [milestones.map((m) => m.id).join(",")]);

  const withLinks = milestones.filter((m) => (links[m.id] || []).length > 0);
  if (withLinks.length === 0) return null;
  return (
    <div className="path-deps-band">
      <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>
        Dependencies
      </div>
      {withLinks.map((m) => (
        <div key={m.id} className="path-deps-milestone">
          <span className="rowmeta">{m.name}</span>
          <DependencyLines milestoneId={m.id} />
        </div>
      ))}
      <div className="rowmeta">
        Explicit relationships only. Nothing here is inferred from a shared date, owner, or wording.
      </div>
    </div>
  );
}

function Marker({ kind, status }) {
  if (kind === "milestone") {
    // Complete = filled, due = hollow: the shape difference carries the state, never hue alone.
    const done = status === "complete";
    return <span style={{ display: "inline-block", width: 12, height: 12, transform: "rotate(45deg)", verticalAlign: "middle",
      background: done ? "var(--status-ok)" : "transparent",
      border: done ? "0" : "2px solid var(--status-warn)", boxSizing: "border-box" }} />;
  }
  if (kind === "renewal") return <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 2, background: "var(--data-1)", verticalAlign: "middle" }} />;
  if (kind === "comms") return <span style={{ display: "inline-block", width: 10, height: 10, background: "var(--data-2)", verticalAlign: "middle" }} />;
  return <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: "50%", background: "var(--ink-secondary)", verticalAlign: "middle" }} />;
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
