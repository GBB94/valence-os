import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import {
  Badge, Card, Empty, Loading, SegTabs, SlideOver, AgeChip, DueChip, fmtDate, useToast,
} from "../ui";
import {
  readLastVisit, resolveCommandCenterLens, writeLastVisit, writePreferredLens,
} from "../accountCommandCenter";
import AccountIntakeDrop from "./AccountIntakeDrop";
import AccountPath from "./AccountPath";
import LeadershipReview from "./LeadershipReview";
import MeetingPrepare from "./MeetingPrepare";
import ProposalPreview from "./ProposalPreview";
import { ReadinessSummary } from "./Readiness";

const LENSES = [
  ["operate", "Operate"],
  ["prepare", "Prepare"],
  ["leadership", "Leadership"],
];
const LENS_COPY = {
  operate: ["Daily operating view", "Changes, actions, and the next account moment"],
  prepare: ["Meeting preparation", "People, open threads, and evidence for the conversation"],
  leadership: ["Leadership review", "Movement, exposure, forecast, and explicit asks"],
};
const PROGRAM_PHASES = ["foundation", "launch", "programmatic", "expansion", "renewal", "closed"];

function sentence(value) {
  return String(value || "").replaceAll("_", " ");
}

function whenLabel(value) {
  if (!value) return "No date";
  return value.includes("T") ? value.slice(0, 16).replace("T", " · ") : fmtDate(value);
}

function ActivityRows({ items, emptyTitle, emptyBody, onOpenTarget }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) return <Empty title={emptyTitle}>{emptyBody}</Empty>;
  const visible = expanded ? items : items.slice(0, 5);
  return (
    <div className="command-rows">
      {visible.map((item) => (
        <article className="command-row" key={item.id}>
          <div className="command-row-time">{item.direction === "future"
            ? <DueChip date={item.display_at} /> : <AgeChip date={item.display_at} />}</div>
          <div className="command-row-body">
            <div className="actions command-row-title">
              <strong>{item.title}</strong>
              <Badge>{sentence(item.stream)}</Badge>
              <Badge>{sentence(item.state)}</Badge>
              {item.status && <span className="rowmeta">{sentence(item.status)}</span>}
            </div>
            {item.summary && <div className="subtle">{item.summary}</div>}
            <div className="rowmeta">{sentence(item.temporal_kind)} {whenLabel(item.display_at)} · {item.reason} · recorded {whenLabel(item.recorded_at)}</div>
          </div>
          <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>
            Open
          </button>
        </article>
      ))}
      {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
      </button>}
    </div>
  );
}

// The old "Needs action" list is gone, not moved. It ranked the same overdue/blocked/due-soon work
// that Next best move and You own now rank from the Execution Path, and keeping both would put two
// competing orderings of one set of records on one screen (ACCOUNT-PATH-SPEC.md §3, §7.3).

function UpcomingRows({ items, onOpenTarget }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) return <Empty title="Nothing scheduled">No confirmed upcoming account events are recorded.</Empty>;
  const visible = expanded ? items : items.slice(0, 5);
  return (
    <div className="command-rows">
      {visible.map((item) => (
        <article className="command-row" key={item.id}>
          <div className="command-date">{whenLabel(item.display_at)}</div>
          <div className="command-row-body">
            <strong>{item.title}</strong>
            {item.summary && <div className="subtle">{item.summary}</div>}
            <div className="rowmeta">{item.reason}</div>
          </div>
          <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button>
        </article>
      ))}
      {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
      </button>}
    </div>
  );
}

function Section({ title, meta, action, children, className = "", tone = "neutral" }) {
  return (
    <Card spotlight className={`command-section command-tone-${tone}${className ? ` ${className}` : ""}`}>
      <div className="card-h">
        <div>
          <h3>{title}</h3>
          {meta && <div className="rowmeta command-section-meta">{meta}</div>}
        </div>
        <div className="spacer" />
        {action}
      </div>
      {children}
    </Card>
  );
}

/**
 * ACCOUNT-PATH-SPEC.md §5.2 order: Next best move and the Account Path lead, the execution groups
 * follow, and the existing activity sections keep their semantics but move below them. Account
 * Path loads separately (§11.2) so a failure there leaves the activity sections usable, and the
 * review checkpoint, point of view, and visit cursor behave exactly as before.
 */
