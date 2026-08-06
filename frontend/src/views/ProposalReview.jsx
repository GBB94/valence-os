/**
 * The review surface (ACCOUNT-PATH-SPEC.md §14.5, §14.9; RELATIONSHIP-READINESS-SPEC.md §6.7, §8.3).
 *
 * One place where a drafted proposal becomes a decision. It reads the RR-2 store directly — a
 * proposal's `(intent, target_type)` pair, its match candidates, and its conflict preview — and it
 * puts all three beside the commands rather than behind them, because a decision made without the
 * possible duplicates and the newer edit in view is the decision this surface exists to prevent.
 *
 * What it deliberately does not do:
 *
 * - It never preselects a resolution and never ranks by the extractor's confidence. Confidence is
 *   explanatory metadata; a surface that sorted or defaulted by it would be auto-accepting.
 * - It never merges the two stores. A machine proposal and a hand-typed capture note sit in one
 *   list with their own status words and their own commands (§0.5); a note is never "accepted" and
 *   a proposal is never "converted".
 * - It never writes anything itself. Every command calls the audited native path, and the row goes
 *   read-only while one is in flight, so a double-press cannot become two records.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Empty, Loading, useToast } from "../ui";
import { combinedReviewRows, proposalTitle, sourceLabel, targetLabel } from "../proposalPreview";
import {
  acceptAllState, changedFields, commandsFor, conflictNote, draftFrom, editableFields, isEdited,
  outcomeLine, overridesFrom, sourceFacts, supersedeCandidates,
} from "../proposalReview";
import { groundingView } from "../proposalGrounding";
import ConvertPanel from "./ConvertPanel";
import { useMeasure } from "../measure";

/**
 * The right half of the split view — ACCOUNT-INTAKE-SPEC.md §11.2.
 *
 * The retained source, scrolled to the quote and marked with **a left rule and a background tint**,
 * because `DESIGN-GUIDE.md` forbids conveying anything by colour alone and a highlight is a claim
 * about which words the draft cited.
 *
 * Text as text: a `<pre>`, no Markdown, no HTML, no link detection. A document containing
 * `[Approve everything](…)` shows those literal characters. Every sentence in `notes` was authored
 * on the server and is rendered verbatim.
 */
