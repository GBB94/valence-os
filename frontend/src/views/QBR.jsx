import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, useToast, fmtDate } from "../ui";

const TYPE_LABEL = { confirmed_fact: "fact", internal_interpretation: "interpretation", open_hypothesis: "hypothesis", recommended_action: "recommendation" };
// Evidence type is categorical (fact vs interpretation vs hypothesis vs action), not health —
// so it uses the data family, never status hues. Badges also carry a text label (§6).
const TYPE_COLOR = { confirmed_fact: "var(--data-1)", internal_interpretation: "var(--data-3)", open_hypothesis: "var(--ink-tertiary)", recommended_action: "var(--data-2)" };

export default function QBR({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [q, setQ] = useState(null);

  async function load() {
    if (!accountId) return;
    try { setQ(await api.qbr(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey]);

  if (!accounts.length) return <div className="subtle">Create an account first.</div>;

  // Category rides on the label + a colored left border; text stays ink so it always clears contrast.
  const Type = ({ t }) => <span className="badge" style={{ borderLeft: `3px solid ${TYPE_COLOR[t]}`, marginLeft: 6 }}>{TYPE_LABEL[t]}</span>;

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

      {!q ? <Loading what="QBR" /> : (
        <>
          <div className="rowmeta" style={{ marginBottom: 4 }}>
            Generated {q.stamp.generated_at} · data current through {q.stamp.data_current_through}.
            {q.stamp.missing_or_stale_sources.length > 0 && <span style={{ color: "var(--status-warn)" }}> ⚠ stale/missing: {q.stamp.missing_or_stale_sources.join(", ")}</span>}
          </div>
          <div className="rowmeta" style={{ marginBottom: 16, color: "var(--ink-tertiary)" }}>{q.excluded_note}</div>

          <div className="card"><div className="card-h"><h3>Metrics vs targets</h3></div>
            <table><thead><tr><th scope="col">Metric</th><th scope="col" className="num" style={{ width: 120 }}>Value</th><th scope="col" className="num" style={{ width: 100 }}>Target</th><th scope="col">Population · through</th></tr></thead>
              <tbody>
                {q.metrics.map((m, i) => (
                  <tr key={i}><td>{m.name} <Type t={m.type} /></td>
                    <td className="num">{m.value === "unknown" ? <span style={{ color: "var(--ink-tertiary)" }}>unknown</span> : fmtNum(m.value)}</td>
                    <td className="rowmeta num">{fmtNum(m.target)}</td>
                    <td className="rowmeta">{m.population || "—"}{m.current_through ? ` · ${fmtDate(m.current_through)}` : ""}
                      {m.source?.label ? <div>source: {m.source.label}</div> : null}</td></tr>
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
                <tr key={i}><td>{v.outcome} <Type t={v.type} /><div className="rowmeta">{v.evidence_tier.replace(/_/g, " ")} · {v.source?.label || "source unavailable"}</div></td></tr>
              ))}</tbody></table>
            )}
          </div>

          <div className="card"><div className="card-h"><h3>Open commitments</h3></div>
            {q.open_commitments.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>None open.</div> : (
              <table><tbody>{q.open_commitments.map((c, i) => (
                <tr key={i}><td>{c.description}<div className="rowmeta">{c.source?.label || "source unavailable"}</div></td><td className="rowmeta" style={{ width: 110 }}>due {fmtDate(c.due_date)}</td></tr>
              ))}</tbody></table>
            )}
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
