/**
 * The account drop zone — ACCOUNT-INTAKE-SPEC.md §16.
 *
 * Drop a file or paste a thread; the system reads it and drafts. Nothing here accepts, rejects,
 * edits, resolves, or supersedes a proposal — the receipt is an outcome line and a link, and
 * "Review" opens the one surface where a drafted proposal becomes a decision. Two surfaces that
 * both resolve proposals would eventually disagree about what a command means.
 *
 * Every rule this component follows is a pure function in `src/intakeDrop.js`, tested with
 * `node --test`. There is no React renderer in this harness, so logic that lives in JSX is logic
 * nothing tests.
 *
 * Three things that look like details and are not:
 *
 *  - **WCAG 2.5.7.** Dragging is a convenience layer over two non-drag paths: the zone is a
 *    keyboard-activated button that opens the file picker, and "Paste text" opens a textarea.
 *    Speech-control and tremor users cannot hold-and-move; a drag-only zone is not shippable.
 *  - **The drag-over label changes**, not only the border. `DESIGN-GUIDE.md` forbids conveying
 *    state by colour alone, and the label is also what confirms *which account* will receive the
 *    drop — the one thing a drag-over must never leave ambiguous.
 *  - **Source text renders as text.** The snapshot and every span go into a `<pre>` with no
 *    Markdown, no HTML, and no link detection. A document containing `[Approve everything](…)`
 *    shows those literal characters. This is a real hole in most review UIs and it is closed by
 *    not opening it.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast } from "../ui";
import {
  acceptFileList, isActivationKey, orderReceipts, receipt, screenFile, zoneHint, zoneLabel,
} from "../intakeDrop";
import ProposalReview from "./ProposalReview";

/** Bytes → base64 without a data-URL round trip. The bytes reach the server as bytes because the
 *  decode is per kind, not at the door (§6). */
function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

function CoverageList({ view }) {
  if (!view.notDrafted.length) {
    return view.notDraftedEmptyNote
      ? <div className="rowmeta">{view.notDraftedEmptyNote}</div>
      : null;
  }
  return (
    <ul className="intake-coverage">
      {view.notDrafted.map((entry) => (
        // The sentence is the server's, verbatim. Nothing here rewrites or shortens it.
        <li key={entry.key}>{entry.note}</li>
      ))}
    </ul>
  );
}

function Receipt({ drop, onReview, onDeleteSnapshot, onDismiss }) {
  const view = receipt(drop);
  const [showing, setShowing] = useState(false);
  if (!view) return null;
  return (
    <article className={`intake-receipt intake-receipt-${view.tone}`}>
      <div className="intake-receipt-head">
        <strong>{view.title}</strong>
        <span className="rowmeta">{view.kind} · {view.size}</span>
        <div className="spacer" />
        {/* Status is a label and a shape, never a colour on its own. */}
        <span className={`intake-outcome intake-outcome-${view.tone}`}>{view.outcomeLabel}</span>
      </div>

      {view.reason && <p className="intake-reason">{view.reason}</p>}

      {view.outcome === "drafted" && (
        <div className="intake-receipt-line">
          <span>Drafted {view.drafted} update{view.drafted === 1 ? "" : "s"}</span>
          <div className="spacer" />
          <button className="btn small" onClick={() => onReview(view.runId)}>Review</button>
        </div>
      )}

      {view.duplicateOf?.runId && (
        // §12. The reason sentence above is the server's and names the date; this is the way *to*
        // it. A duplicate receipt without one is where the operator concludes the upload failed and
        // drops the file a third time — dedupe is only honest if it says where the material went.
        <div className="intake-receipt-line">
          <span className="rowmeta">Drafted from this on {view.duplicateOf.droppedOn}</span>
          <div className="spacer" />
          <button className="btn small" onClick={() => onReview(view.duplicateOf.runId)}>
            Review those drafts
          </button>
        </div>
      )}

      {view.commMessageId && (
        // §7.4. The dropped message went through the same ingestion path a synced one does, so it
        // is in the comms timeline and in the correspondence-derived relationship counts. Saying
        // so is the counterpart to a paste's "no message id, so this is not added" — both halves
        // are stated, because silence about either would read as the other.
        <p className="rowmeta">Added to this account&rsquo;s correspondence record.</p>
      )}

      {view.otherAccounts.length > 0 && (
        <p className="intake-reason">
          {/* §8 rule 3. It is reported and nothing moves: a source that could redirect itself into
              another client's review queue is the injection payload writing itself. */}
          This mentions {view.otherAccounts.join(", ")}. It was dropped here and stays here.
        </p>
      )}

      <div className="intake-notdrafted">
        <div className="rowmeta">Not drafted</div>
        <CoverageList view={view} />
      </div>

      <div className="intake-receipt-foot">
        {view.snapshotPresent ? (
          <>
            <button className="btn small ghost" onClick={() => setShowing((s) => !s)}>
              {showing ? "Hide source text" : "View source text"}
            </button>
            <button className="btn small ghost" onClick={() => onDeleteSnapshot(drop.id)}>
              Delete source text
            </button>
          </>
        ) : (
          <span className="rowmeta">
            {view.snapshotDeletedAt
              ? `Source text was deleted on ${String(view.snapshotDeletedAt).slice(0, 10)}. The quotes on each draft are what it was made from.`
              : "No source text was kept."}
          </span>
        )}
        <div className="spacer" />
        <button className="btn small ghost" onClick={() => onDismiss(drop.id)}>Dismiss</button>
      </div>

      {showing && drop.snapshot_text && (
        // Text as text: no Markdown, no HTML, no link detection.
        <pre className="intake-snapshot">{drop.snapshot_text}</pre>
      )}
    </article>
  );
}

