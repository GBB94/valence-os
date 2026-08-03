import { useState } from "react";
import { api } from "../api";
import { SlideOver, useToast } from "../ui";

// §1 guided onboarding — fired when an account is created (the first-impression surface).
// Step 1 seeds the launch plan/checklists/placeholders from a kickoff date; step 2 parses the
// sales handover into proposed records the operator accepts one by one (nothing writes otherwise).
export default function Onboarding({ account, onClose, onDone }) {
  const toast = useToast();
  const [step, setStep] = useState("plan");
  const [kickoff, setKickoff] = useState(new Date().toISOString().slice(0, 10));
  const [programName, setProgramName] = useState("Launch");
  const [europe, setEurope] = useState(false);
  const [seed, setSeed] = useState(null);
  const [programId, setProgramId] = useState(null);
  const [notes, setNotes] = useState("");
  const [proposals, setProposals] = useState(null);
  const [accepted, setAccepted] = useState({});
  const [busy, setBusy] = useState(false);

  async function seedPlan() {
    setBusy(true);
    try {
      const r = await api.onboard(account.id, {
        kickoff_date: kickoff, program_name: programName, europe_in_scope: europe,
      });
      setSeed(r.seeded); setProgramId(r.program_id); setStep("intake");
      toast("Launch plan seeded");
    } catch (e) { toast(e.message, "err"); }
    setBusy(false);
  }
  async function parse() {
    setBusy(true);
    try { setProposals((await api.intakeParse(notes)).proposals); }
    catch (e) { toast(e.message, "err"); }
    setBusy(false);
  }
  async function accept(p, i) {
    try {
      await api.intakeAccept({ account_id: account.id, program_id: programId, proposal: p });
      setAccepted((a) => ({ ...a, [i]: true }));
      toast(`Accepted ${p.type.replace(/_/g, " ")}`);
    } catch (e) { toast(e.message, "err"); }
  }

  const footer = step === "plan"
    ? <button className="btn primary" disabled={busy} onClick={seedPlan}>Seed launch plan →</button>
    : <button className="btn primary" onClick={() => { onDone?.(); onClose(); }}>Done</button>;

  return (
    <SlideOver title={`Onboard — ${account.name}`} onClose={onClose} footer={footer}>
      {step === "plan" ? (
        <div className="stack">
          <p className="rowmeta">Seed the standard launch: milestones, back-scheduled kickoff prep,
            time-phased checklists, and the org-chart placeholders for the people you don't know yet.
            Every date is relative to kickoff and editable afterward.</p>
          <label className="field"><span>Kickoff date</span>
            <input type="date" value={kickoff} onChange={(e) => setKickoff(e.target.value)} /></label>
          <label className="field"><span>Program name</span>
            <input value={programName} onChange={(e) => setProgramName(e.target.value)} /></label>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={europe} onChange={(e) => setEurope(e.target.checked)} />
            <span>Europe in scope (seeds a works-council placeholder + consultation checklist)</span>
          </label>
        </div>
      ) : (
        <div className="stack">
          {seed && (
            <div className="card" style={{ padding: 12 }}>
              <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>Seeded</div>
              <div style={{ fontSize: 13 }}>{seed.milestones} milestones · {seed.prep_tasks} prep tasks · {seed.checklist_items} checklist items · {seed.placeholders} org placeholders</div>
            </div>
          )}
          <p className="rowmeta">Paste the sales handover — deal context, named contacts, dates, incumbent.
            We propose records; you accept each. Nothing writes until you do.</p>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5}
            placeholder="e.g. Met with Priya Anand (VP of Learning), the champion. Currently using Ascend. Go-live 2026-10-01. What is the works-council timeline?"
            style={{ width: "100%", borderRadius: 6, border: "1px solid var(--line-strong)", padding: 8, background: "var(--bg-surface)", fontfamily: "inherit" }} />
          <button className="btn" disabled={busy || !notes.trim()} onClick={parse}>Parse handover</button>

          {proposals && (proposals.length === 0
            ? <div className="rowmeta">No proposals found in that text.</div>
            : proposals.map((p, i) => (
              <div key={i} className="card" style={{ padding: 12, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <div>
                  <span className="badge" style={{ marginRight: 6 }}>{p.type.replace(/_/g, " ")}</span>
                  <span style={{ fontSize: 13 }}>{p.name || p.label || p.note || p.question}{p.title ? ` — ${p.title}` : ""}{p.date ? ` (${p.date})` : ""}</span>
                  {p.source_span && <div className="rowmeta">“{p.source_span}”</div>}
                </div>
                {accepted[i]
                  ? <span style={{ color: "var(--status-ok)", whiteSpace: "nowrap" }}>✓ accepted</span>
                  : <button className="btn small" onClick={() => accept(p, i)}>Accept proposal</button>}
              </div>
            )))}
        </div>
      )}
    </SlideOver>
  );
}
