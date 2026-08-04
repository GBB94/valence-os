import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Badge, Card, DueChip, Empty, Loading, ageDays, fmtDate } from "../ui";

function words(value) {
  return String(value || "").replaceAll("_", " ");
}

function dateTime(value) {
  if (!value) return "Not recorded";
  if (!value.includes("T")) return fmtDate(value);
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }).format(instant);
}

function money(value, currency, basis) {
  if (value == null) return "Amount not recorded";
  return `${currency || ""} ${Number(value).toLocaleString()}${basis ? ` · ${words(basis)}` : ""}`.trim();
}

function Section({ title, meta, action, children }) {
  return <Card className="command-section">
    <div className="card-h"><div><h3>{title}</h3>{meta && <div className="rowmeta command-section-meta">{meta}</div>}</div>
      <div className="spacer" />{action}</div>
    {children}
  </Card>;
}

function Expandable({ items, empty, render, className = "command-rows" }) {
  const [expanded, setExpanded] = useState(false);
  if (!items?.length) return empty;
  const visible = expanded ? items : items.slice(0, 5);
  return <div className={className}>
    {visible.map(render)}
    {items.length > 5 && <button className="command-more" onClick={() => setExpanded((value) => !value)}>
      {expanded ? "Show fewer" : `Show ${items.length - 5} more`}
    </button>}
  </div>;
}

function StatusCard({ item, onOpenTarget }) {
  const band = { on_track: "ok", at_risk: "warn", off_track: "risk", unknown: "unknown" }[item.value] || "unknown";
  // DESIGN-GUIDE §7: a manually assessed status past its 30-day reassessment interval keeps its
  // colour but gains a dotted outline, so an old judgment cannot read as current — least of all
  // on the leadership surface.
  const stale = ageDays(item.assessed_on) != null && ageDays(item.assessed_on) > 30;
  return <article className="leadership-status">
    <div className="actions"><span className={`state-mark ${band}`} aria-hidden="true" />
      <strong>{words(item.dimension)}</strong>
      <Badge className={stale ? "status-stale-outline" : undefined}>{words(item.value)}</Badge>
      {stale && <span className="rowmeta">reassess</span>}
      <span className="spacer" /><AgeChip date={item.assessed_on} /></div>
    <p>{item.rationale || "No governed rationale is recorded."}</p>
    {(item.recovery_action || item.recovery_owner || item.recovery_due_on) && <div className="leadership-recovery">
      <div><span className="ctx-k">Recovery</span>{item.recovery_action || <span className="unknown-fill">Not recorded</span>}</div>
      <div><span className="ctx-k">Owner</span>{item.recovery_owner || <span className="unknown-fill">Not recorded</span>}</div>
      <div><span className="ctx-k">Due</span>{item.recovery_due_on ? <DueChip date={item.recovery_due_on} /> : <span className="unknown-fill">Not recorded</span>}</div>
    </div>}
    {item.leadership_response && <div className="callout leadership-response">
      <strong>Leadership response</strong>
      <div>{item.leadership_response.label}</div>
      {item.leadership_response.status && <div className="rowmeta">{words(item.leadership_response.status)} · needed {fmtDate(item.leadership_response.needed_by)}</div>}
    </div>}
    <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open governed status</button>
  </article>;
}

function ForecastTable({ items, onOpenTarget }) {
  if (!items?.length) return <Empty title="No active forecast call">Create an open or locked forecast entry before leadership review.</Empty>;
  return <div className="leadership-table-wrap"><table>
    <thead><tr><th scope="col">Target</th><th scope="col">Call</th><th scope="col">Amount</th>
      <th scope="col">Evidence</th><th scope="col">Decision</th><th scope="col" aria-label="Actions" /></tr></thead>
    <tbody>{items.map((item) => <tr key={item.id}>
      <td><strong>{item.target}</strong><div className="rowmeta">{item.period.name} · {words(item.period.status)} through {fmtDate(item.period.ends_on)}</div></td>
      <td><Badge>{words(item.category)}</Badge>{item.probability != null && <div className="rowmeta">{Math.round(item.probability * 100)}% recorded</div>}</td>
      <td className="mono">{money(item.amount, item.currency, item.price_basis)}</td>
      <td>{item.evidence_supported ? <span className="band-ok">Supported</span> : <>
        <span className="band-warn">Incomplete</span><div className="rowmeta">{item.missing_evidence[0] || "Required evidence is missing"}</div></>}</td>
      <td>{item.expected_decision_date ? <DueChip date={item.expected_decision_date} /> : <span className="unknown-fill">Not recorded</span>}
        {item.help_needed_note && <div className="rowmeta">Need: {item.help_needed_note}</div>}
        {item.unresolved_conditions && <div className="rowmeta">Conditions: {item.unresolved_conditions}</div>}</td>
      <td className="actions-cell"><button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button></td>
    </tr>)}</tbody>
  </table></div>;
}

