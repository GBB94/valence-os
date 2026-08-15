import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast, DueChip, Empty, Loading } from "../ui";

// §2 launch checklists with falling-behind escalation, and §1e first-call questions.
// Escalation is derived from due_date: past due -> warn, more than a week past -> risk. State
// pairs color with a shape/label (never color alone), matching the design guide.
const SECTIONS = [
  ["first_call", "First call"],
  ["first_two_weeks", "First two weeks"],
  ["first_30_days", "First 30 days"],
  ["first_90_days", "First 90 days"],
];

function today() { return new Date().toISOString().slice(0, 10); }
function overdueDays(due) {
  if (!due) return 0;
  const d = Math.floor((new Date(today()) - new Date(due)) / 86400000);
  return d > 0 ? d : 0;
}

export default function Checklists({ accountId, programId, reloadKey, onSaved }) {
  const toast = useToast();
  const [state, setState] = useState(null);
  const [tick, setTick] = useState(0);
  const [answering, setAnswering] = useState(null); // {id, fills_field}
  const [answer, setAnswer] = useState("");

  useEffect(() => {
    if (!accountId) return;
    api.onboarding(accountId).then(setState).catch((e) => toast(e.message, "err"));
  }, [accountId, reloadKey, tick]);

  if (!state) return <Loading what="checklist" />;
  if (!state.onboarded)
    return <Empty title="Not onboarded yet">Run the guided onboarding to seed the launch plan, checklists, and org placeholders.</Empty>;

  const items = state.checklist || {};
  const prog = state.checklist_progress || { done: 0, total: 0 };
  const behind = Object.values(items).flat().filter((i) => i.status === "open" && overdueDays(i.due_date) > 7).length;

  async function mark(item, status) {
    try {
      await api.patchChecklistItem(item.id, { status });
      toast(status === "done" ? "Done" : "Reopened");
      setTick((t) => t + 1); onSaved?.();
    } catch (e) { toast(e.message, "err"); }
  }
  async function saveAnswer(item) {
    try {
      const r = await api.patchChecklistItem(item.id, { status: "done", answer_note: answer, fill_value: answer });
      toast(r.filled_field ? `Answered — filled ${r.filled_field}` : "Answered");
      setAnswering(null); setAnswer(""); setTick((t) => t + 1); onSaved?.();
    } catch (e) { toast(e.message, "err"); }
  }

  return (
    <div>
      <div className="actions" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>Launch checklist</h1>
        <div className="spacer" />
        <span className="rowmeta">{prog.done}/{prog.total} done</span>
        {behind > 0 && (
          <span className="badge" style={{ borderColor: "var(--status-risk)", color: "var(--status-risk)", marginLeft: 8 }}>
            ● {behind} more than a week behind
          </span>
        )}
      </div>

      {SECTIONS.map(([key, label]) => {
        const list = items[key] || [];
        if (!list.length) return null;
        return (
          <div key={key} className="card" style={{ padding: 0, marginBottom: 12 }}>
            <div className="band-head" style={{ padding: "8px 12px" }}>{label}</div>
            <table>
              <tbody>
                {list.map((i) => {
                  const od = i.status === "open" ? overdueDays(i.due_date) : 0;
                  const band = od > 7 ? "risk" : od > 0 ? "warn" : null;
                  const done = i.status === "done";
                  return (
                    <tr key={i.id}>
                      <td className={"rail-cell " + (band ? "band-" + band : "band-neutral")} style={{ padding: 0 }} />
                      <td style={{ padding: "8px 12px", width: 26 }}>
                        <input type="checkbox" checked={done} onChange={() => mark(i, done ? "open" : "done")} aria-label={`Mark "${i.label}" done`} />
                      </td>
                      <td style={{ padding: "8px 12px" }}>
                        <div style={{ textDecoration: done ? "line-through" : "none", color: done ? "var(--ink-tertiary)" : "var(--ink-primary)" }}>
                          {i.label}
                          {i.fills_field && !done && (
                            <button className="btn small" style={{ marginLeft: 8 }}
                              onClick={() => { setAnswering(i); setAnswer(i.answer_note || ""); }}>Answer →</button>
                          )}
                        </div>
                        {i.detail && <div className="rowmeta">{i.detail}</div>}
                        {i.answer_note && <div className="rowmeta" style={{ color: "var(--ink-secondary)" }}>↳ {i.answer_note}</div>}
                        {answering?.id === i.id && (
                          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                            <input autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)}
                              placeholder={i.fills_field ? `Fills ${i.fills_field}` : "Answer"}
                              style={{ flex: 1, height: 28, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" }} />
                            <button className="btn small" onClick={() => saveAnswer(i)}>Save answer</button>
                            <button className="btn small" onClick={() => setAnswering(null)}>Cancel</button>
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "8px 12px", textAlign: "right", whiteSpace: "nowrap" }}>
                        {i.due_date && !done && (od > 0
                          ? <span style={{ color: band === "risk" ? "var(--status-risk)" : "var(--status-warn)" }}>{od}d overdue</span>
                          : <DueChip date={i.due_date} />)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
