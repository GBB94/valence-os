import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, Loading, useToast, fmtDate } from "../ui";

// Mutual action plan (Section 5N) — client-facing joint plan assembled from items the
// operator has promoted (client_visible). Internal items never appear, by construction.
export default function MutualActionPlan({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [map, setMap] = useState(null);

  async function load() {
    if (!accountId) return;
    try { setMap(await api.accountMap(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey]);

  async function copy() {
    try { await navigator.clipboard.writeText(map.markdown); toast("Copied to clipboard"); }
    catch { toast("Copy failed", "err"); }
  }

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>Mutual action plan</h1>
        <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
        <button className="btn" onClick={load}>Refresh</button>
        <button className="btn primary" onClick={copy} disabled={!map || !map.items.length}>Copy markdown</button>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>
        Client-facing, jointly owned. Only items promoted to the plan (a ★ on the Execution board) appear here — internal work never leaks in.
        {map && <> · current through {map.stamp.data_current_through}</>}
      </div>

      {!map ? <Loading what="mutual action plan" /> : map.items.length === 0 ? (
        <div className="placeholder">Nothing shared to this plan yet. Star a commitment, task, or milestone on the Execution board to add it.</div>
      ) : (
        <div className="card">
          <table>
            <thead><tr><th scope="col">What</th><th scope="col">Owner</th><th scope="col" className="num" style={{ width: 110 }}>Due</th><th scope="col" style={{ width: 110 }}>Status</th><th scope="col" style={{ width: 160 }}>Program</th></tr></thead>
            <tbody>
              {map.items.map((it, i) => (
                <tr key={i}>
                  <td><span className="badge" style={{ marginRight: 6 }}>{it.type}</span>{it.what}</td>
                  <td className="rowmeta">{it.owner || "—"}</td>
                  <td className="rowmeta num">{fmtDate(it.due)}</td>
                  <td className="rowmeta">{it.status}</td>
                  <td className="rowmeta">{it.program || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
