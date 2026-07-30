import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast, fmtDate } from "../ui";

const TYPE_LABEL = { confirmed_fact: "fact", internal_interpretation: "interpretation", open_hypothesis: "hypothesis", recommended_action: "recommendation" };
const TYPE_COLOR = { confirmed_fact: "var(--status-ok)", internal_interpretation: "var(--status-warn)", open_hypothesis: "var(--ink-tertiary)", recommended_action: "var(--accent)" };

export default function QBR({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [q, setQ] = useState(null);

  async function load() {
    if (!accountId) return;
    try { setQ(await api.qbr(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey]);

  if (!accounts.length) return <div className="subtle">Create an account first.</div>;

  const Type = ({ t }) => <span className="badge" style={{ borderColor: TYPE_COLOR[t], color: TYPE_COLOR[t], marginLeft: 6 }}>{TYPE_LABEL[t]}</span>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>QBR generator</h1>
        <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
        <button className="btn" onClick={load}>Regenerate</button>
      </div>

      {!q ? <div className="subtle">Loading…</div> : (
        <>
          <div className="rowmeta" style={{ marginBottom: 4 }}>
            Generated {q.stamp.generated_at} · data current through {q.stamp.data_current_through}.
            {q.stamp.missing_or_stale_sources.length > 0 && <span style={{ color: "var(--status-warn)" }}> ⚠ stale/missing: {q.stamp.missing_or_stale_sources.join(", ")}</span>}
          </div>
          <div className="rowmeta" style={{ marginBottom: 14, color: "var(--ink-tertiary)" }}>{q.excluded_note}</div>

          <div className="card"><div className="card-h"><h3>Metrics vs targets</h3></div>
            <table><thead><tr><th>Metric</th><th style={{ width: 120 }}>Value</th><th style={{ width: 100 }}>Target</th><th>Population · through</th></tr></thead>
              <tbody>
                {q.metrics.map((m, i) => (
                  <tr key={i}><td>{m.name} <Type t={m.type} /></td>
                    <td>{m.value === "unknown" ? <span style={{ color: "var(--ink-tertiary)" }}>unknown</span> : fmtNum(m.value)}</td>
                    <td className="rowmeta">{fmtNum(m.target)}</td>
                    <td className="rowmeta">{m.population || "—"}{m.current_through ? ` · ${fmtDate(m.current_through)}` : ""}</td></tr>
                ))}
                {q.metrics.length === 0 && <tr><td colSpan={4} className="rowmeta">No metric definitions.</td></tr>}
              </tbody></table>
          </div>

          <div className="card"><div className="card-h"><h3>Benchmarks</h3></div>
            {q.benchmarks.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None.</div> : (
              <table><tbody>{q.benchmarks.map((b, i) => (
                <tr key={i}><td>{b.name} <Type t={b.type} /><div className="rowmeta">{b.population} · {b.period} · {b.source} v{b.version}</div></td><td style={{ width: 90 }}>{fmtNum(b.value)}</td></tr>
              ))}</tbody></table>
            )}
          </div>

          <div className="card"><div className="card-h"><h3>Approved value stories</h3><div className="spacer" /><span className="rowmeta">promoted, non-negative only</span></div>
            {q.value_stories.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No promoted stories.</div> : (
              <table><tbody>{q.value_stories.map((v, i) => (
                <tr key={i}><td>{v.outcome} <Type t={v.type} /><div className="rowmeta">{v.evidence_tier.replace(/_/g, " ")}</div></td></tr>
              ))}</tbody></table>
            )}
          </div>

          <div className="card"><div className="card-h"><h3>Open commitments</h3></div>
            {q.open_commitments.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None open.</div> : (
              <table><tbody>{q.open_commitments.map((c, i) => (
                <tr key={i}><td>{c.description}</td><td className="rowmeta" style={{ width: 110 }}>due {fmtDate(c.due_date)}</td></tr>
              ))}</tbody></table>
            )}
            <div className="rowmeta" style={{ padding: "8px 12px" }}>Risk posture (internal): {q.risk_posture.open_risks} open risk(s) — high-level only; internal detail excluded.</div>
          </div>
        </>
      )}
    </div>
  );
}

function fmtNum(v) {
  if (v == null || v === "unknown") return v === "unknown" ? "unknown" : "—";
  return typeof v === "number" ? (v <= 1 && v > 0 ? (v * 100).toFixed(0) + "%" : v.toLocaleString()) : v;
}
const sel = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
