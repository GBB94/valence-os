import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { answerBlocks } from "../copilotAnswer";
import { answerState, revealLabel } from "../copilotFreshness";
import { citationRuns, citedPacketIds, sourceForPacket } from "../inlineCitations";
import { AgeChip, Badge, Btn, Empty, useToast } from "../ui";

const STARTERS = [
  ["fact", "What did we promise and where does it stand?"],
  ["changes", "What changed since last week?"],
  ["weekly", "What needs my attention this week?"],
  ["synthesis", "What is blocking progress?"],
  ["company_brief", "Give me the grounded company brief"],
];

const STATE_LABEL = {
  supported: "Supported", partial: "Answer with gaps", conflicted: "Conflicted",
  insufficient: "Insufficient evidence",
};

/**
 * The answer body, rendered as blocks rather than as the raw markdown the generator emits. Every
 * block's text becomes a text node and never HTML — retrieved prose is untrusted data, so an HTML
 * path would let a record's contents become markup. See `copilotAnswer.js` for why the structure
 * cannot simply be dropped from the generator.
 */
/**
 * One line of answer prose, with the packet ids the claims block cites rendered as inline chips
 * (VISIBILITY-SPEC §7.1). A bracket the claims block does not cite stays literal text — that is a
 * validation failure upstream, and a working-looking chip would hide it.
 */
function Prose({ text, cited, onCite }) {
  if (!cited || !cited.size) return text;
  return citationRuns(text, cited).map((run, index) => run.kind === "text"
    ? <span key={index}>{run.text}</span>
    : <button key={index} type="button" className="cite-chip" onClick={() => onCite?.(run.packetId)}
        aria-label={`Open source ${run.packetId}`}>{run.number}</button>);
}

export function CopilotAnswer({ markdown, cited, onCite }) {
  const prose = (text) => <Prose text={text} cited={cited} onCite={onCite} />;
  return (
    <div className="copilot-answer">
      {answerBlocks(markdown).map((block, index) => {
        if (block.kind === "h2") return <h4 key={index}>{block.text}</h4>;
        if (block.kind === "h3") return <h5 key={index}>{block.text}</h5>;
        if (block.kind === "list") {
          return <ul key={index}>{block.items.map((item, i) => <li key={i}>{prose(item)}</li>)}</ul>;
        }
        return <p key={index}>{prose(block.text)}</p>;
      })}
    </div>
  );
}

