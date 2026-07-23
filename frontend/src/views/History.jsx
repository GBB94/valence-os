import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, useToast, fmtDate } from "../ui";

// Account history / interaction timeline (Module D). Chronological ledger,
// filterable by program or person, showing the records created from each interaction.
export default function History({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null); // account detail for filter options
  const [hist, setHist] = useState(null);
  const [programId, setProgramId] = useState("");
  const [personId, setPersonId] = useState("");

  useEffect(() => {
    if (!accountId) return;
    api.account(accountId).then(setDetail).catch((e) => toast(e.message, "err"));
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    api.history(accountId, { programId, personId }).then(setHist).catch((e) => toast(e.message, "err"));
  }, [accountId, programId, personId, reloadKey]);

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;

  const programs = detail?.programs ?? [];
  const people = detail?.people ?? [];

  return (
    <div>
      <div className="actions" style={{ marginBottom: 12 }}>
        <h1>History</h1>
        <select value={accountId || ""} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); setPersonId(""); }} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
        <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={sel}>
          <option value="">all programs</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select value={personId} onChange={(e) => setPersonId(e.target.value)} style={sel}>
          <option value="">all people</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      <div className="card">
        {!hist ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> :
          hist.interactions.length === 0 ? (
            <Empty title="No interactions">Nothing logged for this filter yet.</Empty>
          ) : (
            <table>
              <thead><tr><th style={{ width: 96 }}>Date</th><th style={{ width: 80 }}>Type</th><th>Interaction</th><th style={{ width: 220 }}>Created from it</th></tr></thead>
              <tbody>
                {hist.interactions.map((it) => (
                  <tr key={it.id}>
                    <td className="rowmeta">{fmtDate(it.occurred_on)}</td>
                    <td><span className="badge">{it.type}</span></td>
                    <td>
                      {it.summary || <span className="rowmeta">(no summary)</span>}
                      <div className="rowmeta">
                        {it.program_name || "account-level"}
                        {it.participants.length ? " · " + it.participants.map((p) => p.name).join(", ") : ""}
                      </div>
                    </td>
                    <td>
                      {it.created_records.length === 0 ? <span className="rowmeta">—</span> :
                        it.created_records.map((r) => (
                          <div key={r.id} className="rowmeta">
                            <span className="badge" style={{ marginRight: 4 }}>{r.type}</span>{r.label?.slice(0, 40)}
                          </div>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
      <div className="rowmeta" style={{ marginTop: 8 }}>Last-touch dates are derived from these interactions — never hand-edited.</div>
    </div>
  );
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
