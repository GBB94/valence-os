import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, useToast } from "../ui";
import { DocPanel } from "./Artifacts";

// Weekly team update export (Module L). Internal, freshness-stamped, summary-level
// only — internal-only capture (raw notes, stance) is excluded by construction in
// the generator, not by operator vigilance.
export default function TeamUpdate({ reloadKey }) {
  const toast = useToast();
  const [tu, setTu] = useState(null);
  const [loading, setLoading] = useState(false);
  const [docs, setDocs] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [open, setOpen] = useState(null);
  const [runAt, setRunAt] = useState("");
  const [tick, setTick] = useState(0);

  async function loadWorkflow() {
    try {
      const [saved, queued] = await Promise.all([api.documents(), api.jobs("queued")]);
      setDocs(saved.filter((d) => d.kind === "team_update"));
      setJobs((queued.jobs || []).filter((j) => j.kind === "weekly_team_update"));
    } catch (e) { toast(e.message, "err"); }
  }

  async function generate() {
    setLoading(true);
    try { setTu(await api.teamUpdate()); }
    catch (e) { toast(e.message, "err"); }
    finally { setLoading(false); }
  }
  useEffect(() => { generate(); loadWorkflow(); }, [reloadKey, tick]);

  async function copy() {
    try { await navigator.clipboard.writeText(tu.markdown); toast("Copied to clipboard"); }
    catch { toast("Copy failed — select and copy manually", "err"); }
  }

  async function schedule() {
    try {
      await api.scheduleWeeklyUpdate({ run_at: runAt ? new Date(runAt).toISOString() : null, recurring: true });
      toast(runAt ? "Weekly draft scheduled" : "Weekly draft queued");
      setRunAt(""); setTick((t) => t + 1);
    } catch (e) { toast(e.message, "err"); }
  }

  return (
    <div>
      <div className="actions" style={{ marginBottom: 4 }}>
        <h1>Weekly team update</h1>
        <div className="spacer" />
        <input type="datetime-local" value={runAt} onChange={(e) => setRunAt(e.target.value)}
               aria-label="First weekly draft time" style={{ width: 190 }} />
        <button className="btn" onClick={schedule}>Schedule weekly draft</button>
        <button className="btn" onClick={generate} disabled={loading}>{loading ? "Generating…" : "Regenerate"}</button>
        <button className="btn primary" onClick={copy} disabled={!tu}>Copy markdown</button>
      </div>

      {tu && (
        <div className="rowmeta" style={{ marginBottom: 12 }}>
          Generated {tu.stamp.generated_at} · data current through {tu.stamp.data_current_through} · covering {tu.stamp.window_since} → {tu.stamp.window_until}. Internal only; raw notes and stakeholder judgments excluded by construction.
        </div>
      )}

      {!tu ? <div className="subtle">Loading…</div> : tu.sections.length === 0 ? (
        <div className="placeholder">Nothing to report this week.</div>
      ) : (
        tu.sections.map((s) => (
          <div className="card" key={s.account_id}>
            <div className="card-h">
              <h3>{s.account_name}</h3>
              <div className="spacer" />
              <span className="badge">delivery: {s.delivery_status.replace("_", " ")}</span>
              <span className="badge">commercial: {s.commercial_status.replace("_", " ")}</span>
            </div>
            <div style={{ padding: 12 }}>
              <Block title="New interactions" items={s.new_interactions} render={(i) => `${i.occurred_on} · ${i.type} · ${i.program || "account-level"} — ${i.summary || "(no summary)"}`} />
              <Block title="New commitments" items={s.new_commitments} render={(c) => `${c.description} — ${c.responsible} → ${c.owner}, due ${c.due_date} (${c.program})`} />
              <Block title="Open blockers" items={s.open_blockers} render={(b) => `[${b.kind}] ${b.description} (${b.program})`} tone="risk" />
              <Block title="Overdue commitments" items={s.overdue_commitments} render={(o) => `${o.description} — was due ${o.due_date} (${o.program})`} tone="risk" />
              <Block title="At-risk milestones" items={s.at_risk_milestones} render={(m) => `${m.name} — target ${m.target_date || "unset"} (${m.program})`} tone="warn" />
              <Block title="Decisions" items={s.decisions} render={(d) => `${d.description} (${d.program})`} />
            </div>
          </div>
        ))
      )}

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-h"><h3>Review queue</h3><div className="spacer" />
          <span className="rowmeta">{jobs.length} scheduled · {docs.length} saved</span>
        </div>
        {docs.length === 0 ? <Empty title="No weekly drafts yet">Schedule one above; it will be saved for review and never auto-sent.</Empty> : (
          <table><thead><tr><th>Draft</th><th>Status</th><th>Generated</th><th></th></tr></thead>
            <tbody>{docs.map((d) => <tr key={d.id}>
              <th style={{ textAlign: "left", fontWeight: 500 }}>{d.title}</th>
              <td>{d.status}</td><td className="rowmeta">{d.generated_at}</td>
              <td><div className="actions">
                <button className="btn small" onClick={() => setOpen(d)}>Open</button>
                <a className="btn small ghost" href={api.documentPptxUrl(d.id)}>.pptx</a>
                <a className="btn small ghost" href={api.documentPdfUrl(d.id)}>.pdf</a>
              </div></td>
            </tr>)}</tbody>
          </table>
        )}
      </div>
      {open && <DocPanel doc={open} onClose={() => setOpen(null)}
                         onChanged={() => { setOpen(null); setTick((t) => t + 1); }} />}
    </div>
  );
}

function Block({ title, items, render, tone }) {
  if (!items?.length) return null;
  const color = tone === "risk" ? "var(--status-risk)" : tone === "warn" ? "var(--status-warn)" : "var(--ink-tertiary)";
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em", color }}>{title}</div>
      {items.map((it, i) => <div key={i} style={{ marginTop: 2 }}>{render(it)}</div>)}
    </div>
  );
}
