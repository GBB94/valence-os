import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { api } from "../api";
import { useToast } from "../ui";

// Transcript / email extraction (v4 + §4.4). Paste text, propose structured updates, review each
// per item on one keyboard-driven surface: j/k move, a accept, r reject, e edit. Nothing writes
// until you accept; every proposal shows its source span. Document content is data, not commands.
const LABEL = {
  create_commitment: "commitment", create_risk: "risk", create_decision: "decision",
  create_task: "task", create_issue: "issue", fill_placeholder: "placeholder-fill",
  log_pull_signal: "pull signal", create_deployment_moment: "deployment moment",
  create_value_story: "value story",
};
const MOMENT_TYPES = ["talent_calendar", "manager_workflow", "business_event", "proactive_coaching", "comms_campaign"];
// Targets that write against the account (a program isn't required to apply them).
const ACCOUNT_SCOPED = new Set(["fill_placeholder", "log_pull_signal", "create_value_story"]);

export default function Extraction({ accounts, accountId, setAccountId, reloadKey, onApplied }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [programId, setProgramId] = useState("");
  const [transcript, setTranscript] = useState("");
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState(null);
  const [mode, setMode] = useState("auto");
  const [backend, setBackend] = useState("");
  const [pasteJson, setPasteJson] = useState("");
  const [sel, setSel] = useState(0);
  const rowRefs = useRef({});

  useEffect(() => { if (accountId) api.account(accountId).then(setDetail).catch(() => {}); }, [accountId]);
  useEffect(() => { api.extractionConfig().then(setConfig).catch(() => {}); }, []);
  const programs = detail?.programs ?? [];
  const people = detail?.people ?? [];

  async function doRun() {
    if (!transcript.trim()) { toast("Paste a transcript first", "err"); return; }
    setBusy(true);
    try { setRun(await api.runExtraction({ account_id: accountId, program_id: programId || null, transcript, backend: backend || null })); setSel(0); }
    catch (e) { toast(e.message, "err"); } finally { setBusy(false); }
  }
  async function doManual() {
    if (!pasteJson.trim()) { toast("Paste the model's JSON output first", "err"); return; }
    setBusy(true);
    try {
      const r = await api.manualExtraction({ account_id: accountId, program_id: programId || null, proposals_json: pasteJson });
      setRun(r); setSel(0); toast(`${r.proposals.length} proposal(s) ingested`);
    } catch (e) { toast(e.message, "err"); } finally { setBusy(false); }
  }
  async function copyPrompt() {
    try { await navigator.clipboard.writeText(`${config.manual_prompt}\n\n--- TRANSCRIPT ---\n${transcript}`); toast("Prompt + transcript copied"); }
    catch { toast("Copy failed", "err"); }
  }

  // Keyboard-driven review: j/k (or arrows) move, a accept, r reject, e edit — the selected item.
  useEffect(() => {
    if (!run) return;
    const onKey = (ev) => {
      const t = ev.target.tagName;
      if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
      const n = run.proposals.length;
      if (ev.key === "j" || ev.key === "ArrowDown") { setSel((s) => Math.min(n - 1, s + 1)); ev.preventDefault(); }
      else if (ev.key === "k" || ev.key === "ArrowUp") { setSel((s) => Math.max(0, s - 1)); ev.preventDefault(); }
      else if (ev.key === "a") { rowRefs.current[run.proposals[sel]?.id]?.accept(); }
      else if (ev.key === "r") { rowRefs.current[run.proposals[sel]?.id]?.reject(); }
      else if (ev.key === "e") { rowRefs.current[run.proposals[sel]?.id]?.toggleEdit(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [run, sel]);

  if (!accounts.length) return <div className="subtle">Create an account first.</div>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 6 }}>
        <h1>Extraction review</h1>
        <select value={accountId || ""} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); setRun(null); }} style={selS}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={selS}>
          <option value="">— program (needed for execution + moments) —</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div className="actions" style={{ marginBottom: 8 }}>
        <button className={"btn small" + (mode === "auto" ? " primary" : "")} onClick={() => setMode("auto")}>Auto</button>
        <button className={"btn small" + (mode === "manual" ? " primary" : "")} onClick={() => setMode("manual")}>Manual (local LLM)</button>
        {mode === "auto" && (
          <>
            <span className="rowmeta">backend:</span>
            <select value={backend} onChange={(e) => setBackend(e.target.value)} style={{ height: 26, borderRadius: 6, border: "1px solid var(--line-hairline)", padding: "0 6px" }}>
              <option value="">default{config ? ` (${config.backend})` : ""}</option>
              <option value="mock">mock (offline)</option>
              <option value="api">api ({config?.api_model || "Claude API"})</option>
            </select>
          </>
        )}
      </div>
      <div className="rowmeta" style={{ marginBottom: 12 }}>
        {mode === "auto"
          ? "Auto runs the configured extractor — the offline mock, or the Claude API (no browsing/tools, strict JSON schema)."
          : "Manual: run your own local LLM, paste its JSON here. The app makes no external call. Either way, output is validated against the same strict schema and every proposal needs your acceptance."}
      </div>

      <div className="card" style={{ padding: 12, marginBottom: 12 }}>
        <textarea value={transcript} onChange={(e) => setTranscript(e.target.value)} rows={6} placeholder="Paste the call transcript or email…" style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: 12, border: "1px solid var(--line-strong)", borderRadius: 6, padding: 8 }} />
        {mode === "auto" ? (
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn primary" onClick={doRun} disabled={busy}>{busy ? "Extracting…" : "Extract proposals"}</button>
            {run && <span className="rowmeta">model {run.model_version} · prompt {run.prompt_version} · {run.proposals.length} proposals</span>}
          </div>
        ) : (
          <div style={{ marginTop: 8 }}>
            <button className="btn small" onClick={copyPrompt} disabled={!config}>Copy prompt + transcript</button>
            <div className="rowmeta" style={{ margin: "8px 0 4px" }}>Paste the model's JSON output:</div>
            <textarea value={pasteJson} onChange={(e) => setPasteJson(e.target.value)} rows={5} placeholder='{"proposals":[…]}' style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: 12, border: "1px solid var(--line-strong)", borderRadius: 6, padding: 8 }} />
            <div className="actions" style={{ marginTop: 8 }}>
              <button className="btn primary" onClick={doManual} disabled={busy}>{busy ? "Ingesting…" : "Validate & ingest"}</button>
              {run && <span className="rowmeta">{run.model_version} · {run.proposals.length} proposals</span>}
            </div>
          </div>
        )}
      </div>

      {run && (
        <div className="card">
          <div className="card-h"><h3>Proposals</h3><div className="spacer" /><span className="rowmeta">j/k move · a accept · r reject · e edit</span></div>
          {run.proposals.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No structured updates found.</div> :
            run.proposals.map((p, i) => (
              <ProposalRow key={p.id} ref={(el) => (rowRefs.current[p.id] = el)} p={p} programId={programId} people={people}
                selected={i === sel} onFocusRow={() => setSel(i)}
                onDone={(r) => { setRun(patchRun(run, p.id, r)); onApplied?.(); }} />
            ))}
        </div>
      )}
    </div>
  );
}

