import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast, fmtDate } from "../ui";

// Operations screen (Module P): say when the tool is broken without reading server logs.
export default function Operations({ reloadKey }) {
  const toast = useToast();
  const [ops, setOps] = useState(null);
  useEffect(() => { api.operations().then(setOps).catch((e) => toast(e.message, "err")); }, [reloadKey]);
  if (!ops) return <div className="subtle">Loading…</div>;

  return (
    <div>
      <h1>Operations</h1>
      <div className="rowmeta" style={{ marginBottom: 14 }}>As of {ops.as_of}. Mock/local mode.</div>

      <div className="two-col" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div className="card" style={{ padding: 12 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase" }}>Job worker</div>
          <div>{ops.job_worker}</div>
          <div className="rowmeta" style={{ marginTop: 10, textTransform: "uppercase" }}>Audit events</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{ops.audit_events.toLocaleString()}</div>
        </div>
        <div className="card" style={{ padding: 12 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase" }}>Backup</div>
          <div>RPO {ops.backup.rpo_hours}h · last restore test: {ops.backup.last_restore_test || "not run"}</div>
          <div className="rowmeta" style={{ marginTop: 6 }}>{ops.backup.note}</div>
        </div>
      </div>

      <h2>Source freshness</h2>
      <div className="card">
        {ops.source_freshness.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No metric sources.</div> : (
          <table><thead><tr><th>Metric</th><th style={{ width: 150 }}>Current through</th><th style={{ width: 100 }}>State</th></tr></thead>
            <tbody>{ops.source_freshness.map((f, i) => (
              <tr key={i}><td>{f.metric}</td><td className="rowmeta">{fmtDate(f.current_through)}</td>
                <td>{f.stale ? <span style={{ color: "var(--warn)" }}>⚠ stale</span> : <span style={{ color: "var(--ok)" }}>fresh</span>}</td></tr>
            ))}</tbody></table>
        )}
      </div>

      <h2>Import batches</h2>
      <div className="card">
        {ops.import_batches.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No imports yet.</div> : (
          <table><thead><tr><th>Adapter</th><th style={{ width: 70 }}>Rows</th><th style={{ width: 120 }}>Status</th><th style={{ width: 140 }}>Created</th></tr></thead>
            <tbody>{ops.import_batches.map((b) => (
              <tr key={b.id}><td>{b.adapter}</td><td className="rowmeta">{b.row_count}</td>
                <td><span className="badge" style={b.status === "rolled_back" ? { borderColor: "var(--risk)", color: "var(--risk)" } : {}}>{b.status}</span></td>
                <td className="rowmeta">{b.created_at?.slice(0, 10)}</td></tr>
            ))}</tbody></table>
        )}
        {ops.failed_or_rolled_back > 0 && <div className="rowmeta" style={{ padding: "8px 12px", color: "var(--risk)" }}>{ops.failed_or_rolled_back} rolled-back batch(es).</div>}
      </div>
    </div>
  );
}
