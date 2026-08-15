import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast } from "../ui";
import ProposalReview from "./ProposalReview";

// Transcript / email extraction (v4 + §4.4). This screen is the *ingest* half: paste text, run the
// configured extractor, and hand the result to the one review surface. It used to carry its own
// row-level accept/reject, keyed on the legacy `mutation_type` enum — which could only ever
// describe creations, and which drifted from the surface Overview opens. Reviewing happens in
// exactly one place now (ProposalReview), so a command means the same thing wherever you reach it.
// Nothing writes until someone accepts; document content is data, not commands.

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
  const [reviewKey, setReviewKey] = useState(0);

  useEffect(() => { if (accountId) api.account(accountId).then(setDetail).catch(() => {}); }, [accountId]);
  useEffect(() => { api.extractionConfig().then(setConfig).catch(() => {}); }, []);
  const programs = detail?.programs ?? [];

  async function doRun() {
    if (!transcript.trim()) { toast("Paste a transcript first", "err"); return; }
    setBusy(true);
    try {
      setRun(await api.runExtraction({ account_id: accountId, program_id: programId || null, transcript, backend: backend || null }));
      setReviewKey((n) => n + 1);
    }
    catch (e) { toast(e.message, "err"); } finally { setBusy(false); }
  }
  async function doManual() {
    if (!pasteJson.trim()) { toast("Paste the model's JSON output first", "err"); return; }
    setBusy(true);
    try {
      const r = await api.manualExtraction({ account_id: accountId, program_id: programId || null, proposals_json: pasteJson });
      setRun(r); setReviewKey((n) => n + 1); toast(`${r.proposals.length} proposal(s) ingested`);
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
        <button className={"btn small" + (mode === "auto" ? " selected" : "")} aria-pressed={mode === "auto"} onClick={() => setMode("auto")}>Auto</button>
        <button className={"btn small" + (mode === "manual" ? " selected" : "")} aria-pressed={mode === "manual"} onClick={() => setMode("manual")}>Manual (local LLM)</button>
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
        <div className="card" style={{ padding: 12 }}>
          <div className="card-h">
            <h3>Review</h3>
            <div className="spacer" />
            <span className="rowmeta">{run.proposals.length} from this run</span>
          </div>
          {run.proposals.length === 0 ? (
            <div className="rowmeta" style={{ padding: 12 }}>No structured updates found.</div>
          ) : (
            // Scoped to this run's source interaction when it has one, so the list is what you just
            // extracted; a paste with no interaction falls back to the account's pending queue
            // rather than silently showing nothing.
            <ProposalReview accountId={accountId} programId={programId}
              sourceInteractionId={run.interaction_id || ""}
              reloadKey={reviewKey + (reloadKey || 0)}
              onApplied={onApplied} />
          )}
        </div>
      )}
    </div>
  );
}


const selS = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
