import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast, fmtDate } from "../ui";

// Metrics scoreboard (Section 6b): 5-second read, number/target/delta, freshness stamp,
// stale = unknown (enforced server-side). Plus benchmarks and the CSV import adapter.
export default function Metrics({ reloadKey }) {
  const toast = useToast();
  const [sb, setSb] = useState(null);
  const [benchmarks, setBenchmarks] = useState([]);
  const [ops, setOps] = useState(null);
  const [importing, setImporting] = useState(false);
  const [tick, setTick] = useState(0);

  async function load() {
    try {
      const [s, b, o] = await Promise.all([api.scoreboard(), api.benchmarks(), api.operations()]);
      setSb(s); setBenchmarks(b); setOps(o);
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [reloadKey, tick]);

  async function rollback(id) {
    try { await api.importRollback(id); toast("Import rolled back"); setTick((t) => t + 1); }
    catch (e) { toast(e.message, "err"); }
  }

  if (!sb) return <div className="subtle">Loading…</div>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>Metrics</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setImporting(true)}>Import observations (CSV)</button>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>As of {sb.as_of}. Definitions are Data-team-owned and ingested; stale data renders as unknown, never carried-forward.</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
        {sb.cards.map((c) => {
          const o = c.observation;
          const delta = o && o.target != null && !c.stale ? o.value - o.target : null;
          return (
            <div className="card" key={c.definition.id} style={{ padding: 12 }}>
              <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em" }}>{c.definition.name}</div>
              <div style={{ fontSize: 24, fontWeight: 700, margin: "4px 0" }}>
                {c.display_value === "unknown" ? <span style={{ color: "var(--text-3)" }}>unknown</span> : fmtNum(c.display_value, o?.unit)}
              </div>
              {o && !c.stale && (
                <div className="rowmeta">
                  target {fmtNum(o.target, o.unit)}{delta != null && <span style={{ color: delta >= 0 ? "var(--ok)" : "var(--risk)", marginLeft: 6 }}>{delta >= 0 ? "▲" : "▼"} {fmtNum(Math.abs(delta), o.unit)}</span>}
                </div>
              )}
              <div className="rowmeta" style={{ marginTop: 6 }}>
                {c.stale
                  ? <span style={{ color: "var(--warn)" }}>⚠ stale — current through {fmtDate(o?.current_through)}</span>
                  : o ? `current through ${fmtDate(o.current_through)} · v${c.definition.version}` : "no observation"}
              </div>
            </div>
          );
        })}
      </div>

      <h2>Benchmarks</h2>
      <div className="card">
        {benchmarks.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No benchmarks.</div> : (
          <table>
            <thead><tr><th>Benchmark</th><th style={{ width: 90 }}>Value</th><th>Population · period</th><th>Source · version</th></tr></thead>
            <tbody>
              {benchmarks.map((b) => (
                <tr key={b.id}><td>{b.name}</td><td>{fmtNum(b.value, b.unit)}</td>
                  <td className="rowmeta">{b.population} · {b.period}</td>
                  <td className="rowmeta">{b.source} · v{b.version}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="rowmeta" style={{ padding: "8px 12px" }}>Benchmarks are versioned, sourced claims with population and period — never hard-coded numbers.</div>
      </div>

      {ops && ops.import_batches.length > 0 && (
        <>
          <h2>Recent imports</h2>
          <div className="card">
            <table>
              <thead><tr><th>Adapter</th><th style={{ width: 70 }}>Rows</th><th style={{ width: 110 }}>Status</th><th style={{ width: 130 }}>Through</th><th style={{ width: 90 }}></th></tr></thead>
              <tbody>
                {ops.import_batches.map((b) => (
                  <tr key={b.id}>
                    <td>{b.adapter}<div className="rowmeta">{b.source_label || ""}</div></td>
                    <td className="rowmeta">{b.row_count}</td>
                    <td><span className="badge" style={b.status === "rolled_back" ? { borderColor: "var(--risk)", color: "var(--risk)" } : {}}>{b.status}</span></td>
                    <td className="rowmeta">{fmtDate(b.current_through)}</td>
                    <td>{b.status === "committed" && <button className="btn small ghost" onClick={() => rollback(b.id)}>Roll back</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {importing && <ImportPanel onClose={() => setImporting(false)} onDone={() => { setImporting(false); setTick((t) => t + 1); }} />}
    </div>
  );
}

function ImportPanel({ onClose, onDone }) {
  const toast = useToast();
  const [defs, setDefs] = useState([]);
  const [csv, setCsv] = useState("definition_id,period_label,value\n");
  const [through, setThrough] = useState(new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = useState(null);
  useEffect(() => { api.metricDefinitions().then(setDefs).catch(() => {}); }, []);

  async function doPreview() {
    try { setPreview(await api.importPreview({ csv_text: csv, current_through: through })); }
    catch (e) { toast(e.message, "err"); }
  }
  async function doCommit() {
    try { const r = await api.importCommit({ csv_text: csv, current_through: through }); toast(`Committed ${r.committed} rows`); onDone(); }
    catch (e) { toast(typeof e.message === "string" ? e.message : "fix errors first", "err"); }
  }
  return (
    <SlideOver title="Import metric observations" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn" onClick={doPreview}>Preview</button><button className="btn primary" onClick={doCommit} disabled={!preview || preview.invalid > 0}>Commit</button></>}>
      <div className="rowmeta" style={{ marginBottom: 8 }}>Columns: <code>definition_id,period_label,value[,program_id,cohort_label,target,unit]</code></div>
      <div className="field"><label>Definition ids</label>
        <div className="rowmeta">{defs.map((d) => <div key={d.id}>{d.id} — {d.name}</div>)}</div>
      </div>
      <div className="field"><label>Current through</label><input type="date" value={through} onChange={(e) => setThrough(e.target.value)} /></div>
      <div className="field"><label>CSV</label><textarea value={csv} onChange={(e) => { setCsv(e.target.value); setPreview(null); }} rows={7} style={{ fontFamily: "var(--mono)" }} /></div>
      {preview && (
        <div className="card" style={{ padding: 10 }}>
          <div className="rowmeta">valid {preview.valid} · invalid {preview.invalid} · duplicates (will supersede) {preview.duplicates}</div>
          {preview.rows.filter((r) => r.errors.length).map((r) => (
            <div key={r.line} style={{ color: "var(--risk)", fontSize: 12 }}>line {r.line}: {r.errors.join(", ")}</div>
          ))}
        </div>
      )}
    </SlideOver>
  );
}

function fmtNum(v, unit) {
  if (v == null) return "—";
  if (unit === "ratio") return (v * 100).toFixed(0) + "%";
  return typeof v === "number" ? v.toLocaleString() : v;
}