function Movement({ items, onOpenTarget }) {
  return <Expandable items={items} empty={<Empty title="No material movement">No scoped forecast transition, decision, meaningful interaction, completed milestone, closed blocker, or confirmed external change was recorded in this window.</Empty>}
    render={(item) => <article className="command-row" key={item.id}>
      <div className="command-row-time"><AgeChip date={item.display_at} /></div>
      <div className="command-row-body"><div className="actions command-row-title"><strong>{item.title}</strong>
        <Badge>{words(item.source_type)}</Badge></div>
        {item.summary && <div className="subtle">{item.summary}</div>}
        <div className="rowmeta">{item.reason} · effective {dateTime(item.display_at)} · recorded {dateTime(item.recorded_at)}</div></div>
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button>
    </article>} />;
}

function Stuck({ items, onOpenTarget }) {
  return <Expandable items={items} empty={<Empty title="Nothing named as stuck">No scoped blocker, overdue item, at-risk milestone, or required evidence gap is recorded.</Empty>}
    render={(item) => <article className="command-row" key={item.id}>
      <span className={`state-mark ${item.severity === "unknown" ? "unknown" : item.severity === "at_risk" ? "warn" : "risk"}`} aria-hidden="true" />
      <div className="command-row-body"><div className="actions command-row-title"><strong>{item.title}</strong><Badge>{words(item.kind)}</Badge></div>
        <div className="subtle">{item.reason}</div>
        <div className="rowmeta">{item.owner ? `Owner ${item.owner}` : "Owner not recorded"}{item.due_date ? ` · due ${fmtDate(item.due_date)}` : ""}</div></div>
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Resolve</button>
    </article>} />;
}

function Needs({ items, onOpenTarget }) {
  return <Expandable items={items} empty={<Empty title="No active internal asks">Leadership has no active account-wide ask or escalation.</Empty>}
    render={(item) => <article className="leadership-need" key={item.id}>
      <div className="actions"><strong>{item.need}</strong><Badge>{words(item.status)}</Badge><span className="spacer" /><DueChip date={item.needed_by} /></div>
      <div className="rowmeta">Requested from {item.requested_from || "not recorded"}{item.current_owner ? ` · owner ${item.current_owner}` : ""}</div>
      <div className="leadership-next"><span className="ctx-k">Explicit next action</span>{item.next_action}</div>
      {!!item.escalations.length && <div className="actions leadership-escalations">{item.escalations.map((escalation) => <Badge key={escalation.id}>
        {words(escalation.severity)} escalation · {words(escalation.path_type)}
      </Badge>)}</div>}
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open ask</button>
    </article>} />;
}

function NearTerm({ items, onOpenTarget }) {
  return <Expandable items={items} empty={<Empty title="Nothing near term">No meeting, commitment, review, notice, or renewal is recorded in the near-term window.</Empty>}
    render={(item) => <article className="command-row" key={item.id}>
      <div className="command-date">{dateTime(item.due_date)}</div>
      <div className="command-row-body"><div className="actions command-row-title"><strong>{item.title}</strong><Badge>{words(item.kind)}</Badge></div>
        <div className="rowmeta">{item.detail}</div></div>
      <button className="btn small ghost" onClick={() => onOpenTarget(item.native_target)}>Open</button>
    </article>} />;
}

