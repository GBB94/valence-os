import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import {
  AgeChip, Badge, Card, DueChip, Empty, Loading, SlideOver, StanceLabel, fmtDate, useToast,
} from "../ui";

function words(value) {
  return String(value || "").replaceAll("_", " ");
}

function meetingTime(value) {
  if (!value) return "Not recorded";
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }).format(instant);
}

function ActivityContext({ items, window, onOpenTarget }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) {
    return <Empty title="No attendee-linked changes found">
      {window?.basis || "Resolve an attendee to assemble attendee-specific context."}
    </Empty>;
  }
  const visible = expanded ? items : items.slice(0, 5);
  return <div className="command-rows">
    {visible.map((item) => <article className="command-row" key={item.id}>
      <div className="command-row-time"><AgeChip date={item.display_at} /></div>
      <div className="command-row-body">
        <div className="actions command-row-title">
          <strong>{item.title}</strong><Badge>{words(item.stream)}</Badge>
        </div>
        {item.summary && <div className="subtle">{item.summary}</div>}
        <div className="rowmeta">{item.reason} · recorded {meetingTime(item.recorded_at)}</div>
      </div>
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button>
    </article>)}
    {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
      {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
    </button>}
  </div>;
}

function PublicContext({ items, onOpenTarget }) {
  if (!items?.length) return <Empty title="No active public context linked">
    Confirmed company events appear here only when they are linked to this account or a resolved attendee.
  </Empty>;
  return <div className="command-rows">
    {items.map((item) => <article className="command-row" key={item.id}>
      <div className="command-row-time"><AgeChip date={item.occurred_on} /></div>
      <div className="command-row-body">
        <div className="actions command-row-title"><strong>{item.title}</strong>
          <Badge>{words(item.direction)}</Badge><Badge>{item.source_count} source{item.source_count === 1 ? "" : "s"}</Badge></div>
        <div className="subtle">{item.summary}</div>
        <div className="rowmeta">{item.relevance}</div>
        <div className="prepare-public-sources">{item.evidence.map((source) => <a key={source.span_id}
          href={source.url} target="_blank" rel="noreferrer">
          {source.publisher} · {source.locator}
        </a>)}</div>
      </div>
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Inspect</button>
    </article>)}
  </div>;
}

function ThreadRows({ items, onOpenTarget }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) return <Empty title="No open threads">No attendee-related or scoped blockers, commitments, asks, or follow-ups are open.</Empty>;
  const visible = expanded ? items : items.slice(0, 5);
  return <div className="command-rows">
    {visible.map((item) => <article className="command-row" key={item.id}>
      <span className={`state-mark ${["risk", "issue"].includes(item.kind) ? "risk" : "warn"}`} aria-hidden="true" />
      <div className="command-row-body">
        <div className="actions command-row-title"><strong>{item.title}</strong><Badge>{words(item.kind)}</Badge></div>
        <div className="actions"><span className="subtle">{item.detail}</span>{item.due_date && <DueChip date={item.due_date} />}</div>
      </div>
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button>
    </article>)}
    {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
      {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
    </button>}
  </div>;
}

function EvidenceGaps({ items, onOpenTarget }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) return <Empty title="No named evidence gaps">The required meeting and attendee context is recorded and current.</Empty>;
  const visible = expanded ? items : items.slice(0, 5);
  return <div className="prepare-gaps">
    {visible.map((gap, index) => <article className="prepare-gap" key={`${gap.kind}-${index}`}>
      <span className="unknown-hatch" aria-hidden="true" />
      <div><strong>{gap.title}</strong><div className="rowmeta">{gap.detail}</div></div>
      {gap.native_target && <button className="btn small ghost" onClick={() => onOpenTarget(gap.native_target)}>Resolve</button>}
    </article>)}
    {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
      {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
    </button>}
  </div>;
}