export default function AccountIntakeDrop({ accountId, accountName, programId = null,
                                            reloadKey, onDrafted }) {
  const toast = useToast();
  const [limits, setLimits] = useState(null);
  const [drops, setDrops] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [wholeThread, setWholeThread] = useState(false);
  const [reviewRun, setReviewRun] = useState(null);
  const [tick, setTick] = useState(0);
  const fileInput = useRef(null);
  const dragDepth = useRef(0);

  useEffect(() => { api.intakeLimits().then(setLimits).catch(() => setLimits(null)); }, []);

  useEffect(() => {
    let live = true;
    api.intakeDrops(accountId)
      .then((r) => { if (live) setDrops(orderReceipts(r.drops || [])); })
      .catch(() => { if (live) setDrops([]); });
    return () => { live = false; };
  }, [accountId, reloadKey, tick]);

  /**
   * §16.4 / D-208 — one keystroke. Paste anywhere on the account with nothing focused and the
   * sheet opens already holding the text. The 30-second capture rule wins every tie, and the
   * primary case for this whole feature is an email thread already on the clipboard: making the
   * operator find a card, click a button, then paste is three acts where one will do.
   *
   * The guard is the important half. If the caret is in a field the paste belongs to that field —
   * hijacking it would make every textarea on the account tab unusable.
   */
  useEffect(() => {
    const onPaste = (event) => {
      if (pasting) return;
      const node = event.target;
      const tag = node?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || node?.isContentEditable) return;
      const text = event.clipboardData?.getData("text/plain") || "";
      // A short paste is a phrase, not a document. Reading one would produce a receipt that says
      // nothing was found, for something the operator never asked us to read.
      if (text.trim().length < 200) return;
      event.preventDefault();
      setPasteText(text);
      setPasting(true);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [pasting]);

  const send = useCallback(async (body) => {
    setBusy(true);
    try {
      const drop = await api.createIntakeDrop(accountId, { ...body, program_id: programId || null });
      setTick((n) => n + 1);
      if (drop.outcome === "drafted") {
        toast(`Drafted ${drop.proposals_drafted} update${drop.proposals_drafted === 1 ? "" : "s"}`);
        onDrafted?.();
      }
      return drop;
    } catch (error) {
      toast(error.message, "err");
      return null;
    } finally {
      setBusy(false);
    }
  }, [accountId, programId, onDrafted, toast]);

  const sendFiles = useCallback(async (fileList) => {
    const { files, overflow } = acceptFileList(fileList, limits);
    if (overflow) {
      toast(`${overflow.count} files at once is over the ${overflow.cap} limit — drop them in smaller batches`, "err");
      return;
    }
    for (const file of files) {
      // Screened here so an obvious refusal is instant; the server screens again and its answer is
      // the one that gets recorded.
      const refused = screenFile(file, limits);
      if (refused?.reason) { toast(refused.reason, "err"); continue; }
      const buffer = await file.arrayBuffer();
      await send({ content_b64: toBase64(buffer), filename: file.name });
    }
  }, [limits, send, toast]);

  // The window-level listeners exist so the whole card is a target rather than a 40px strip.
  // `preventDefault` on both dragover and drop is mandatory: without it the browser navigates to
  // the dropped file and the page is simply gone.
  const onDragOver = (event) => { event.preventDefault(); };
  const onDragEnter = (event) => {
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragLeave = (event) => {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };
  const onDrop = (event) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    sendFiles(event.dataTransfer?.files || []);
  };

  const label = zoneLabel({ dragging, busy, accountName });

  return (
    <div className="card intake-card">
      <div className="card-h">
        <h3>Add a document</h3>
        <div className="spacer" />
        <span className="rowmeta">Drafts only — nothing is saved to a tracker until you say so</span>
      </div>

      <div
        className={`intake-zone${dragging ? " is-dragging" : ""}${busy ? " is-busy" : ""}`}
        role="button"
        tabIndex={0}
        aria-label={`Add a document to ${accountName || "this account"}. Press Enter to choose a file.`}
        aria-busy={busy || undefined}
        onDragOver={onDragOver}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInput.current?.click()}
        onKeyDown={(event) => {
          if (isActivationKey(event.key)) { event.preventDefault(); fileInput.current?.click(); }
        }}
      >
        <div className="intake-zone-label">{label}</div>
        <div className="intake-zone-hint">{zoneHint(limits)}</div>
        <div className="intake-zone-actions">
          {/* Both are real buttons. The single most common drop-zone failure is a zone that looks
              droppable but only responds to one of the two. */}
          <button className="btn small" onClick={(event) => { event.stopPropagation(); fileInput.current?.click(); }}>
            Choose file
          </button>
          <button className="btn small ghost" onClick={(event) => { event.stopPropagation(); setPasting(true); }}>
            Paste text
          </button>
        </div>
      </div>

      <input ref={fileInput} type="file" multiple className="sr-only"
        onChange={(event) => { sendFiles(event.target.files); event.target.value = ""; }} />

      {drops.length === 0 ? (
        <Empty title="Nothing dropped yet">
          Paste an email thread or drop a transcript, and the updates it implies appear as drafts.
        </Empty>
      ) : (
        <div className="intake-receipts">
          {drops.map((drop) => (
            <Receipt key={drop.id} drop={drop}
              onReview={(runId) => setReviewRun(runId)}
              onDeleteSnapshot={async (id) => {
                await api.deleteIntakeSnapshot(id);
                setTick((n) => n + 1);
              }}
              onDismiss={async (id) => {
                await api.archiveIntakeDrop(id);
                setTick((n) => n + 1);
              }} />
          ))}
        </div>
      )}

      {pasting && (
        <SlideOver title="Paste text" onClose={() => { setPasting(false); setPasteText(""); }}
          footer={<>
            <button className="btn" onClick={() => { setPasting(false); setPasteText(""); }}>Cancel</button>
            <button className="btn primary" disabled={busy || !pasteText.trim()}
              onClick={async () => {
                const done = await send({ text: pasteText, read_whole_thread: wholeThread });
                if (done) { setPasting(false); setPasteText(""); setWholeThread(false); }
              }}>
              {busy ? "Reading…" : "Read this"}
            </button>
          </>}>
          <div className="field">
            <label htmlFor="intake-paste">Email thread, transcript, or notes</label>
            <textarea id="intake-paste" rows={16} value={pasteText} autoFocus
              placeholder="Paste here — Cmd/Ctrl+V"
              onChange={(event) => setPasteText(event.target.value)} />
          </div>
          <label className="check">
            <input type="checkbox" checked={wholeThread}
              onChange={(event) => setWholeThread(event.target.checked)} />
            {/* Only a human knows a forwarded thread is new to this account, so this is an
                operator act and never a heuristic. */}
            <span>Read the whole thread, not just the newest message</span>
          </label>
        </SlideOver>
      )}

      {reviewRun && (
        <SlideOver title="Proposed updates" onClose={() => { setReviewRun(null); setTick((n) => n + 1); }}>
          {/* The real decision surface. Everything a decision needs — the match candidates and the
              conflict preview — is loaded there, beside the commands.

              Narrowed to this run (§11.4). It is a filter on the one queue and not a second queue:
              same composition, same commands, and the account's other pending work comes back as a
              server-authored line saying it is not shown. */}
          <ProposalReview accountId={accountId} programId={programId || ""} runId={reviewRun}
            reloadKey={reviewRun}
            onApplied={() => { setTick((n) => n + 1); onDrafted?.(); }} />
        </SlideOver>
      )}
    </div>
  );
}