function ReviewTrail({ view, reviews, onOpenTarget }) {
  return <div>
    {view ? <div className="command-pov"><p>{view.body}</p><div className="rowmeta">Assessed {fmtDate(view.assessed_on)} · {view.author}</div>
      <button className="btn small ghost" onClick={() => onOpenTarget(view.native_target)}>Open point of view</button></div>
      : <Empty title="No point of view">Record a dated operator view before presenting a leadership narrative.</Empty>}
    <div className="leadership-review-trail">
      {reviews?.map((review) => <article key={review.id}>
        <div className="actions"><strong>{words(review.review_type)} review</strong><Badge>{words(review.status)}</Badge></div>
        <div className="rowmeta">{review.held_on ? `Held ${fmtDate(review.held_on)}` : review.scheduled_on ? `Scheduled ${fmtDate(review.scheduled_on)}` : "No review date"}</div>
        {!!review.participants.length && <div className="rowmeta">{review.participants.join(", ")}</div>}
        <button className="btn small ghost" onClick={() => onOpenTarget(review.native_target)}>Open review</button>
      </article>)}
      {!reviews?.length && <div className="rowmeta">No account review trail is recorded.</div>}
    </div>
  </div>;
}

export default function LeadershipReview({ accountId, programId, reloadKey, onOpenTarget, onOpenCopilot }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.leadershipReview(accountId, { programId }));
    } catch (loadError) {
      setData(null);
      setError(loadError.message);
    }
  }, [accountId, programId]);
  useEffect(() => { load(); }, [load, reloadKey]);

  if (!data && !error) return <Loading what="leadership review" />;
  if (error) return <Card className="command-load-error"><Empty title="Leadership review unavailable">{error}</Empty>
    <button className="btn" onClick={load}>Retry</button></Card>;
  const window = data.movement_window;
  const windowLabel = window.program_reviewed_through || window.account_reviewed_through
    ? `Recorded since scoped review · account ${dateTime(window.account_reviewed_through)}${window.program_reviewed_through ? ` · program ${dateTime(window.program_reviewed_through)}` : ""}`
    : `No review checkpoint · recorded since ${dateTime(window.fallback_starts_at)}`;
  return <div className="leadership-workflow stack">
    <div className="leadership-scope callout">
      <div><strong>Internal leadership review</strong><div className="rowmeta">Statuses, forecast, asks, contract, and review trail are account-wide. Program-aware work follows the selected scope.</div></div>
      <div className="actions">
        <button className="btn" onClick={() => onOpenTarget({ tab: "internal" })}>Open Internal</button>
        {onOpenCopilot && <button className="btn primary" onClick={() => onOpenCopilot("draft",
          "Draft a concise internal leadership update using the governed statuses, recorded movement, stuck items, explicit asks, near-term commitments, and dated operator point of view. Name evidence gaps and do not invent a composite health score.")}>Draft leadership update</button>}
      </div>
    </div>
    <Section title="Where the account stands" meta="Two independent governed statuses and the active account-wide forecast call">
      <div className="leadership-statuses">{data.standing.statuses.map((item) => <StatusCard key={item.dimension} item={item} onOpenTarget={onOpenTarget} />)}</div>
      <ForecastTable items={data.standing.forecast} onOpenTarget={onOpenTarget} />
    </Section>
    <div className="leadership-columns">
      <div className="stack">
        <Section title="What moved" meta={windowLabel}><Movement items={data.movement} onOpenTarget={onOpenTarget} /></Section>
        <Section title="What is stuck" meta="Blockers, overdue work, at-risk milestones, and named evidence gaps"><Stuck items={data.stuck} onOpenTarget={onOpenTarget} /></Section>
        <Section title="What I need" meta="Active account-wide asks with owners, deadlines, escalation state, and explicit next actions"><Needs items={data.needs} onOpenTarget={onOpenTarget} /></Section>
      </div>
      <aside className="stack">
        <Section title="Near-term commitments" meta="Next 30 days, plus contractual renewal and notice dates"><NearTerm items={data.near_term} onOpenTarget={onOpenTarget} /></Section>
        <Section title="Point of view and review trail" meta="Operator judgment stays distinct from source facts"><ReviewTrail view={data.operator_view} reviews={data.review_trail} onOpenTarget={onOpenTarget} /></Section>
        {!!data.stamp.omitted?.length && <div className="callout warn">Partial activity coverage: {data.stamp.omitted.map(words).join(", ")}.</div>}
        <div className="callout">Current through {dateTime(data.stamp.data_current_through)}. Opening Leadership does not create or send an update.</div>
      </aside>
    </div>
  </div>;
}