function Attendees({ items, onOpenTarget }) {
  if (!items?.length) return <Empty title="No invitees recorded">Add or associate attendees on the calendar event before preparing person context.</Empty>;
  return <div className="prepare-table-wrap"><table>
    <thead><tr>
      <th scope="col">Attendee</th><th scope="col">Role and stance</th>
      <th scope="col">Last meaningful touch</th><th scope="col">Response</th><th scope="col" aria-label="Actions" />
    </tr></thead>
    <tbody>{items.map((item) => <tr key={item.key}>
      <td>
        <strong>{item.name || item.email || "Unknown invitee"}</strong>
        <div className="rowmeta">{item.title || item.email || "No identity details"}</div>
        {item.association_state === "unknown" && <Badge>unresolved</Badge>}
      </td>
      <td>{item.role ? <>
        <div>{words(item.role.effective_role)} · {words(item.role.layer)}</div>
        <div className="actions prepare-stance"><StanceLabel stance={item.role.stance} />
          <AgeChip date={item.role.stance_assessed_on} /></div>
        {/* An assessment travels with its basis, never the judgment alone (CLAUDE.md §2). */}
        {item.role.stance && (item.role.stance_evidence_note
          ? <div className="rowmeta">Because {item.role.stance_evidence_note}</div>
          : <div className="rowmeta"><span className="unknown-fill">Evidence note not recorded</span></div>)}
        {item.role.influence && <div className="rowmeta">
          Influence {item.role.influence}
          {item.role.influence_assessed_on
            ? <> as of {fmtDate(item.role.influence_assessed_on)}
                {item.role.influence_evidence_note ? ` — ${item.role.influence_evidence_note}` : ""}</>
            : <> · <span className="unknown-fill">not dated</span></>}
        </div>}
        {item.role.cares_about && <div className="rowmeta">Cares about {item.role.cares_about}</div>}
      </> : <span className="unknown-fill">Not recorded</span>}</td>
      <td>{item.last_meaningful_touch ? <>
        <AgeChip date={item.last_meaningful_touch.occurred_on} />
        <div className="rowmeta">{item.last_meaningful_touch.summary || words(item.last_meaningful_touch.type)}</div>
      </> : <span className="unknown-fill">No meaningful touch</span>}</td>
      <td><Badge>{words(item.response_status)}</Badge></td>
      <td className="actions-cell">{item.native_target && <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button>}</td>
    </tr>)}</tbody>
  </table></div>;
}

function BriefPreview({ brief, onClose }) {
  return <SlideOver title="Pre-call brief preview" onClose={onClose} footer={
    <button className="btn" onClick={onClose}>Close preview</button>
  }>
    <div className="callout">Internal preparation · deterministic native records · nothing was saved or sent.</div>
    {!!brief.stamp?.missing_or_stale_sources?.length && <div className="callout warn prepare-preview-section">
      <strong>Known gaps</strong><ul>{brief.stamp.missing_or_stale_sources.map((gap) => <li key={gap}>{gap}</li>)}</ul>
    </div>}
    <section className="prepare-preview-section"><h2>Who is in the room</h2>
      {brief.attendees?.map((item) => <Card className="prepare-preview-person" key={item.person_id}>
        <strong>{item.name}</strong>{item.title && <span className="subtle"> · {item.title}</span>}
        <div className="rowmeta">{words(item.role) || "Role not recorded"}{item.stance ? ` · ${item.stance} as of ${fmtDate(item.stance_assessed_on)}` : ""}</div>
        {item.cares_about && <div>Cares about: {item.cares_about}</div>}
      </Card>)}
    </section>
    <section className="prepare-preview-section"><h2>Live risks</h2>
      {brief.live_risks?.length ? <ul>{brief.live_risks.map((item, index) => <li key={index}>{item.description} · {item.severity}{item.is_blocker ? " · blocker" : ""}</li>)}</ul> : <div className="rowmeta">None recorded.</div>}
    </section>
    <section className="prepare-preview-section"><h2>Public context</h2>
      {brief.public_context?.length ? brief.public_context.map((item) => <article key={item.id} className="prepare-preview-public">
        <strong>{item.summary}</strong><div className="rowmeta">{item.relevance} · {fmtDate(item.occurred_on)}</div>
        <div className="prepare-public-sources">{item.evidence.map((source) => <a key={source.span_id}
          href={source.url} target="_blank" rel="noreferrer">{source.publisher} · {source.locator}</a>)}</div>
      </article>) : <div className="rowmeta">No confirmed, active account- or attendee-linked public context.</div>}
    </section>
    <section className="prepare-preview-section"><h2>Open gates and follow-up</h2>
      {brief.gate_items_due?.map((item, index) => <div key={index}>{item.description} · <span className="rowmeta">{item.gate}</span></div>)}
      {brief.unanswered_email?.map((item, index) => <div key={index}>{item.subject} · <span className="rowmeta">{item.reason}</span></div>)}
      {!brief.gate_items_due?.length && !brief.unanswered_email?.length && <div className="rowmeta">None recorded.</div>}
    </section>
    <section className="prepare-preview-section"><h2>Suggested talking points</h2>
      {brief.talking_points?.length ? <ul>{brief.talking_points.map((item, index) => <li key={index}>{item.point}</li>)}</ul> : <div className="rowmeta">None generated.</div>}
    </section>
  </SlideOver>;
}