function OperateLens({ data, firstVisit, reviewing, accountId, programId, reloadKey,
                      onMarkReviewed, onOpenTarget, onSaved }) {
  const checkpoint = data.cursors.program || data.cursors.account;
  const reviewMeta = checkpoint
    ? `Reviewed through ${whenLabel(checkpoint.reviewed_through)}`
    : `No review checkpoint · showing changes recorded since ${fmtDate(data.cursors.initial_window_start)}`;

  /**
   * ACCOUNT-INTAKE-SPEC.md §3.1. Full width in the main column, directly above "Since last
   * review" — the two belong together, because this is where new information enters and that is
   * where recorded information appears.
   *
   * It sits below the ranked work rather than above it on purpose, and the distinction is between
   * the input and its output: the *zone* is prominent, its *results* are not. Putting a file
   * target above Next best move would say the first thing to do on opening an account is to feed
   * the machine. The paste shortcut is what makes it reachable without scrolling at all.
   */
  const dropZone = (
    <AccountIntakeDrop accountId={accountId} accountName={data.account.name}
      programId={programId} reloadKey={reloadKey} onDrafted={onSaved} />
  );

  const sinceReview = (
    <Section
      title="Since last review"
      tone="accent"
      meta={reviewMeta}
      action={<button className="btn small" disabled={reviewing} onClick={onMarkReviewed}
        aria-label={`Mark changes reviewed through ${data.stamp.data_current_through}`}>
        {reviewing ? "Marking…" : "Mark reviewed"}
      </button>}
    >
      <ActivityRows items={data.changes_since_review} emptyTitle="You are caught up"
        emptyBody="No material confirmed changes have been recorded since this scope was reviewed."
        onOpenTarget={onOpenTarget} />
    </Section>
  );

  const sideExtras = (
    <>
      {/* Compact readiness: only the gaps this phase actually requires. The full pillar set and
          its evidence live behind the row, so Operate stays a prompt rather than a scorecard
          (RELATIONSHIP-READINESS-SPEC.md §8.2). It follows the scope selector — a program in
          scope is evaluated on its own evidence and never merged with its siblings. It keeps
          fetching its own data and reporting its own coverage: readiness coverage and execution
          coverage are different claims and must not be merged into one notice. */}
      <ReadinessSummary accountId={accountId} programId={programId} mode="compact"
        reloadKey={reloadKey} onOpenTarget={onOpenTarget} />
      {/* Up to three proposals from the newest source, plus a way to the full list
          (RELATIONSHIP-READINESS-SPEC.md §8.1). It sits below readiness on purpose: a draft
          nobody has accepted is not an account condition, and it must not read like one. */}
      <ProposalPreview accountId={accountId} programId={programId} reloadKey={reloadKey}
        onApplied={onSaved} />
      <Section title="Next on account" tone="accent" meta="Confirmed future events">
        <UpcomingRows items={data.upcoming} onOpenTarget={onOpenTarget} />
      </Section>
      <Section title="Current point of view" tone="quiet" meta={data.operator_view ? `Assessed ${fmtDate(data.operator_view.assessed_on)}` : "Operator-authored"}>
        {data.operator_view ? (
          <div className="command-pov">
            <p>{data.operator_view.body}</p>
            <div className="rowmeta">{data.operator_view.author}</div>
            <button className="btn small ghost" onClick={() => onOpenTarget({ tab: "internal" })}>Open review record</button>
          </div>
        ) : (
          <Empty title="No point of view yet">Record a dated operator view in Internal before the next review.</Empty>
        )}
      </Section>
    </>
  );

  return (
    <div className="stack operate-stack">
      <AccountPath accountId={accountId} programId={programId} reloadKey={reloadKey}
        onOpenTarget={onOpenTarget} onSaved={onSaved}
        mainSlot={<>{dropZone}{sinceReview}</>} sideSlot={sideExtras} />
      {/* Retained and deliberately subordinate (§5.2 item 10): a personal recency band, not a
          statement about the account. */}
      <Section title="Since last visit" tone="quiet" meta={firstVisit ? "First visit in this browser" : "This browser and selected scope"}>
        <ActivityRows items={data.changes_since_visit} emptyTitle={firstVisit ? "Visit baseline set" : "Nothing new since your last visit"}
          emptyBody={firstVisit ? "New material changes will appear here on your next visit." : "The review cursor is separate; this only tracks browser visits."}
          onOpenTarget={onOpenTarget} />
      </Section>
    </div>
  );
}

function NewProgram({ accountId, onClose, onCreated }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [phase, setPhase] = useState("foundation");
  const [saving, setSaving] = useState(false);
  async function save() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await api.createProgram({ account_id: accountId, name: name.trim(), phase });
      toast("Program created");
      onCreated();
      onClose();
    } catch (error) {
      toast(error.message, "err");
    } finally {
      setSaving(false);
    }
  }
  return (
    <SlideOver title="New program" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={saving || !name.trim()} onClick={save}>{saving ? "Creating…" : "Create program"}</button>
    </>}>
      <div className="field"><label>Name <span className="req">*</span></label>
        <input value={name} onChange={(event) => setName(event.target.value)} autoFocus /></div>
      <div className="field"><label>Phase</label>
        <select value={phase} onChange={(event) => setPhase(event.target.value)}>
          {PROGRAM_PHASES.map((value) => <option key={value} value={value}>{value}</option>)}
        </select></div>
    </SlideOver>
  );
}

