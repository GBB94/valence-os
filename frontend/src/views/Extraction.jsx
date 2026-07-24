import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast } from "../ui";

// Transcript extraction (v4). Paste a transcript, propose structured updates, accept
// each per-item. Nothing writes until you accept. Document content is data, not commands.
export default function Extraction({ accounts, accountId, setAccountId, reloadKey, onApplied }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [programId, setProgramId] = useState("");
  const [transcript, setTranscript] = useState("");
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState(null);
  const [mode, setMode] = useState("auto");       // 'auto' (mock/api) | 'manual' (paste local-LLM JSON)
  const [backend, setBackend] = useState("");     // '' = configured default, else 'mock'|'api'
  const [pasteJson, setPasteJson] = useState("");

  useEffect(() => { if (accountId) api.account(accountId).then(setDetail).catch(() => {}); }, [accountId]);
  useEffect(() => { api.extractionConfig().then(setConfig).catch(() => {}); }, []);
  const programs = detail?.programs ?? [];
  const people = detail?.people ?? [];

  async function doRun() {
    if (!transcript.trim()) { toast("Paste a transcript first", "err"); return; }
    setBusy(true);
    try { setRun(await api.runExtraction({ account_id: accountId, program_id: programId || null, transcript, backend: backend || null })); }
    catch (e) { toast(e.message, "err"); } finally { setBusy(false); }
  }
  async function doManual() {
    if (!pasteJson.trim()) { toast("Paste the model's JSON output first", "err"); return; }
    setBusy(true);
    try {
      const r = await api.manualExtraction({ account_id: accountId, program_id: programId || null, proposals_json: pasteJson });
      setRun(r); toast(`${r.proposals.length} proposal(s) ingested`);
    } catch (e) { toast(e.message, "err"); } finally { setBusy(false); }
  }
  async function copyPrompt() {
    try { await navigator.clipboard.writeText(`${config.manual_prompt}\n\n--- TRANSCRIPT ---\n${transcript}`); toast("Prompt + transcript copied"); }
    catch { toast("Copy failed", "err"); }
  }

  if (!accounts.length) return <div className="subtle">Create an account first.</div>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 6 }}>
        <h1>Transcript extraction</h1>
        <select value={accountId || ""} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); setRun(null); }} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={sel}>
          <option value="">— program (needed to apply) —</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div className="actions" style={{ marginBottom: 8 }}>
        <button className={"btn small" + (mode === "auto" ? " primary" : "")} onClick={() => setMode("auto")}>Auto</button>
        <button className={"btn small" + (mode === "manual" ? " primary" : "")} onClick={() => setMode("manual")}>Manual (local LLM)</button>
        {mode === "auto" && (
          <>
            <span className="rowmeta">backend:</span>
            <select value={backend} onChange={(e) => setBackend(e.target.value)} style={{ height: 26, borderRadius: 6, border: "1px solid var(--border)", padding: "0 6px" }}>
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
        <textarea value={transcript} onChange={(e) => setTranscript(e.target.value)} rows={6} placeholder="Paste the call transcript…" style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 12, border: "1px solid var(--border-strong)", borderRadius: 6, padding: 8 }} />
        {mode === "auto" ? (
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn primary" onClick={doRun} disabled={busy}>{busy ? "Extracting…" : "Extract proposals"}</button>
            {run && <span className="rowmeta">model {run.model_version} · prompt {run.prompt_version} · {run.proposals.length} proposals</span>}
          </div>
        ) : (
          <div style={{ marginTop: 8 }}>
            <button className="btn small" onClick={copyPrompt} disabled={!config}>Copy prompt + transcript</button>
            <div className="rowmeta" style={{ margin: "8px 0 4px" }}>Paste the model's JSON output:</div>
            <textarea value={pasteJson} onChange={(e) => setPasteJson(e.target.value)} rows={5} placeholder='{"proposals":[…]}' style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 12, border: "1px solid var(--border-strong)", borderRadius: 6, padding: 8 }} />
            <div className="actions" style={{ marginTop: 8 }}>
              <button className="btn primary" onClick={doManual} disabled={busy}>{busy ? "Ingesting…" : "Validate & ingest"}</button>
              {run && <span className="rowmeta">{run.model_version} · {run.proposals.length} proposals</span>}
            </div>
          </div>
        )}
      </div>

      {run && (
        <div className="card">
          <div className="card-h"><h3>Proposals</h3><div className="spacer" /><span className="rowmeta">accept or reject each</span></div>
          {run.proposals.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No structured updates found.</div> :
            run.proposals.map((p) => (
              <ProposalRow key={p.id} p={p} programId={programId} people={people}
                onDone={(r) => { setRun(patchRun(run, p.id, r)); onApplied?.(); }} />
            ))}
        </div>
      )}
    </div>
  );
}

// update one proposal's status locally after accept/reject
function patchRun(run, id, result) {
  const status = result.status || (result.created_type ? "accepted" : "proposed");
  return { ...run, proposals: run.proposals.map((x) => (x.id === id ? { ...x, status } : x)) };
}

function ProposalRow({ p, programId, people, onDone }) {
  const toast = useToast();
  const [expand, setExpand] = useState(false);
  const [resp, setResp] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const valence = people.filter((x) => x.affiliation === "valence");
  const isCommitment = p.mutation_type === "create_commitment";
  const done = p.status !== "proposed";

  async function accept() {
    if (!programId) { toast("Pick a program above to apply proposals", "err"); return; }
    const overrides = {};
    if (isCommitment) {
      if (!resp || !owner || !due) { setExpand(true); toast("Commitment needs responsible party, owner, and due date", "err"); return; }
      Object.assign(overrides, { responsible_party_id: resp, internal_owner_id: owner, due_date: due });
    }
    try { const r = await api.acceptProposal(p.id, { overrides }); toast(`Created ${r.created_type}`); onDone(r); }
    catch (e) { toast(e.message, "err"); }
  }
  async function reject() {
    try { const r = await api.rejectProposal(p.id); toast("Rejected"); onDone(r); }
    catch (e) { toast(e.message, "err"); }
  }

  return (
    <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", opacity: done ? 0.55 : 1 }}>
      <div className="actions">
        <span className="badge">{p.mutation_type.replace("create_", "")}</span>
        <strong style={{ fontWeight: 500 }}>{p.payload.description}</strong>
        <div className="spacer" />
        {done ? <span className="rowmeta">{p.status}</span> : <>
          {isCommitment && <button className="btn small ghost" onClick={() => setExpand((v) => !v)}>{expand ? "Hide" : "Details"}</button>}
          <button className="btn small" onClick={accept}>Accept</button>
          <button className="btn small ghost" onClick={reject}>Reject</button>
        </>}
      </div>
      <div className="rowmeta" style={{ marginTop: 2 }}>from: “{p.source_span}” · confidence {p.confidence}</div>
      {expand && !done && isCommitment && (
        <div className="grid2" style={{ marginTop: 8 }}>
          <div className="field"><label>Responsible</label><select value={resp} onChange={(e) => setResp(e.target.value)}><option value="">—</option>{people.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div className="field"><label>Internal owner</label><select value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">—</option>{valence.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
          <div className="field"><label>Due date</label><input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
        </div>
      )}
    </div>
  );
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
