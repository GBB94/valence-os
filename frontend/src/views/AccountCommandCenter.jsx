import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import {
  Badge, Card, Empty, Loading, SegTabs, SlideOver, AgeChip, DueChip, fmtDate, useToast,
} from "../ui";
import {
  readLastVisit, resolveCommandCenterLens, writeLastVisit, writePreferredLens,
} from "../accountCommandCenter";
import MeetingPrepare from "./MeetingPrepare";

const LENSES = [
  ["operate", "Operate"],
  ["prepare", "Prepare"],
  ["leadership", "Leadership"],
];
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

function AttentionRows({ items, onOpenTarget }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) {
    return <Empty title="No immediate action">Nothing overdue, blocked, or due within seven days.</Empty>;
  }
  const visible = expanded ? items : items.slice(0, 5);
  return (
    <div className="command-rows">
      {visible.map((item) => (
        <article className={`command-row attention-${item.band}`} key={item.id}>
          <span className={`state-mark ${item.band === "now" ? "risk" : "warn"}`} aria-hidden="true" />
          <div className="command-row-body">
            <div className="actions command-row-title">
              <strong>{item.title}</strong>
              <Badge>{sentence(item.kind)}</Badge>
            </div>
            <div className="subtle">{item.reason}{item.due_date ? ` · ${fmtDate(item.due_date)}` : ""}</div>
          </div>
          <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>
            Resolve
          </button>
        </article>
      ))}
      {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
      </button>}
    </div>
  );
}

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

function Section({ title, meta, action, children, className = "" }) {
  return (
    <Card className={`command-section${className ? ` ${className}` : ""}`}>
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

function OperateLens({ data, firstVisit, reviewing, onMarkReviewed, onOpenTarget }) {
  const checkpoint = data.cursors.program || data.cursors.account;
  const reviewMeta = checkpoint
    ? `Reviewed through ${whenLabel(checkpoint.reviewed_through)}`
    : `No review checkpoint · showing changes recorded since ${fmtDate(data.cursors.initial_window_start)}`;
  return (
    <div className="command-grid">
      <div className="command-main stack">
        <Section
          title="Since last review"
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
        <Section title="Needs action" meta="Deterministic rules · overdue, blocked, or due within seven days">
          <AttentionRows items={data.attention} onOpenTarget={onOpenTarget} />
        </Section>
        <Section title="Since last visit" meta={firstVisit ? "First visit in this browser" : "This browser and selected scope"}>
          <ActivityRows items={data.changes_since_visit} emptyTitle={firstVisit ? "Visit baseline set" : "Nothing new since your last visit"}
            emptyBody={firstVisit ? "New material changes will appear here on your next visit." : "The review cursor is separate; this only tracks browser visits."}
            onOpenTarget={onOpenTarget} />
        </Section>
      </div>
      <aside className="command-side stack">
        <Section title="Next on account" meta="Confirmed future events">
          <UpcomingRows items={data.upcoming} onOpenTarget={onOpenTarget} />
        </Section>
        <Section title="Current point of view" meta={data.operator_view ? `Assessed ${fmtDate(data.operator_view.assessed_on)}` : "Operator-authored"}>
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
      </aside>
    </div>
  );
}

function LeadershipLens({ data, onOpenTarget, onOpenCopilot }) {
  return (
    <div className="leadership-grid">
      <Section title="What moved" meta="Material changes since review">
        <ActivityRows items={data.changes_since_review} emptyTitle="No material movement"
          emptyBody="The reviewed position remains current." onOpenTarget={onOpenTarget} />
      </Section>
      <Section title="What is stuck" meta="Blockers and near-term exposure">
        <AttentionRows items={data.attention} onOpenTarget={onOpenTarget} />
      </Section>
      <Section title="What I need" meta="Leadership-ready follow-through">
        <div className="command-pov">
          {data.operator_view?.body
            ? <p>{data.operator_view.body}</p>
            : <p className="subtle">No operator point of view is recorded yet.</p>}
          <div className="actions">
            <button className="btn small" onClick={() => onOpenTarget({ tab: "internal" })}>Open internal asks</button>
            {onOpenCopilot && <button className="btn small ghost" onClick={() => onOpenCopilot("draft", "Draft a concise leadership update for this account")}>Draft update</button>}
          </div>
        </div>
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
      writeLastVisit(window.localStorage, accountId, programId, result.stamp.data_current_through);
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
  return (
    <div className="command-center">
      <header className="command-center-head">
        <div>
          <h1>{data.account.name}</h1>
          <div className="subtle">{data.account.short_context || "Account operating command center"}</div>
        </div>
        <div className="spacer" />
        <div className="actions command-head-actions">
          <span className="rowmeta">Current through {whenLabel(data.stamp.data_current_through)}</span>
          <button className="btn" onClick={exportAccount}>Export</button>
          <button className="btn" onClick={() => setAddingProgram(true)}>New program</button>
          <button className="btn primary" onClick={() => onQuickEntry(accountId)}>Log interaction</button>
        </div>
      </header>

      <SegTabs id="command-center-lenses" panelId="command-center-panel" ariaLabel="Command center focus"
        tabs={LENSES} value={activeLens} onChange={changeLens} />

      {omitted.length > 0 && <div className="callout warn command-coverage" role="status">
        Partial coverage: {omitted.map(sentence).join(", ")} could not be read. Other sections remain current through {whenLabel(data.stamp.data_current_through)}.
      </div>}

      <div id="command-center-panel" role="tabpanel" aria-labelledby={`command-center-lenses-${activeLens}-tab`}
        className="command-panel">
        {activeLens === "operate" && <OperateLens data={data} firstVisit={!priorVisit} reviewing={reviewing}
          onMarkReviewed={markReviewed} onOpenTarget={onOpenTarget} />}
        {activeLens === "prepare" && <MeetingPrepare accountId={accountId} programId={programId}
          meetingId={meetingId} onMeetingChange={onMeetingChange} onOpenTarget={onOpenTarget}
          onQuickEntry={onQuickEntry} onOpenCopilot={onOpenCopilot} />}
        {activeLens === "leadership" && <LeadershipLens data={data} onOpenTarget={onOpenTarget} onOpenCopilot={onOpenCopilot} />}
      </div>

      {addingProgram && <NewProgram accountId={accountId} onClose={() => setAddingProgram(false)} onCreated={onSaved} />}
    </div>
  );
}