function patchRun(run, id, result) {
  const status = result.status || (result.created_type ? "accepted" : "proposed");
  return { ...run, proposals: run.proposals.map((x) => (x.id === id ? { ...x, status } : x)) };
}

const ProposalRow = forwardRef(function ProposalRow({ p, programId, people, selected, onFocusRow, onDone }, ref) {
  const toast = useToast();
  const [expand, setExpand] = useState(false);
  const [resp, setResp] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const [name, setName] = useState(p.payload.name || "");
  const [title, setTitle] = useState(p.payload.title || "");
  const [momentType, setMomentType] = useState(p.payload.moment_type || "business_event");
  const valence = people.filter((x) => x.affiliation === "valence");
  const mt = p.mutation_type;
  const done = p.status !== "proposed";
  const needsProgram = !ACCOUNT_SCOPED.has(mt);

  async function accept() {
    if (done) return;
    if (needsProgram && !programId) { toast("Pick a program above to apply this", "err"); return; }
    const overrides = {};
    if (mt === "create_commitment") {
      if (!resp || !owner || !due) { setExpand(true); toast("Commitment needs responsible party, owner, and due date", "err"); return; }
      Object.assign(overrides, { responsible_party_id: resp, internal_owner_id: owner, due_date: due });
    } else if (mt === "fill_placeholder") {
      if (!name.trim()) { setExpand(true); toast("A placeholder-fill needs a name", "err"); return; }
      Object.assign(overrides, { name: name.trim(), title: title.trim() || null });
    } else if (mt === "create_deployment_moment") {
      overrides.moment_type = momentType;
    }
    try { const r = await api.acceptProposal(p.id, { overrides }); toast(`Created ${r.created_type}`); onDone(r); }
    catch (e) { toast(e.message, "err"); }
  }
  async function reject() {
    if (done) return;
    try { const r = await api.rejectProposal(p.id); toast("Rejected"); onDone(r); }
    catch (e) { toast(e.message, "err"); }
  }
  const toggleEdit = () => setExpand((v) => !v);
  useImperativeHandle(ref, () => ({ accept, reject, toggleEdit }));

  const editable = mt === "create_commitment" || mt === "fill_placeholder" || mt === "create_deployment_moment";

  return (
    <div onClick={onFocusRow} style={{ padding: "10px 12px", borderBottom: "1px solid var(--line-hairline)", opacity: done ? 0.55 : 1,
      borderLeft: selected ? "3px solid var(--accent)" : "3px solid transparent", background: selected ? "var(--bg-selected)" : undefined }}>
      <div className="actions">
        <span className="badge">{LABEL[mt] || mt}</span>
        <strong style={{ fontWeight: 500 }}>{mt === "fill_placeholder" && p.payload.name ? p.payload.name : p.payload.description}</strong>
        <div className="spacer" />
        {done ? <span className="rowmeta">{p.status}</span> : <>
          {editable && <button className="btn small ghost" onClick={toggleEdit}>{expand ? "Hide" : "Details"}</button>}
          <button className="btn small" onClick={accept}>Accept</button>
          <button className="btn small ghost" onClick={reject}>Reject</button>
        </>}
      </div>
      <div className="rowmeta" style={{ marginTop: 2 }}>from: “{p.source_span}” · confidence {p.confidence}</div>
      {expand && !done && mt === "create_commitment" && (
        <div className="grid2" style={{ marginTop: 8 }}>
          <div className="field"><label>Responsible</label><select value={resp} onChange={(e) => setResp(e.target.value)}><option value="">—</option>{people.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div className="field"><label>Internal owner</label><select value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">—</option>{valence.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div className="field"><label>Due date</label><input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
        </div>
      )}
      {expand && !done && mt === "fill_placeholder" && (
        <div className="grid2" style={{ marginTop: 8 }}>
          <div className="field"><label>Name <span className="req">*</span></label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Person's name" /></div>
          <div className="field"><label>Title</label><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. VP of IT" /></div>
        </div>
      )}
      {expand && !done && mt === "create_deployment_moment" && (
        <div className="field" style={{ marginTop: 8, maxWidth: 240 }}>
          <label>Moment type</label>
          <select value={momentType} onChange={(e) => setMomentType(e.target.value)}>
            {MOMENT_TYPES.map((m) => <option key={m} value={m}>{m.replace(/_/g, " ")}</option>)}
          </select>
        </div>
      )}
    </div>
  );
});

const selS = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