export default function CopilotPanel({ scope, accountName, starter, onClose, onNavigateSource }) {
  const toast = useToast();
  const closeRef = useRef(null);
  const dialogRef = useRef(null);
  const [question, setQuestion] = useState(starter?.question || "");
  const [intent, setIntent] = useState(starter?.intent || "fact");
  const [run, setRun] = useState(null);
  const [history, setHistory] = useState([]);
  const [working, setWorking] = useState(false);
  const [details, setDetails] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null);
  const [draftPreview, setDraftPreview] = useState(null);
  const [savingDraft, setSavingDraft] = useState(false);

  // Same contract, same capture rule, and for the same reason as `ui.jsx`'s SlideOver: the opener is
  // read during the first render, because an effect keyed on the caller's `onClose` re-runs on every
  // render and would re-capture a control inside the panel. Restoring here rather than only from
  // `App.jsx` means the panel that owns the focus trap also owns giving focus back — the caller's
  // restore is a rAF, which never fires in a backgrounded tab.
  const openerRef = useRef(undefined);
  if (openerRef.current === undefined) openerRef.current = document.activeElement;
  useEffect(() => {
    closeRef.current?.focus();
    return () => {
      const opener = openerRef.current;
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  useEffect(() => {
    const key = (event) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll(
        'button:not([disabled]), textarea:not([disabled]), select:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])') || [])];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  useEffect(() => {
    const params = scope.scope_type === "portfolio"
      ? { scopeType: "portfolio" }
      : { scopeType: scope.scope_type, accountId: scope.account_id, programId: scope.program_id };
    api.copilotRuns(params).then((r) => setHistory(r.runs || [])).catch(() => {});
  }, [scope.scope_type, scope.account_id, scope.program_id]);

  async function ask(nextQuestion = question, nextIntent = intent) {
    if (!nextQuestion.trim()) return;
    const contextRunId = run?.status === "completed" ? run.id : null;
    setWorking(true); setRun(null); setSelectedSource(null); setDraftPreview(null);
    try {
      const queued = await api.createCopilotRun({ ...scope, query_text: nextQuestion,
        intent: nextIntent, context_run_id: contextRunId });
      await api.runJobs();
      const complete = await api.copilotRun(queued.id);
      setRun(complete);
      const params = scope.scope_type === "portfolio" ? { scopeType: "portfolio" }
        : { scopeType: scope.scope_type, accountId: scope.account_id, programId: scope.program_id };
      api.copilotRuns(params).then((r) => setHistory(r.runs || [])).catch(() => {});
    } catch (error) { toast(error.message, "err"); }
    finally { setWorking(false); }
  }

  async function feedback(issueKind, claimId = null, runSourceId = null) {
    try {
      await api.copilotFeedback(run.id, { issue_kind: issueKind, claim_id: claimId,
        run_source_id: runSourceId });
      toast("Feedback recorded. No account record was changed.");
    } catch (error) { toast(error.message, "err"); }
  }

  async function previewDraft() {
    try {
      setDraftPreview(await api.copilotDraftPreview(run.id,
        { title: `Internal note — ${accountName || "portfolio"}` }));
    } catch (error) { toast(error.message, "err"); }
  }

  async function saveDraft() {
    setSavingDraft(true);
    try {
      const doc = await api.copilotDraft(run.id, { title: draftPreview.title });
      toast(`Draft saved: ${doc.title}`);
      setDraftPreview(null);
    } catch (error) { toast(error.message, "err"); }
    finally { setSavingDraft(false); }
  }

  // The explicit action a past-window answer sits behind. It re-reads the same run and asks the
  // server for the body; it starts no new run, so what comes back is still what was written then.
  async function revealAnswer() {
    try { setRun(await api.copilotRun(run.id, { reveal: true })); }
    catch (error) { toast(error.message, "err"); }
  }

  async function markReviewed() {
    try { setRun(await api.copilotMarkReviewed(run.id)); toast("Change cursor advanced explicitly."); }
    catch (error) { toast(error.message, "err"); }
  }

  const scopeLabel = scope.scope_type === "portfolio" ? "Portfolio · all accounts"
    : scope.scope_type === "program" ? `${accountName} · selected program` : accountName;
  const answer = answerState(run);
  // The inline chips render only what the claims block below cites, from the same links. A chip
  // cannot point at a source the evidence block does not carry.
  const cited = citedPacketIds(run);

  // Portal to <body> so the panel clears the workspace's isolated stacking context; rendered
  // inline the sticky topbar painted over its header (same fix as the shared SlideOver).
  return createPortal(
    <>
      <div className="scrim" onClick={onClose} />
      <aside ref={dialogRef} className="slideover copilot-panel" role="dialog" aria-modal="true"
        aria-labelledby="copilot-title" aria-describedby="copilot-boundary">
        <header>
          <div>
            <h1 id="copilot-title">Account Copilot</h1>
            <div id="copilot-boundary" className="rowmeta">Internal records only · sources required · no actions taken</div>
          </div>
          <div className="spacer" />
          <button ref={closeRef} className="btn ghost" onClick={onClose}>Close</button>
        </header>
        <div className="body stack">
          <div className="actions">
            <Badge>{scopeLabel || "Explicit scope"}</Badge>
            <Badge>deterministic mock</Badge>
          </div>

          <div className="copilot-starters" aria-label="Prompt starters">
            {STARTERS.map(([key, text]) => <button key={key} className="filter-chip"
              onClick={() => { setIntent(key); setQuestion(text); ask(text, key); }}>{text}</button>)}
          </div>

          <form onSubmit={(event) => { event.preventDefault(); ask(); }}>
            <label htmlFor="copilot-question">Ask within this scope</label>
            <textarea id="copilot-question" value={question} rows={3} maxLength={1200}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a grounded account question…" />
            <div className="actions" style={{ marginTop: 8 }}>
              <select aria-label="Answer intent" value={intent} onChange={(event) => setIntent(event.target.value)}>
                <option value="fact">Answer</option><option value="synthesis">Synthesize</option>
                <option value="changes">What changed</option><option value="weekly">Plan this week</option>
                <option value="company_brief">Company brief</option>
              </select>
              <div className="spacer" />
              <Btn variant="primary" disabled={working || !question.trim()}>{working ? "Assembling…" : "Ask"}</Btn>
            </div>
          </form>

          {working && <div className="card" style={{ padding: 14 }} role="status">
            Queued through the local job worker. The panel remains usable.
          </div>}

          {run && <section aria-live="polite" className="stack">
            <div className="card" style={{ padding: 14 }}>
              <div className="actions">
                <Badge>{STATE_LABEL[run.evidence_state] || run.status}</Badge>
                {/* The decay ramp, on the one surface that persists generated prose. A run asked a
                    minute ago and one re-opened from history six months later reach this line the
                    same way — the signal is the date, not how the run arrived. */}
                <span className="rowmeta">Answered {run.generated_at?.slice(0, 10) || "unknown"}</span>
                <AgeChip date={run.generated_at} />
              </div>
              {run.intent === "changes" && <div className="rowmeta" style={{ marginTop: 6 }}>
                Interpreted window: {run.time_window_start || "first recorded change"} → {run.time_window_end || run.generated_at || "now"}
                {run.context_run_id ? " · bounded follow-up" : ""}
              </div>}
              {run.status === "abstained"
                ? <Empty title="I can't defend an answer from this scope">{run.failure_detail}</Empty>
                : answer.withheld && !answer.revealed
                  // Withheld, not dimmed. A greyed paragraph is still a rendering of the claim, and
                  // an operator reads it as the claim. The sentence is the server's, unedited; the
                  // claims block below stays open either way, because an operator handed a refusal
                  // needs the evidence that explains it.
                  ? <div className="copilot-withheld" role="note">
                      <p>{answer.sentence}</p>
                      <Btn variant="ghost" onClick={revealAnswer}>{revealLabel(run)}</Btn>
                    </div>
                  : <>
                      {answer.revealed && <p className="copilot-withheld-note">{answer.sentence}</p>}
                      <CopilotAnswer markdown={run.answer_markdown} cited={cited}
                        onCite={(packetId) => setSelectedSource(sourceForPacket(run, packetId))} />
                    </>}
              {!!run.gaps?.length && <div className="copilot-gaps">
                <strong>Named gaps</strong>
                <ul>{run.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul>
              </div>}
            </div>

            {!!run.claims?.length && <div className="card">
              <div className="card-h"><h3>Claims and exact support</h3></div>
              {run.claims.map((claim) => <div key={claim.id} className="copilot-claim">
                <div><Badge>{claim.kind}</Badge> {claim.claim_text}</div>
                <div className="chiprow" style={{ marginTop: 6 }}>
                  {claim.sources.map((link) => {
                    const source = run.sources.find((item) => item.id === link.source_id);
                    return <button key={link.source_id} className="filter-chip"
                      onClick={() => source && setSelectedSource(source)}>
                      {link.packet_id} · {source?.record_type?.replaceAll("_", " ")}
                      {source?.archived_after_answer ? " · archived after answer" : ""}
                    </button>;
                  })}
                  <button className="btn small ghost" onClick={() => feedback("wrong_fact", claim.id)}>Flag claim</button>
                </div>
              </div>)}
            </div>}

            {selectedSource && <div className="card copilot-source-drawer" role="region" aria-label="Frozen source snapshot">
              <div className="card-h"><div><h3>{selectedSource.packet_id} · {selectedSource.record_type.replaceAll("_", " ")}</h3>
                <div className="rowmeta">Frozen version {selectedSource.record_version} · {selectedSource.freshness_state}
                  {selectedSource.archived_after_answer ? " · native record is now archived" : ""}</div></div>
                <button className="btn small ghost" onClick={() => setSelectedSource(null)}>Close source</button></div>
              <dl className="copilot-source-fields">{Object.entries(selectedSource.fields || {}).map(([key, value]) =>
                <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{key === "source_url" && value
                  ? <a href={String(value)} target="_blank" rel="noreferrer">Open exact source</a>
                  : value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>
              <div className="actions" style={{ padding: "0 12px 12px" }}>
                <Btn onClick={() => onNavigateSource?.({ ...selectedSource,
                  record_type: selectedSource.fields?.native_record_type || selectedSource.record_type,
                  record_id: selectedSource.fields?.native_record_id || selectedSource.record_id,
                })}>Open canonical record</Btn>
                <Btn variant="ghost" onClick={() => feedback("wrong_source", null, selectedSource.id)}>Wrong source</Btn>
                <Btn variant="ghost" onClick={() => feedback("stale_or_superseded_source", null, selectedSource.id)}>Stale / superseded</Btn>
              </div>
            </div>}

            {draftPreview && <div className="card copilot-draft-preview" role="region" aria-label="Internal draft preview">
              <div className="card-h"><div><h3>Preview before saving</h3><div className="rowmeta">Internal only · source run {draftPreview.source_run_id}</div></div></div>
              <CopilotAnswer markdown={draftPreview.markdown} />
              <div className="actions" style={{ padding: 12 }}>
                <Btn variant="primary" onClick={saveDraft} disabled={savingDraft}>{savingDraft ? "Saving…" : "Save internal draft"}</Btn>
                <Btn variant="ghost" onClick={() => setDraftPreview(null)}>Cancel</Btn>
              </div>
            </div>}

            <div className="actions">
              {/* A withheld answer cannot seed a saved note either — the server refuses it, and a
                  control that looks available up to the moment it fails is worse than one that says
                  why. Disabled, with the same clause. */}
              {run.status === "completed" && <Btn onClick={previewDraft} disabled={answer.withheld}
                title={answer.withheld ? answer.sentence : undefined}>Preview internal draft</Btn>}
              {run.intent === "changes" && run.status === "completed" && !run.reviewed_at &&
                <Btn onClick={markReviewed}>Mark brief reviewed</Btn>}
              <Btn variant="ghost" onClick={() => feedback("helpful")}>Helpful</Btn>
              <Btn variant="ghost" onClick={() => feedback("unhelpful")}>Not helpful</Btn>
            </div>

            <div className="card">
              <button className="collapsible-head" aria-expanded={details} onClick={() => setDetails((value) => !value)}>
                {details ? "▾" : "▸"} How this was assembled
              </button>
              {details && <div style={{ padding: "0 16px 16px" }}>
                <div><strong>Readers:</strong> {(run.readers || []).join(", ") || "none"}</div>
                <div><strong>Retrieved:</strong> {run.sources?.length || 0} snapshots · <strong>Excluded:</strong> {run.excluded?.length || 0}</div>
                <div><strong>Resolved:</strong> {run.resolved_entities?.length ? run.resolved_entities.map((entity) =>
                  `${entity.label || entity.name || entity.entity_text} (${entity.match_kind || "exact"})`).join(", ") : "none"}</div>
                <div className="rowmeta">{run.model_version} · {run.prompt_version} · {run.retrieval_version} · {run.validator_version}</div>
              </div>}
            </div>
          </section>}

          {!run && !!history.length && <section>
            <h2>Saved runs</h2>
            <div className="card">
              {history.slice(0, 6).map((item) => <button key={item.id} className="copilot-history"
                onClick={() => api.copilotRun(item.id).then(setRun).catch((error) => toast(error.message, "err"))}>
                <span>{item.query_text}</span>
                <span className="rowmeta">{item.status} · {item.created_at?.slice(0, 10)}
                  {" "}<AgeChip date={item.generated_at || item.created_at} /></span>
              </button>)}
            </div>
          </section>}
        </div>
      </aside>
    </>,
    document.body,
  );
}