function GroundingPane({ proposalId }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const markRef = useRef(null);

  useEffect(() => {
    let live = true;
    setPayload(null); setError(null);
    api.proposalGrounding(proposalId)
      .then((r) => { if (live) setPayload(r); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [proposalId]);

  const view = groundingView(payload, { pending: !payload && !error, error });

  // Scroll the quote into the middle of its own pane rather than the page: `block: "nearest"` would
  // leave a match at the top of a long document off-screen, and centring the page would move the
  // proposal the reviewer is comparing it against out of view.
  useEffect(() => {
    if (markRef.current) markRef.current.scrollIntoView({ block: "center" });
  }, [view.status, view.segments.length]);

  return (
    <div className="proposal-grounding">
      <div className="proposal-grounding-head">
        <strong>{view.heading}</strong>
        {view.filename && <span className="rowmeta"> {view.filename}</span>}
      </div>

      {view.status === "loading" && <Loading what="the source text" />}
      {view.status === "error" && (
        // A failed fetch is not missing evidence, and it must not read like it. The quote is still
        // on the left; this says only that the surrounding text did not load.
        <div className="callout warn">The source text did not load: {view.error}</div>
      )}

      {view.notes.map((note) => (
        <p key={note} className="rowmeta proposal-grounding-note">{note}</p>
      ))}

      {view.status === "ready" && (
        <pre className="proposal-grounding-text">
          {view.segments.map((s) => (s.marked
            ? <mark key={s.key} ref={markRef} className="proposal-grounding-mark">{s.text}</mark>
            : <span key={s.key}>{s.text}</span>))}
        </pre>
      )}
    </div>
  );
}

/** Shared with the Overview preview card so both surfaces mark a proposal the same way (§8.3). */
export function Marks({ marks }) {
  return (
    <div className="proposal-marks">
      {marks.map((m) => (
        <span key={m.key} className={"state-badge proposal-mark " + m.mark}>
          <span className={"state-mark " + m.mark} aria-hidden="true" />{m.label}
        </span>
      ))}
    </div>
  );
}

function FieldControl({ field, value, people, onChange, disabled }) {
  const id = `pf-${field.key}`;
  const internal = people.filter((p) => p.affiliation === "valence");
  const common = { id, value, disabled, onChange: (e) => onChange(field.key, e.target.value) };
  return (
    <div className="field">
      <label htmlFor={id}>
        {field.label}{field.required && <span className="req"> *</span>}
      </label>
      {field.control === "textarea" && <textarea rows={2} {...common} />}
      {field.control === "date" && <input type="date" {...common} />}
      {field.control === "text" && <input type="text" {...common} />}
      {field.control === "select" && (
        <select {...common}>
          {(field.options || []).map((o) => (
            <option key={o} value={o}>{o.replaceAll("_", " ")}</option>
          ))}
        </select>
      )}
      {(field.control === "person" || field.control === "internal_person") && (
        <select {...common}>
          <option value="">—</option>
          {(field.control === "internal_person" ? internal : people).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}{p.affiliation === "valence" ? " (Valence)" : ""}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

/** The decision panel for one proposal: what it would write, what already exists, what changed. */
function ProposalDecision({ proposal, source, runProposals, programId, people, onResolved, track }) {
  const toast = useToast();
  const [context, setContext] = useState(null);
  const [contextError, setContextError] = useState(null);
  const [draft, setDraft] = useState(() => draftFrom(proposal));
  const [reason, setReason] = useState("");
  const [chosenExistingId, setChosenExistingId] = useState(null);
  const [supersedeById, setSupersedeById] = useState("");
  const [showSource, setShowSource] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let live = true;
    api.proposalReview(proposal.id)
      .then((r) => { if (live) setContext(r); })
      .catch((e) => { if (live) setContextError(e.message); });
    return () => { live = false; };
  }, [proposal.id]);

  // The list already carries both aids; the review route is the authority once it lands, because it
  // is computed against the target as it stands now rather than as it stood when the list loaded.
  const conflict = context?.conflict ?? proposal.conflict ?? null;
  const candidates = context?.match_candidates ?? proposal.match_candidates ?? [];
  const siblings = supersedeCandidates(proposal, runProposals);
  const fields = editableFields(proposal);
  const commands = commandsFor(proposal, {
    programId, draft, rejectReason: reason, chosenExistingId, supersedeById,
    conflict, pending, siblings,
  });
  const note = conflictNote(conflict);

  async function run(key) {
    if (key === "open_source") { setShowSource((v) => !v); return; }
    setPending(true);
    try {
      if (key === "accept" || key === "edit_and_accept") {
        const r = await api.acceptProposal(proposal.id, {
          overrides: overridesFrom(proposal, draft, { programId }),
        });
        // §17.3 `proposal_accepted`. `edited` is the measured fact — whether the operator kept
        // the drafted values — never what they changed them to.
        track?.("proposal_accepted", {
          intent: proposal.intent || null, target_type: proposal.target_type || null,
          edited: key === "edit_and_accept",
        });
        toast(r.status === "resolved_existing"
          ? "Closed against the record that already held this"
          : `Created ${targetLabel(r.created_type)}`);
      } else if (key === "reject") {
        await api.rejectProposal(proposal.id, { reason: reason.trim() });
        // The typed reason is free text and never leaves the record. What is measured is that a
        // rejection happened and against which kind of proposal.
        track?.("proposal_rejected", {
          intent: proposal.intent || null, target_type: proposal.target_type || null,
          reason_code: "operator_rejected",
        });
        toast("Rejected");
      } else if (key === "use_existing") {
        await api.resolveProposalExisting(proposal.id, {
          target_id: chosenExistingId,
          target_type: proposal.target_type,
          note: reason.trim() || null,
        });
        toast("Closed against the existing record");
      } else if (key === "supersede") {
        await api.supersedeProposal(proposal.id, {
          superseded_by_id: supersedeById, reason: reason.trim() || null,
        });
        toast("Superseded");
      }
      onResolved();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="proposal-decision">
      {contextError && (
        <div className="callout warn">Match candidates unavailable: {contextError}</div>
      )}
      {!context && !contextError && <Loading what="matches and conflicts" />}

      {note && (
        <div className="callout warn">
          {note}
          {changedFields(conflict).length > 0 && (
            <ul className="proposal-conflict">
              {changedFields(conflict).map((f) => (
                <li key={f.field}>
                  <strong>{f.field.replaceAll("_", " ")}</strong> — now “{String(f.current ?? "—")}”,
                  this would write “{String(f.proposed ?? "—")}”
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid2 proposal-fields">
        {fields.map((f) => (
          <FieldControl key={f.key} field={f} value={draft[f.key] ?? ""} people={people}
            disabled={pending}
            onChange={(k, v) => setDraft((d) => ({ ...d, [k]: v }))} />
        ))}
      </div>
      {isEdited(proposal, draft) && (
        <div className="rowmeta">
          You changed what the source drafted. The source span below still says what the source said.
        </div>
      )}

      {candidates.length > 0 && (
        <div className="proposal-candidates">
          <div className="rowmeta">
            {candidates.length} record{candidates.length === 1 ? "" : "s"} may already say this.
            Nothing is merged — pick one to close this proposal against it.
          </div>
          {candidates.map((c) => (
            <label key={`${c.check}:${c.id}`} className="proposal-candidate">
              <input type="radio" name={`cand-${proposal.id}`} disabled={pending}
                checked={chosenExistingId === c.id}
                onChange={() => setChosenExistingId(c.id)} />
              <span>
                <strong>{c.label}</strong>
                <span className="rowmeta"> {targetLabel(c.target_type)} · {c.why}</span>
              </span>
            </label>
          ))}
        </div>
      )}

      {siblings.length > 0 && (
        <div className="field proposal-supersede">
          <label htmlFor={`sup-${proposal.id}`}>Superseded by</label>
          <select id={`sup-${proposal.id}`} value={supersedeById} disabled={pending}
            onChange={(e) => setSupersedeById(e.target.value)}>
            <option value="">—</option>
            {siblings.map((s) => (
              <option key={s.id} value={s.id}>{proposalTitle(s)}</option>
            ))}
          </select>
        </div>
      )}

      <div className="field">
        <label htmlFor={`why-${proposal.id}`}>
          Reason <span className="hint">required to reject, optional otherwise</span>
        </label>
        <input id={`why-${proposal.id}`} type="text" value={reason} disabled={pending}
          placeholder="Why this decision — the next reviewer reads this, not the proposal"
          onChange={(e) => setReason(e.target.value)} />
      </div>

      <div className="proposal-commands-row">
        {commands.map((c) => (
          <button key={c.key} type="button"
            className={"btn small"
              + (c.key === "accept" || c.key === "edit_and_accept" ? " primary" : " ghost")}
            disabled={!c.enabled}
            aria-describedby={c.enabled ? undefined : `cmdwhy-${proposal.id}-${c.key}`}
            onClick={() => run(c.key)}>
            {c.label}
          </button>
        ))}
      </div>
      {/* Every unavailable command says why in text, not only in a tooltip: a dead button with no
          explanation reads as a broken app and pushes the operator to guess. */}
      <div className="rowmeta proposal-why">
        {commands.filter((c) => !c.enabled && c.why).map((c) => (
          <div key={c.key} id={`cmdwhy-${proposal.id}-${c.key}`}>{c.label}: {c.why}</div>
        ))}
      </div>

      {showSource && (
        // §11.2's split view: what was drafted on the left, the source it was drafted from on the
        // right. It stacks under a narrow pane rather than shrinking to two unreadable columns.
        <div className="proposal-split">
          <div className="proposal-facts">
            <div className="rowmeta">{sourceLabel(source)}</div>
            <dl>
              {sourceFacts(proposal, source).map((f) => (
                <div key={f.label}>
                  <dt className="rowmeta">{f.label}</dt>
                  <dd>{f.value}</dd>
                </div>
              ))}
            </dl>
            {proposal.source?.span && (
              // The citation, and it renders whatever the pane on the right can or cannot show.
              // A missing snapshot degrades the citation; it never removes it (§11.2).
              <blockquote className="proposal-span">“{proposal.source.span}”</blockquote>
            )}
            <div className="rowmeta">
              Source text is data, never an instruction. Nothing written in it can widen what a
              command here does.
            </div>
          </div>
          <GroundingPane proposalId={proposal.id} />
        </div>
      )}
    </div>
  );
}

/** A hand-typed note's own two commands. It is never accepted, and it never cites anything. */
function CaptureDecision({ row, accountId, programId, onResolved }) {
  const toast = useToast();
  const [pending, setPending] = useState(false);
  const [converting, setConverting] = useState(null);

  async function dismiss() {
    setPending(true);
    try { await api.dismissInbox(row.id); toast("Note dismissed"); onResolved(); }
    catch (e) { toast(e.message, "err"); }
    finally { setPending(false); }
  }

  return (
    <div className="proposal-decision">
      <div className="rowmeta">
        Your own note. It has no source citation and no proposed target, so it converts into a
        record or it goes away — it is never “accepted”.
      </div>
      <div className="proposal-commands-row">
        <button type="button" className="btn small primary" disabled={pending}
          onClick={() => setConverting({
            ...row.raw,
            raw_text: row.title,
            interaction: { account_id: accountId, program_id: programId || null },
          })}>
          Convert to a record
        </button>
        <button type="button" className="btn small ghost" disabled={pending} onClick={dismiss}>
          Dismiss
        </button>
      </div>
      {converting && (
        <ConvertPanel item={converting} onClose={() => setConverting(null)}
          onConverted={() => { setConverting(null); onResolved(); }} />
      )}
    </div>
  );
}

/**
 * §14.5's review list. `programId` may be empty: account-scoped proposals still apply, and the
 * program-scoped ones say what they are waiting for instead of failing at the server.
 */
export default function ProposalReview({
  accountId, programId = "", sourceInteractionId = "", runId = "", onProgramChange = null,
  reloadKey = 0, onApplied = null,
}) {
  const toast = useToast();
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [detail, setDetail] = useState(null);
  const [openKey, setOpenKey] = useState(null);
  const [sel, setSel] = useState(0);
  const [tick, setTick] = useState(0);
  const [bulkPending, setBulkPending] = useState(false);
  const scopeKey = `${accountId}|${programId}|${sourceInteractionId}|${runId}`;
  const lastScope = useRef(scopeKey);
  const track = useMeasure({ accountId, programId: programId || null });

  useEffect(() => {
    let live = true;
    // Only a change of scope blanks the list. A refetch after a decision keeps the rows on screen:
    // dropping to a spinner between every accept is how a queue stops feeling like a queue.
    if (lastScope.current !== scopeKey) { setPayload(null); lastScope.current = scopeKey; }
    setError(null);
    api.proposedUpdates(accountId, { programId: programId || "", sourceInteractionId, runId })
      .then((r) => { if (live) setPayload(r); })
      .catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [scopeKey, accountId, programId, sourceInteractionId, runId, reloadKey, tick]);

  useEffect(() => {
    let live = true;
    api.account(accountId).then((d) => { if (live) setDetail(d); }).catch(() => {});
    return () => { live = false; };
  }, [accountId]);

  const rows = useMemo(() => combinedReviewRows(payload), [payload]);
  // Supersede only ever offers proposals from the same run: one drafted from different material is
  // not a replacement for this one.
  const runProposals = useMemo(() => {
    const byRun = {};
    for (const g of payload?.groups || []) {
      byRun[g.source.run_id] = (g.targets || []).flatMap((t) => t.proposals || []);
    }
    return byRun;
  }, [payload]);

  /**
   * §11.4 — accept-all is offered only when the whole visible list is **one run**.
   *
   * That is what makes "Accept all 6" a statement the operator can check against what is on the
   * screen. A batch that spanned two sources would apply drafts from material they may not have
   * looked at, and a key that did that is the one thing D-208 has to avoid while still being one
   * keystroke.
   */
  const soleRun = useMemo(() => {
    const groups = payload?.groups || [];
    return groups.length === 1 ? groups[0] : null;
  }, [payload]);
  const bulk = useMemo(() => acceptAllState(
    (soleRun?.targets || []).flatMap((t) => t.proposals || []),
    { programId, pending: bulkPending },
  ), [soleRun, programId, bulkPending]);

  async function acceptAll() {
    if (!soleRun || !bulk.enabled) return;
    setBulkPending(true);
    try {
      const r = await api.acceptAllInRun(soleRun.source.run_id);
      // One `proposal_accepted` per applied item, flagged `bulk`. A separate event would leave the
      // acceptance funnel undercounting by however much this path is used (§17.3). The pair is read
      // off the proposal that was applied, so the two paths report the same two properties.
      const byId = Object.fromEntries(
        (soleRun.targets || []).flatMap((t) => t.proposals || []).map((p) => [p.id, p]));
      for (const one of r.results || []) {
        const p = byId[one.proposal_id] || {};
        track?.("proposal_accepted", {
          intent: p.intent || null, target_type: p.target_type || null,
          // `edited` is the measured fact — a batch applies exactly what was drafted, always.
          edited: false, bulk: true,
        });
      }
      toast(r.complete
        ? `Applied ${r.accepted} update${r.accepted === 1 ? "" : "s"}`
        : `Applied ${r.accepted}, then stopped — the rest need a decision of their own`,
        r.complete ? undefined : "err");
      setOpenKey(null); setTick((n) => n + 1); onApplied?.();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      setBulkPending(false);
    }
  }

  // j/k move, Enter opens the decision. Accepting *one* proposal is deliberately not a bare
  // keystroke here: it needs the required fields, the possible matches, and the conflict in view
  // first. `a` is the run-scoped batch (§11.4, D-208) and only fires when every guard has already
  // passed — it is one listener, not a second window-level handler.
  useEffect(() => {
    const onKey = (ev) => {
      const t = ev.target.tagName;
      if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
      if (ev.key === "a" && bulk.enabled) { acceptAll(); ev.preventDefault(); return; }
      if (!rows.length) return;
      if (ev.key === "j" || ev.key === "ArrowDown") {
        setSel((s) => Math.min(rows.length - 1, s + 1)); ev.preventDefault();
      } else if (ev.key === "k" || ev.key === "ArrowUp") {
        setSel((s) => Math.max(0, s - 1)); ev.preventDefault();
      } else if (ev.key === "Enter") {
        const row = rows[sel];
        if (!row) return;
        const key = `${row.kind}:${row.id}`;
        setOpenKey((k) => (k === key ? null : key));
        ev.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sel, bulk.enabled, soleRun]);

  // §17.3 `proposal_review_opened`, once per scope rather than once per refetch: the list stays on
  // screen between decisions on purpose, and counting each refetch as an opening would make the
  // review look busier than it was.
  const openedRef = useRef(null);
  useEffect(() => {
    if (!payload || openedRef.current === scopeKey) return;
    openedRef.current = scopeKey;
    const proposals = (payload.groups || [])
      .flatMap((g) => (g.targets || []).flatMap((t) => t.proposals || []));
    // Intent and target type stay separate, and a mixed list reports neither rather than picking
    // one — a review of five different kinds is not a review of whichever came first.
    const single = (key) => {
      const values = new Set(proposals.map((p) => p[key]).filter(Boolean));
      return values.size === 1 ? [...values][0] : null;
    };
    const statuses = new Set((payload.groups || []).map((g) => g.source?.run_status).filter(Boolean));
    track("proposal_review_opened", {
      intent: single("intent"), target_type: single("target_type"),
      proposal_count: proposals.length,
      run_status: statuses.size === 1 ? [...statuses][0] : statuses.size > 1 ? "mixed" : null,
    });
  }, [payload, scopeKey, track]);

  const afterResolve = () => { setOpenKey(null); setTick((n) => n + 1); onApplied?.(); };
  const people = detail?.people ?? [];
  const programs = detail?.programs ?? [];

  if (error) return <div className="callout warn">Proposals unavailable: {error}</div>;
  if (!payload) return <Loading what="proposed updates" />;

  return (
    <div className="proposal-review">
      <div className="rowmeta">
        {payload.counts.proposals} proposed update(s) and {payload.counts.manual_capture} of your
        own notes, in one list. They are separate records with separate commands — accept or
        resolve a proposal, convert or dismiss a note. j/k move · Enter opens a decision
        {bulk.count > 0 && " · a applies all of this source's drafts"}.
      </div>

      {payload.scope?.note && (
        // §11.4 / D-160. The narrowed view is complete for what it was asked, and it still says
        // what it is not showing. The sentence is the server's, verbatim — a view that composed
        // part of an "I did not show you this" statement is a view that could soften one.
        <p className="rowmeta proposal-scope-note">{payload.scope.note}</p>
      )}

      {soleRun && bulk.count > 0 && (
        <div className="proposal-bulk">
          <span className="rowmeta">
            Everything here came from {sourceLabel(soleRun.source)}.
          </span>
          <div className="spacer" />
          <button type="button" className="btn small primary" disabled={!bulk.enabled}
            aria-describedby={bulk.enabled ? undefined : "bulk-why"} onClick={acceptAll}>
            {bulk.label}
          </button>
        </div>
      )}
      {soleRun && bulk.count > 0 && !bulk.enabled && bulk.why && (
        // The reason, in text and not only in a tooltip — the same rule the per-proposal commands
        // follow. A dead button with no explanation reads as a broken app.
        <div className="rowmeta proposal-why" id="bulk-why">{bulk.label}: {bulk.why}</div>
      )}

      {onProgramChange && (
        <div className="field proposal-scope">
          <label htmlFor="proposal-program">Program</label>
          <select id="proposal-program" value={programId || ""}
            onChange={(e) => onProgramChange(e.target.value)}>
            <option value="">— all programs —</option>
            {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div className="hint">Program-scoped proposals need one chosen before they can apply.</div>
        </div>
      )}

      {rows.length === 0 ? (
        <Empty title="Nothing waiting">
          No proposed updates and no untriaged notes in this scope.
        </Empty>
      ) : (
        <div className="proposal-list">
          {rows.map((row, i) => {
            const key = `${row.kind}:${row.id}`;
            const open = openKey === key;
            const outcome = row.kind === "extraction_proposal" ? outcomeLine(row.raw) : null;
            return (
              <div key={key} className={"proposal-row" + (i === sel ? " selected" : "")}
                onClick={() => setSel(i)}>
                <div className="proposal-row-head">
                  <strong>{row.title}</strong>
                  <div className="spacer" />
                  <span className="rowmeta">{row.statusLabel}</span>
                  <button type="button" className="readiness-more" aria-expanded={open}
                    onClick={() => setOpenKey(open ? null : key)}>
                    {open ? "Close" : "Review"}
                  </button>
                </div>
                {row.span && <blockquote className="proposal-span">“{row.span}”</blockquote>}
                <div className="rowmeta">
                  {row.kind === "extraction_proposal" ? sourceLabel(row.source) : "Your capture note"}
                </div>
                <Marks marks={row.marks} />
                {outcome && <div className="rowmeta">{outcome}</div>}
                {open && row.kind === "extraction_proposal" && (
                  <ProposalDecision proposal={row.raw} source={row.source}
                    runProposals={runProposals[row.raw.run_id] || []}
                    programId={programId || row.raw.program_id || ""}
                    people={people} onResolved={afterResolve} track={track} />
                )}
                {open && row.kind === "capture_item" && (
                  <CaptureDecision row={row} accountId={accountId} programId={programId}
                    onResolved={afterResolve} />
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="rowmeta readiness-foot">
        Nothing is applied until someone here applies it. Every command runs the same audited path
        a hand-typed record does.
      </div>
    </div>
  );
}