export default function MeetingPrepare({
  accountId, programId, meetingId, onMeetingChange, onOpenTarget, onQuickEntry, onOpenCopilot,
}) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [brief, setBrief] = useState(null);
  const [briefing, setBriefing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const result = await api.meetingPrep(accountId, { programId, meetingId });
      setData(result);
      if (!meetingId && result.selected_meeting?.id) {
        onMeetingChange(result.selected_meeting.id, { replace: true });
      }
    } catch (loadError) {
      if (loadError.status === 422 && meetingId) {
        onMeetingChange("", { replace: true });
        return;
      }
      setError(loadError.message);
      setData(null);
    }
  }, [accountId, programId, meetingId, onMeetingChange]);

  useEffect(() => { load(); }, [load]);

  async function previewBrief() {
    if (!data?.selected_meeting || !data.brief_person_ids?.length) return;
    setBriefing(true);
    try {
      setBrief(await api.meetingBrief(accountId, {
        programId: data.selected_meeting.program_id || programId,
        personIds: data.brief_person_ids,
      }));
    } catch (previewError) {
      toast(previewError.message, "err");
    } finally {
      setBriefing(false);
    }
  }

  if (!data && !error) return <Loading what="meeting preparation" />;
  if (error) return <Card className="command-load-error"><Empty title="Meeting preparation unavailable">{error}</Empty>
    <button className="btn" onClick={load}>Retry</button></Card>;

  const meeting = data.selected_meeting;
  return <div className="prepare-workflow stack">
    <Card className="prepare-selector">
      <div className="card-h"><div><h3>Meeting focus</h3><div className="rowmeta">Upcoming and recently completed associated meetings</div></div>
        <div className="spacer" />
        <select aria-label="Meeting to prepare" value={meeting?.id || ""}
          onChange={(event) => onMeetingChange(event.target.value)}>
          {!meeting && <option value="">No meeting selected</option>}
          {data.meetings.map((item) => <option key={item.id} value={item.id}>
            {item.timing === "upcoming" ? "Upcoming" : "Recent"} · {item.title} · {meetingTime(item.starts_at)}
          </option>)}
        </select>
      </div>
      {!meeting ? <Empty title="No associated meeting">Open Plan to create or associate a calendar event.</Empty> : <>
        <div className="prepare-identity">
          <div><div className="ctx-k">Meeting</div><strong>{meeting.title}</strong></div>
          <div><div className="ctx-k">When</div><span className="mono">{meetingTime(meeting.starts_at)}</span>{meeting.ends_at && <div className="rowmeta">to {meetingTime(meeting.ends_at)}</div>}</div>
          <div><div className="ctx-k">Purpose</div>{words(meeting.purpose)}</div>
          <div><div className="ctx-k">Program</div>{meeting.program_name || "Account-level"}</div>
          <div><div className="ctx-k">Location</div>{meeting.location || <span className="unknown-fill">Not recorded</span>}</div>
          <div><div className="ctx-k">Organizer</div>{meeting.organizer_email || <span className="unknown-fill">Not recorded</span>}</div>
          {/* DESIGN-GUIDE §8: a numeric confidence badge is prohibited. The underlying value is
              a recorded boolean, so it reads as a word. */}
          <div><div className="ctx-k">Association</div>{meeting.association_confidence == null
            ? <span className="unknown-fill">Not recorded</span>
            : meeting.association_confidence >= 1
              ? <span>Confirmed</span>
              : <span>Not fully confirmed</span>}</div>
        </div>
        <div className="prepare-actions">
          <button className="btn primary" onClick={() => onQuickEntry(accountId)}>Log interaction</button>
          <button className="btn" disabled={briefing || !data.brief_person_ids.length} onClick={previewBrief}
            title={!data.brief_person_ids.length ? "Resolve at least one attendee with an in-scope stakeholder role" : undefined}>
            {briefing ? "Assembling…" : "Preview pre-call brief"}
          </button>
          {onOpenCopilot && <button className="btn" onClick={() => onOpenCopilot("synthesis",
            `Prepare me for ${meeting.title} on ${meeting.starts_at}. Focus on the recorded attendees, open threads, and evidence gaps.`)}>
            Ask Copilot
          </button>}
          <button className="btn ghost" onClick={() => onOpenTarget(meeting.native_target)}>Open calendar record</button>
          {meeting.source_reference?.url && <a className="btn ghost prepare-source-link" href={meeting.source_reference.url}
            target="_blank" rel="noreferrer">Open source</a>}
          <span className="rowmeta">Nothing runs automatically.</span>
        </div>
      </>}
    </Card>

    {meeting && <>
      <Card><div className="card-h"><div><h3>Attendees</h3><div className="rowmeta">Known people are resolved from canonical records; unknown invitees stay unknown</div></div></div>
        <Attendees items={data.attendees} onOpenTarget={onOpenTarget} /></Card>
      <div className="command-grid">
        <div className="command-main stack">
          <Card><div className="card-h"><div><h3>What changed since the last meaningful touch</h3>
            <div className="rowmeta">{data.context_window?.starts_on ? `Since ${fmtDate(data.context_window.starts_on)} · ` : ""}{data.context_window?.basis}</div></div></div>
            {!!data.context_window?.omitted?.length && <div className="callout warn prepare-inline-callout">Partial coverage: {data.context_window.omitted.map(words).join(", ")}</div>}
            <ActivityContext items={data.recent_context} window={data.context_window} onOpenTarget={onOpenTarget} /></Card>
          <Card><div className="card-h"><div><h3>Public context for this conversation</h3>
            <div className="rowmeta">Confirmed, non-expired evidence linked to the account or a resolved attendee</div></div></div>
            <PublicContext items={data.public_context} onOpenTarget={onOpenTarget} /></Card>
          <Card><div className="card-h"><div><h3>Open threads</h3><div className="rowmeta">Attendee-linked first, followed by blockers and active account follow-through</div></div></div>
            <ThreadRows items={data.open_threads} onOpenTarget={onOpenTarget} /></Card>
        </div>
        <aside className="command-side stack">
          <Card><div className="card-h"><div><h3>Evidence gaps</h3><div className="rowmeta">Missing, stale, unresolved, or weak inputs</div></div></div>
            <EvidenceGaps items={data.evidence_gaps} onOpenTarget={onOpenTarget} /></Card>
          <div className="callout">Current through {meetingTime(data.stamp.data_current_through)}. Meeting preparation is internal-only.</div>
        </aside>
      </div>
    </>}
    {brief && <BriefPreview brief={brief} onClose={() => setBrief(null)} />}
  </div>;
}