export default function AccountCommandCenter({
  accountId, programId, lens, meetingId, reloadKey, onLensChange, onQuickEntry,
  onMeetingChange, onOpenTarget, onSaved, onOpenCopilot,
}) {
  const toast = useToast();
  const activeLens = useMemo(() => resolveCommandCenterLens(lens, window.localStorage), [lens]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [priorVisit, setPriorVisit] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  const stampedScope = useRef(null);
  const [addingProgram, setAddingProgram] = useState(false);

  useEffect(() => {
    if (lens !== activeLens) onLensChange(activeLens, { replace: true });
  }, [activeLens, lens, onLensChange]);

  const load = useCallback(async () => {
    const visit = readLastVisit(window.localStorage, accountId, programId);
    setPriorVisit(visit);
    setError(null);
    try {
      const result = await api.commandCenter(accountId, { programId, recordedAfter: visit || "" });
      setData(result);
      // The visit cursor advances once per arrival at a scope, not on every refresh. Without
      // this guard any unrelated capture (which bumps reloadKey) silently emptied "Since your
      // last visit", and marking changes reviewed advanced it as a side effect — collapsing two
      // bands the spec defines as independent.
      const scope = `${accountId}::${programId || ""}`;
      if (stampedScope.current !== scope) {
        stampedScope.current = scope;
        writeLastVisit(window.localStorage, accountId, programId, result.stamp.data_current_through);
      }
    } catch (error) {
      setError(error.message);
      setData(null);
      toast(error.message, "err");
    }
  }, [accountId, programId, toast]);

  useEffect(() => { load(); }, [load, reloadKey]);

  function changeLens(next) {
    writePreferredLens(window.localStorage, next);
    onLensChange(next);
  }

  async function markReviewed() {
    if (!data) return;
    setReviewing(true);
    try {
      await api.markAccountChangesReviewed(accountId, {
        scope_type: programId ? "program" : "account",
        program_id: programId || null,
        reviewed_through: data.stamp.data_current_through,
        source_type: "command_center",
      });
      toast(`Changes reviewed through ${whenLabel(data.stamp.data_current_through)}`);
      await load();
      onSaved?.();
    } catch (error) {
      toast(error.message, "err");
    } finally {
      setReviewing(false);
    }
  }

  async function exportAccount() {
    try {
      const bundle = await api.exportAccount(accountId);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${(data?.account?.name || "account").replace(/[^\w.-]+/g, "_")}.valence-export.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast("Account exported");
    } catch (error) {
      toast(error.message, "err");
    }
  }

  if (!data && error) return <Card className="command-load-error">
    <Empty title="Command center unavailable">{error}</Empty>
    <button className="btn" onClick={load}>Retry</button>
  </Card>;
  if (!data) return <Loading what="command center" />;
  const omitted = data.stamp.omitted || [];
  const lensCopy = LENS_COPY[activeLens];
  return (
    <div className="command-center">
      <Card as="header" spotlight className="command-center-head command-center-hero">
        <div className="command-heading-copy">
          <div className="page-eyebrow">{data.account.name} · command center</div>
          <h1>{lensCopy[0]}</h1>
          <div className="page-subtitle">{lensCopy[1]}</div>
        </div>
        <div className="spacer" />
        <div className="actions command-head-actions">
          <span className="freshness-stamp"><span>Current through</span>{whenLabel(data.stamp.data_current_through)}</span>
          <button className="btn" onClick={exportAccount}>Export</button>
          <button className="btn" onClick={() => setAddingProgram(true)}>New program</button>
          <button className="btn primary" onClick={() => onQuickEntry(accountId)}>Log interaction</button>
        </div>
      </Card>

      <div className="command-lens-dock">
        <div className="command-lens-label">
          <span>Focus lens</span>
          <small>Change the command center's operating job</small>
        </div>
        <SegTabs id="command-center-lenses" panelId="command-center-panel" ariaLabel="Command center focus"
          tabs={LENSES} value={activeLens} onChange={changeLens} />
      </div>

      {omitted.length > 0 && <div className="callout warn command-coverage" role="status">
        Partial coverage: {omitted.map(sentence).join(", ")} could not be read. Other sections remain current through {whenLabel(data.stamp.data_current_through)}.
      </div>}

      <div id="command-center-panel" role="tabpanel" aria-labelledby={`command-center-lenses-${activeLens}-tab`}
        className="command-panel">
        {activeLens === "operate" && <OperateLens data={data} firstVisit={!priorVisit} reviewing={reviewing}
          accountId={accountId} programId={programId} reloadKey={reloadKey}
          onMarkReviewed={markReviewed} onOpenTarget={onOpenTarget} onSaved={onSaved} />}
        {activeLens === "prepare" && <MeetingPrepare accountId={accountId} programId={programId}
          meetingId={meetingId} onMeetingChange={onMeetingChange} onOpenTarget={onOpenTarget}
          onQuickEntry={onQuickEntry} onOpenCopilot={onOpenCopilot} />}
        {activeLens === "leadership" && <LeadershipReview accountId={accountId} programId={programId}
          reloadKey={reloadKey} onOpenTarget={onOpenTarget} onOpenCopilot={onOpenCopilot} />}
      </div>

      {addingProgram && <NewProgram accountId={accountId} onClose={() => setAddingProgram(false)} onCreated={onSaved} />}
    </div>
  );
}
