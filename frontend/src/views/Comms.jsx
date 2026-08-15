import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast, AgeChip, Empty } from "../ui";

// §4.2/§4.3 communications ingestion surface — mock email sync + recording ingest, with the
// priority flag and the association confidence shown (never guessed silently). Link-first: the
// one-line summary is the working record; "original" points at the source reference.
export default function Comms({ accountId, reloadKey, onSaved }) {
  const toast = useToast();
  const [comms, setComms] = useState([]);
  const [fixtures, setFixtures] = useState(null);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => { api.ingestFixtures().then(setFixtures).catch(() => {}); }, []);
  useEffect(() => {
    if (!accountId) return;
    api.accountComms(accountId).then((r) => setComms(r.comms)).catch((e) => toast(e.message, "err"));
  }, [accountId, reloadKey, tick]);

  const reload = () => { setTick((t) => t + 1); onSaved?.(); };

  async function sync() {
    setBusy(true);
    try { const r = await api.syncInbox(); toast(`Synced — ${r.result?.created ?? 0} new, ${r.result?.flagged ?? 0} flagged`); reload(); }
    catch (e) { toast(e.message, "err"); }
    setBusy(false);
  }
  async function ingest() {
    if (!pick) return;
    setBusy(true);
    try {
      const r = await api.ingestRecording({ reference: pick, keywords: [] });
      const res = r.result || {};
      toast(res.status === "ingested" ? `Ingested — ${res.proposals} proposals${res.needs_triage ? " (needs triage)" : ""}` : "Could not associate");
      reload();
    } catch (e) { toast(e.message, "err"); }
    setBusy(false);
  }
  async function responded(id) {
    try { await api.commResponded(id); toast("Marked handled"); reload(); } catch (e) { toast(e.message, "err"); }
  }

  return (
    <div>
      <div className="actions" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>Communications</h1>
        <div className="spacer" />
        <select value={pick} onChange={(e) => setPick(e.target.value)} style={sel}>
          <option value="">recording fixture…</option>
          {fixtures?.transcripts?.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button className="btn small" disabled={busy || !pick} onClick={ingest}>Ingest recording</button>
        <button className="btn small" disabled={busy} onClick={sync}>Sync inbox{fixtures ? ` (${fixtures.emails})` : ""}</button>
      </div>

      {comms.length === 0
        ? <Empty title="No communications yet">Sync the mock inbox or ingest a recording fixture to thread messages onto the ledger.</Empty>
        : (
          <div className="card" style={{ padding: 0 }}>
            <table>
              <tbody>
                {comms.map((m) => (
                  <tr key={m.id}>
                    <td className={"rail-cell " + (m.needs_response ? "band-risk" : "band-neutral")} style={{ padding: 0 }} />
                    <td style={{ padding: "8px 12px" }}>
                      <div>
                        <strong>{m.subject || "(no subject)"}</strong>
                        {m.needs_response ? <span className="badge" style={{ marginLeft: 8, borderColor: "var(--status-risk)", color: "var(--status-risk)" }}>● needs response</span> : null}
                        {m.confidence != null && m.confidence < 0.6 ? <span className="badge" style={{ marginLeft: 6, borderColor: "var(--status-warn)", color: "var(--status-warn)" }}>low confidence</span> : null}
                      </div>
                      <div className="rowmeta">{m.from_addr} · {m.summary}</div>
                      {m.flag_reason && <div className="rowmeta" style={{ color: "var(--status-warn)" }}>{m.flag_reason}</div>}
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "right", whiteSpace: "nowrap" }}>
                      {m.occurred_on && <AgeChip date={m.occurred_on} />}
                      {m.needs_response && <button className="btn small" style={{ marginLeft: 8 }} onClick={() => responded(m.id)}>Mark handled</button>}
                    </td>
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
