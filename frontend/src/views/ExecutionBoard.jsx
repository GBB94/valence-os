import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast, fmtDate } from "../ui";

export default function ExecutionBoard({ accounts, accountId, setAccountId, reloadKey, onChanged }) {
  const toast = useToast();
  const [board, setBoard] = useState(null);
  const [people, setPeople] = useState([]);
  const [closing, setClosing] = useState(null); // {kind, item}

  async function load() {
    if (!accountId) return;
    try {
      const [b, acct] = await Promise.all([api.accountExecution(accountId), api.account(accountId)]);
      setBoard(b);
      setPeople(acct.people);
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey]);

  const afterClose = () => { setClosing(null); load(); onChanged?.(); };

  async function togglePlan(kind, item) {
    try {
      await api.mapPromote({ object_type: kind, object_id: item.id, client_visible: !item.client_visible });
      toast(item.client_visible ? "Removed from plan" : "Added to mutual action plan");
      load(); onChanged?.();
    } catch (e) { toast(e.message, "err"); }
  }
  const PlanStar = ({ kind, item }) => (
    <button className="btn small ghost" title={item.client_visible ? "On the mutual action plan — click to remove" : "Add to mutual action plan"}
      onClick={() => togglePlan(kind, item)} style={{ color: item.client_visible ? "var(--accent)" : "var(--text-3)" }}>
      {item.client_visible ? "★" : "☆"}
    </button>
  );

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Execution</h1>
        <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)} style={{ height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px" }}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
        <span className="rowmeta">Open items across this account’s programs</span>
      </div>

      {!board ? <div className="subtle">Loading…</div> : (
        <>
          <Section title="Commitments" rows={board.commitments} empty="No commitments.">
            {(c) => (
              <tr key={c.id} className={c.status === "closed" ? "" : ""}>
                <td>{c.description}<div className="rowmeta">{c.program_name} · {c.responsible_party_name || "—"} → {c.internal_owner_name || "—"}</div></td>
                <td className="rowmeta">{fmtDate(c.due_date)}</td>
                <td>{statusCell(c.status, c.overdue ? "overdue" : null)}</td>
                <td><div className="actions"><PlanStar kind="commitment" item={c} />{c.status === "open" && <button className="btn small" onClick={() => setClosing({ kind: "commitment", item: c })}>Close</button>}</div></td>
              </tr>
            )}
          </Section>

          <Section title="Risks & issues" rows={[...board.risks, ...board.issues]} empty="No risks or issues.">
            {(r) => {
              const isRisk = "severity" in r;
              return (
                <tr key={r.id}>
                  <td>{r.description}
                    <div className="rowmeta">{r.program_name} · {isRisk ? `risk · ${r.severity}` : "issue"}{r.is_blocker ? " · blocker" : ""}</div>
                  </td>
                  <td className="rowmeta">{isRisk ? (r.mitigation ? "mitigating" : "—") : "—"}</td>
                  <td>{statusCell(r.status, r.is_blocker && r.status === "open" ? "blocker" : null)}</td>
                  <td>
                    {r.status === "open" && (
                      <button className="btn small" onClick={() => setClosing({ kind: isRisk ? "risk" : "issue", item: r })}>
                        {isRisk ? "Close" : "Resolve"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            }}
          </Section>

          <Section title="Milestones" rows={board.milestones} empty="No milestones.">
            {(m) => (
              <tr key={m.id}>
                <td>{m.name}<div className="rowmeta">{m.program_name}{m.success_criteria ? ` · ${m.success_criteria}` : ""}</div></td>
                <td className="rowmeta">{fmtDate(m.target_date)}</td>
                <td>{statusCell(m.status === "complete" ? "complete" : "upcoming", m.derived_at_risk ? "at risk" : null)}</td>
                <td><div className="actions"><PlanStar kind="milestone" item={m} />{m.status === "upcoming" && <button className="btn small" onClick={() => setClosing({ kind: "milestone", item: m })}>Complete</button>}</div></td>
              </tr>
            )}
          </Section>

          <Section title="Tasks" rows={board.tasks} empty="No tasks.">
            {(t) => (
              <tr key={t.id}>
                <td>{t.description}<div className="rowmeta">{t.program_name}{t.internal_owner_name ? ` · ${t.internal_owner_name}` : ""}</div></td>
                <td className="rowmeta">{fmtDate(t.due_date)}</td>
                <td>{statusCell(t.status, t.overdue ? "overdue" : null)}</td>
                <td><div className="actions"><PlanStar kind="task" item={t} />{t.status === "open" && <button className="btn small" onClick={() => setClosing({ kind: "task", item: t })}>Done</button>}</div></td>
              </tr>
            )}
          </Section>

          {board.decisions.length > 0 && (
            <Section title="Decisions" rows={board.decisions} empty="">
              {(d) => (
                <tr key={d.id}>
                  <td>{d.description}<div className="rowmeta">{d.program_name}{d.rationale ? ` · ${d.rationale}` : ""}</div></td>
                  <td className="rowmeta">{fmtDate(d.decided_on)}</td>
                  <td>{statusCell(d.status)}</td>
                  <td></td>
                </tr>
              )}
            </Section>
          )}
        </>
      )}

      {closing && (
        <CloseDrawer info={closing} people={people} onClose={() => setClosing(null)} onDone={afterClose} />
      )}
    </div>
  );
}

function Section({ title, rows, empty, children }) {
  return (
    <div className="card">
      <div className="card-h"><h3>{title}</h3><div className="spacer" /><span className="rowmeta">{rows.length}</span></div>
      {rows.length === 0 ? <div className="rowmeta" style={{ padding: "10px 12px" }}>{empty}</div> : (
        <table>
          <thead><tr><th>Item</th><th style={{ width: 100 }}>Due / info</th><th style={{ width: 120 }}>Status</th><th style={{ width: 90 }}></th></tr></thead>
          <tbody>{rows.map(children)}</tbody>
        </table>
      )}
    </div>
  );
}

function statusCell(status, flag) {
  const cls = flag === "overdue" || flag === "blocker" ? "risk" : flag === "at risk" ? "warn" : status === "closed" || status === "complete" || status === "resolved" ? "ok" : "";
  return (
    <span>
      <span className={"dot " + cls} /> {status}
      {flag && <span className={"badge"} style={{ marginLeft: 6, borderColor: cls === "risk" ? "var(--risk)" : "var(--warn)", color: cls === "risk" ? "var(--risk)" : "var(--warn)" }}>{flag}</span>}
    </span>
  );
}

// One drawer, adapts its form to the closure rule of each object type.
function CloseDrawer({ info, people, onClose, onDone }) {
  const toast = useToast();
  const { kind, item } = info;
  const [note, setNote] = useState("");
  const [ack, setAck] = useState("");        // commitment: acknowledged_by
  const [reason, setReason] = useState("no_longer_relevant"); // risk
  const [rtype, setRtype] = useState("condition_removed");    // issue
  const [tstatus, setTstatus] = useState("done");             // task
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    try {
      if (kind === "commitment") await api.closeCommitment(item.id, { acknowledged_by_id: ack || null, close_note: note || null });
      else if (kind === "task") await api.closeTask(item.id, { status: tstatus, close_note: note || null });
      else if (kind === "risk") await api.closeRisk(item.id, { close_reason: reason, close_note: note || null });
      else if (kind === "issue") await api.resolveIssue(item.id, { resolution_type: rtype, resolution_note: note || null });
      else if (kind === "milestone") await api.completeMilestone(item.id, { completion_note: note || null });
      toast("Updated");
      onDone();
    } catch (e) { toast(e.message, "err"); }
    finally { setSaving(false); }
  }

  const titles = { commitment: "Close commitment", task: "Complete task", risk: "Close risk", issue: "Resolve issue", milestone: "Complete milestone" };
  return (
    <SlideOver title={titles[kind]} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={submit} disabled={saving}>Confirm</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{item.description || item.name}</div>

      {kind === "commitment" && (
        <>
          <div className="field"><label>Acknowledged by (receiving party)</label>
            <select value={ack} onChange={(e) => setAck(e.target.value)}>
              <option value="">— optional —</option>
              {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <div className="hint">A commitment closes when the receiving party acknowledges completion.</div>
          </div>
        </>
      )}
      {kind === "task" && (
        <div className="field"><label>Outcome</label>
          <select value={tstatus} onChange={(e) => setTstatus(e.target.value)}>
            <option value="done">done (deliverable exists)</option>
            <option value="cancelled">cancelled (no longer needed)</option>
          </select>
        </div>
      )}
      {kind === "risk" && (
        <div className="field"><label>Close reason <span className="req">*</span></label>
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="no_longer_relevant">no longer relevant</option>
            <option value="no_longer_possible">no longer possible</option>
          </select>
          <div className="hint">A risk closes only when no longer possible or relevant — not when mitigation begins.</div>
        </div>
      )}
      {kind === "issue" && (
        <div className="field"><label>Resolution <span className="req">*</span></label>
          <select value={rtype} onChange={(e) => setRtype(e.target.value)}>
            <option value="condition_removed">condition removed</option>
            <option value="workaround_operating">workaround operating</option>
          </select>
        </div>
      )}
      <div className="field"><label>Note</label>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Short closing note (recorded with date + closer)" />
      </div>
    </SlideOver>
  );
}
