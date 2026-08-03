import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Empty, Loading, SlideOver, useToast, fmtDate, SegTabs, AgeChip, Badge, Btn, Input } from "../ui";
import ConvertPanel from "./ConvertPanel";

// The Ledger (DESIGN-GUIDE §2.3): one chronological, filterable record of everything on an
// account — interactions, commitments, tasks, decisions, risks, issues, and untriaged capture —
// as a master-detail table. Untriaged inbox notes pin to the top with the unknown treatment.

const CHIPS = [
  ["all", "All"], ["interaction", "Interactions"], ["commitment", "Commitments"],
  ["task", "Tasks"], ["decision", "Decisions"], ["risk", "Risks"], ["issue", "Issues"], ["inbox", "Inbox"],
  ["milestone", "Milestones"],
];
const KIND_LABEL = {
  interaction: "interaction", commitment: "commitment", task: "task",
  decision: "decision", risk: "risk", issue: "issue", inbox: "inbox note",
  milestone: "milestone",
};

// state → (color-band, shape) so state never rides on color alone (§6 badges)
function stateOf(kind, r) {
  const s = (r.status || "").toLowerCase();
  if (kind === "inbox") return { label: "untriaged", band: "unknown" };
  if (kind === "interaction") return { label: r.type?.replace(/_/g, " ") || "—", band: "neutral" };
  if (["done", "closed", "resolved", "complete", "completed", "acknowledged"].includes(s)) return { label: s || "closed", band: "ok" };
  if (kind === "risk" && (r.is_blocker || (r.severity || "") === "high")) return { label: s || "open", band: "risk" };
  if (kind === "issue" && r.is_blocker) return { label: s || "open", band: "risk" };
  if (kind === "decision") return { label: s || "recorded", band: "neutral" };
  return { label: s || "open", band: "warn" };
}

function StateBadge({ band, label }) {
  return (
    <span className={"state-badge band-" + band} title={label}>
      <span className={"state-mark " + band} aria-hidden="true" />
      {label}
    </span>
  );
}

function activityWhen(value) {
  if (!value) return "Not recorded";
  if (!value.includes("T")) return fmtDate(value);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    return `${value.slice(0, 16).replace("T", " · ")} · timezone not recorded`;
  }
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return value.replace("T", " · ");
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  }).format(instant);
}

export default function Ledger({ accountId, programId, reloadKey, onChanged, onOpenTarget }) {
  const [view, setView] = useState("records");
  return <div>
    <SegTabs id="ledger-views" ariaLabel="Ledger view" value={view} onChange={setView}
      tabs={[["records", "Records"], ["activity", "Activity"]]} />
    <div className="ledger-view-body">
      {view === "records"
        ? <RecordsLedger accountId={accountId} programId={programId} reloadKey={reloadKey} onChanged={onChanged} />
        : <ActivityTimeline accountId={accountId} programId={programId} reloadKey={reloadKey} onOpenTarget={onOpenTarget} />}
    </div>
  </div>;
}

function ActivityTimeline({ accountId, programId, reloadKey, onOpenTarget }) {
  const [direction, setDirection] = useState("past");
  const [stream, setStream] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [activityState, setActivityState] = useState("");
  const [materiality, setMateriality] = useState("");
  const [search, setSearch] = useState("");
  const [data, setData] = useState(null);
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [expandedGroups, setExpandedGroups] = useState(() => new Set());
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  const filters = { programId, direction, stream, sourceType, state: activityState, materiality, limit: 50 };
  useEffect(() => {
    let current = true;
    setLoading(true); setError(null); setSelectedId(null); setExpandedGroups(new Set());
    api.accountActivity(accountId, filters).then((result) => {
      if (!current) return;
      setData(result); setItems(result.items); setLoading(false);
    }).catch((loadError) => {
      if (!current) return;
      setError(loadError.message); setData(null); setItems([]); setLoading(false);
    });
    return () => { current = false; };
    // Scalar dependencies intentionally describe the server query; filters is rebuilt per render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId, programId, direction, stream, sourceType, activityState, materiality, reloadKey]);

  async function loadMore() {
    if (!data?.next_cursor) return;
    setLoadingMore(true);
    try {
      const result = await api.accountActivity(accountId, { ...filters, nextCursor: data.next_cursor });
      setItems((current) => [...current, ...result.items]);
      setData(result);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoadingMore(false);
    }
  }

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => [item.title, item.summary, item.reason, item.owner, item.actor,
      item.source_type, item.event_kind].some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [items, search]);
  const selected = shown.find((item) => item.id === selectedId) || null;
  const sourceFacets = Object.entries(data?.facets?.source_types || {});
  const grouped = useMemo(() => {
    const members = new Map();
    shown.forEach((item) => {
      if (item.group_id) members.set(item.group_id, [...(members.get(item.group_id) || []), item]);
    });
    const emitted = new Set();
    return shown.flatMap((item) => {
      if (!item.group_id || (members.get(item.group_id)?.length || 0) < 2) {
        return [{ root: item, linked: [] }];
      }
      if (emitted.has(item.group_id)) return [];
      emitted.add(item.group_id);
      const group = members.get(item.group_id);
      const root = group.find((candidate) => candidate.group_role === "origin") || group[0];
      return [{ root, linked: group.filter((candidate) => candidate.id !== root.id) }];
    });
  }, [shown]);

  if (loading) return <Loading what="account activity" />;
  return <div className="activity-consumer stack">
    {error && <div className="callout warn" role="status">Activity could not be read: {error}</div>}
    {data && <div className="activity-evidence callout">
      <div><strong>{data.stamp.coverage.length}/{data.stamp.adapter_metrics.length} adapters covered</strong>
        <div className="rowmeta">{data.matched_count} matching events · projected in {data.stamp.projection_duration_ms.toFixed(3)} ms · query-time and rebuildable</div></div>
      <details className="activity-diagnostics"><summary>Coverage and query evidence</summary>
        <div className="actions activity-adapters" aria-label="Activity adapter measurements">
          {data.stamp.adapter_metrics.map((metric) => <span className={`badge ${metric.status === "omitted" ? "band-risk" : ""}`} key={metric.adapter}
            title={`${metric.item_count} items in ${metric.duration_ms.toFixed(3)} ms`}>
            {metric.adapter} · {metric.item_count} · {metric.duration_ms.toFixed(3)} ms
          </span>)}
        </div>
      </details>
    </div>}
    {!!data?.stamp.omitted.length && <div className="callout warn">Partial coverage: {data.stamp.omitted.join(", ")} could not be read. Empty results are not complete.</div>}
    <div className="viewbar activity-filters" aria-label="Activity filters">
      <label className="view-filter">Time
        <select value={direction} onChange={(event) => setDirection(event.target.value)}>
          <option value="past">Past</option><option value="future">Future</option><option value="all">All</option>
        </select></label>
      <label className="view-filter">Stream
        <select value={stream} onChange={(event) => setStream(event.target.value)}>
          <option value="">All</option><option value="customer">Customer</option><option value="internal">Internal</option>
          <option value="external">External</option><option value="unknown">Unknown</option>
        </select></label>
      <label className="view-filter">Source
        <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
          <option value="">All</option>{sourceFacets.map(([value, count]) => <option key={value} value={value}>{value.replaceAll("_", " ")} ({count})</option>)}
        </select></label>
      <label className="view-filter">State
        <select value={activityState} onChange={(event) => setActivityState(event.target.value)}>
          <option value="">All</option>{Object.entries(data?.facets?.states || {}).map(([value, count]) => <option key={value} value={value}>{value} ({count})</option>)}
        </select></label>
      <label className="view-filter">Importance
        <select value={materiality} onChange={(event) => setMateriality(event.target.value)}>
          <option value="">All</option><option value="material">Material</option><option value="context">Context</option>
        </select></label>
      <label className="view-filter">Search loaded
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Title, reason, owner…" /></label>
    </div>
    <div className="ledger activity-ledger">
      <div className="card ledger-list activity-list">
        {!shown.length ? <Empty title="No covered activity matches">Change the filters, or inspect partial coverage before concluding nothing happened.</Empty> : <table>
          <thead><tr><th scope="col">Activity</th><th scope="col">Stream</th><th scope="col">Effective</th><th scope="col">Recorded</th></tr></thead>
          <tbody>{grouped.flatMap(({ root, linked }) => {
            const expanded = root.group_id && expandedGroups.has(root.group_id);
            const renderRow = (item, isLinked = false) => <tr key={item.id} className={`clickable${item.id === selectedId ? " sel" : ""}${isLinked ? " activity-linked-row" : ""}`}
              onClick={() => setSelectedId(item.id)} tabIndex={0}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(item.id); } }}>
              <td><div className="actions activity-title">{isLinked && <span className="rowmeta" aria-hidden="true">↳</span>}<strong>{item.title}</strong><Badge>{item.source_type.replaceAll("_", " ")}</Badge>
                {!isLinked && linked.length > 0 && <button className="btn small ghost activity-group-toggle"
                  aria-expanded={Boolean(expanded)} onClick={(event) => { event.stopPropagation(); setExpandedGroups((current) => {
                    const next = new Set(current); if (expanded) next.delete(root.group_id); else next.add(root.group_id); return next;
                  }); }}>{expanded ? "Hide" : `+${linked.length} linked`}</button>}</div>
                {item.summary && <div className="rowmeta">{item.summary}</div>}</td>
              <td><StateBadge band={item.state === "confirmed" ? "ok" : item.state === "proposed" ? "warn" : "unknown"} label={`${item.stream} · ${item.state}`} /></td>
              <td><AgeChip date={item.display_at} /><div className="rowmeta">{item.temporal_kind}</div></td>
              <td><AgeChip date={item.recorded_at} /></td>
            </tr>;
            return [renderRow(root), ...(expanded ? linked.map((item) => renderRow(item, true)) : [])];
          })}</tbody>
        </table>}
        {data?.next_cursor && <button className="command-more" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "Loading…" : "Load 50 more"}</button>}
      </div>
      <div className="card ledger-detail">
        {selected ? <ActivityDetail item={selected} onOpenTarget={onOpenTarget} />
          : <Empty title="Select an activity event">Its temporal meaning, provenance, reason, and native record appear here.</Empty>}
      </div>
    </div>
  </div>;
}

function ActivityDetail({ item, onOpenTarget }) {
  return <div className="detail-body">
    <div className="detail-head"><Badge>{item.source_type.replaceAll("_", " ")}</Badge>
      <StateBadge band={item.state === "confirmed" ? "ok" : item.state === "proposed" ? "warn" : "unknown"} label={item.state} />
      <Badge>{item.materiality}</Badge></div>
    <div className="detail-title">{item.title}</div>
    {item.summary && <p>{item.summary}</p>}
    <dl className="kv">
      <dt>Effective</dt><dd><span className="mono">{activityWhen(item.display_at)}</span> · {item.temporal_kind} · {item.temporal_precision}</dd>
      <dt>Recorded</dt><dd className="mono">{activityWhen(item.recorded_at)}</dd>
      <dt>Why included</dt><dd>{item.reason}</dd>
      <dt>Stream</dt><dd>{item.stream}</dd>
      <dt>Event</dt><dd>{item.event_kind.replaceAll("_", " ")}</dd>
      {item.status && <><dt>Native state</dt><dd>{item.status.replaceAll("_", " ")}</dd></>}
      {item.owner && <><dt>Owner</dt><dd>{item.owner}</dd></>}
      {item.actor && <><dt>Actor</dt><dd>{item.actor}</dd></>}
      {item.program_id && <><dt>Program scope</dt><dd className="mono">{item.program_id}</dd></>}
      {!!item.participants.length && <><dt>Participants</dt><dd>{item.participants.map((person) => person.name).join(", ")}</dd></>}
      {item.group_id && <><dt>Activity group</dt><dd>{item.group_role === "origin" ? "Originating interaction" : "Record created from the linked interaction"}</dd></>}
      {item.source_reference && <><dt>Source</dt><dd>{item.source_reference.url
        ? <a href={item.source_reference.url} target="_blank" rel="noreferrer">{item.source_reference.label}</a>
        : item.source_reference.label}</dd></>}
    </dl>
    {onOpenTarget && <button className="btn primary" onClick={() => onOpenTarget(item.native_target)}>Open native record</button>}
  </div>;
}

function RecordsLedger({ accountId, programId, reloadKey, onChanged }) {
  const toast = useToast();
  const [exec, setExec] = useState(null);
  const [history, setHistory] = useState(null);
  const [inbox, setInbox] = useState([]);
  const [filter, setFilter] = useState("all");
  const [selKey, setSelKey] = useState(null);
  const [converting, setConverting] = useState(null);
  const [closing, setClosing] = useState(null);

  async function load() {
    if (!accountId) return;
    try {
      const [e, h, ib] = await Promise.all([
        api.accountExecution(accountId),
        api.history(accountId, programId ? { programId } : {}),
        api.inbox("untriaged"),
      ]);
      setExec(e); setHistory(h);
      setInbox(ib.filter((it) => it.interaction?.account_id === accountId && (!programId || it.interaction?.program_id === programId)));
    } catch (err) { toast(err.message, "err"); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [accountId, programId, reloadKey]);

  const rows = useMemo(() => {
    if (!exec || !history) return [];
    const out = [];
    const pushExec = (kind, list, dateKey) => (list || []).forEach((r) => {
      if (programId && r.program_id && r.program_id !== programId) return;
      out.push({
        key: `${kind}:${r.id}`, kind, raw: r,
        date: r[dateKey] || r.created_at, title: r.description || r.name || "(untitled)",
        program: r.program_name,
        owner: r.internal_owner_name || r.responsible_party_name || null,
        state: stateOf(kind, r), sourceInteractionId: r.source_interaction_id,
      });
    });
    pushExec("commitment", exec.commitments, "due_date");
    pushExec("task", exec.tasks, "due_date");
    pushExec("decision", exec.decisions, "decided_on");
    pushExec("risk", exec.risks, "created_at");
    pushExec("issue", exec.issues, "created_at");
    pushExec("milestone", exec.milestones, "target_date");
    (history.interactions || []).forEach((it) => out.push({
      key: `interaction:${it.id}`, kind: "interaction", raw: it,
      date: it.occurred_on, title: it.summary || "(interaction)", program: it.program_name,
      owner: null, state: stateOf("interaction", it), sourceInteractionId: it.id,
    }));
    inbox.forEach((it) => out.push({
      key: `inbox:${it.id}`, kind: "inbox", raw: it,
      date: it.created_at, title: it.raw_text, program: it.interaction?.program_id ? undefined : undefined,
      owner: null, state: stateOf("inbox", it), pinned: true,
    }));
    // untriaged inbox pinned to the top, then newest-first by date
    out.sort((a, b) => {
      if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
      return (b.date || "").localeCompare(a.date || "");
    });
    return out;
  }, [exec, history, inbox, programId]);

  const counts = useMemo(() => {
    const c = { all: rows.length };
    rows.forEach((r) => { c[r.kind] = (c[r.kind] || 0) + 1; });
    return c;
  }, [rows]);

  const shown = filter === "all" ? rows : rows.filter((r) => r.kind === filter);
  const selected = shown.find((r) => r.key === selKey) || null;

  const afterMutation = () => { setClosing(null); setConverting(null); setSelKey(null); load(); onChanged?.(); };

  if (!exec || !history) return <Loading what="ledger" />;

  return (
    <div>
      <SegTabs kind="chip" value={filter} onChange={setFilter}
        tabs={CHIPS.map(([k, label]) => [k, label, counts[k] || 0])} />
      <div style={{ height: 12 }} />

      <div className="ledger">
        <div className="card ledger-list">
          {shown.length === 0 ? <Empty title="Nothing here yet">Capture a call, or convert an inbox note into a record.</Empty> : (
            <table>
              <thead><tr><th scope="col" style={{ width: 96 }}>Type</th><th scope="col">What</th><th scope="col" style={{ width: 120 }}>State</th><th scope="col" className="num" style={{ width: 64 }}>Age</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.key} className={"clickable" + (r.key === selKey ? " sel" : "") + (r.pinned ? " unknown-row" : "")} onClick={() => setSelKey(r.key)}
                      tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelKey(r.key); } }}>
                    <td><Badge>{KIND_LABEL[r.kind]}</Badge></td>
                    <td>
                      <div className="cell-title">{r.title}</div>
                      <div className="rowmeta">{[r.program, r.owner].filter(Boolean).join(" · ") || <span>&nbsp;</span>}</div>
                    </td>
                    <td><StateBadge band={r.state.band} label={r.state.label} /></td>
                    <td><AgeChip date={r.date} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card ledger-detail">
          {!selected ? <div className="empty"><h3>Select a record</h3><div>Its detail and actions appear here.</div></div> : (
            <Detail row={selected} onConvert={() => setConverting(selected.raw)} onClose={() => setClosing(selected)}
                    onShare={async () => {
                      try {
                        await api.mapPromote({ object_type: selected.kind, object_id: selected.raw.id,
                          client_visible: !Boolean(selected.raw.client_visible) });
                        toast(selected.raw.client_visible ? "Removed from mutual plan" : "Added to mutual plan");
                        await load(); onChanged?.();
                      } catch (e) { toast(e.message, "err"); }
                    }} />
          )}
        </div>
      </div>

      {converting && <ConvertPanel item={converting} onClose={() => setConverting(null)} onConverted={afterMutation} />}
      {closing && <CloseItemPanel row={closing} onClose={() => setClosing(null)} onDone={afterMutation} />}
    </div>
  );
}

function Detail({ row, onConvert, onClose, onShare }) {
  const r = row.raw;
  const closable = ["commitment", "task", "risk", "issue"].includes(row.kind) && row.state.band !== "ok";
  return (
    <div className="detail-body">
      <div className="detail-head">
        <Badge>{KIND_LABEL[row.kind]}</Badge>
        <StateBadge band={row.state.band} label={row.state.label} />
        <span className="mono rowmeta" style={{ marginLeft: "auto" }}>{fmtDate(row.date)}</span>
      </div>
      <div className="detail-title">{row.title}</div>

      <dl className="kv">
        {row.program && <><dt>Program</dt><dd>{row.program}</dd></>}
        {r.responsible_party_name && <><dt>Who does it</dt><dd>{r.responsible_party_name}</dd></>}
        {r.internal_owner_name && <><dt>Valence owner</dt><dd>{r.internal_owner_name}</dd></>}
        {r.due_date && <><dt>Due</dt><dd className="mono">{fmtDate(r.due_date)}</dd></>}
        {r.severity && <><dt>Severity</dt><dd style={{ textTransform: "capitalize" }}>{r.severity}{r.is_blocker ? " · blocker" : ""}</dd></>}
        {row.kind === "issue" && r.is_blocker != null && <><dt>Blocker</dt><dd>{r.is_blocker ? "Yes" : "No"}</dd></>}
        {r.rationale && <><dt>Rationale</dt><dd>{r.rationale}</dd></>}
        {r.decided_on && <><dt>Decided</dt><dd className="mono">{fmtDate(r.decided_on)}</dd></>}
        {row.kind === "interaction" && r.participants?.length > 0 && <><dt>Participants</dt><dd>{r.participants.map((p) => p.name).filter(Boolean).join(", ")}</dd></>}
        {r.close_note && <><dt>Close note</dt><dd>{r.close_note}</dd></>}
      </dl>

      {row.kind === "interaction" && r.created_records?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 4 }}>Records from this touch</div>
          {r.created_records.map((d) => (
            <div key={d.id} className="rowmeta"><span className="badge" style={{ marginRight: 4 }}>{d.type}</span>{d.label}</div>
          ))}
        </div>
      )}

      <div className="actions" style={{ marginTop: 16 }}>
        {row.kind === "inbox" && <Btn variant="primary" size="small" onClick={onConvert}>Convert to record</Btn>}
        {closable && <Btn variant="primary" size="small" onClick={onClose}>
          {row.kind === "issue" ? "Resolve issue" : row.kind === "risk" ? "Close risk" : row.kind === "commitment" ? "Close commitment" : "Close task"}
        </Btn>}
        {["commitment", "task", "milestone"].includes(row.kind) && (
          <Btn size="small" onClick={onShare}>
            {r.client_visible ? "★ Shared in mutual plan" : "☆ Add to mutual plan"}
          </Btn>
        )}
      </div>
    </div>
  );
}

// One compact panel to close/resolve any of commitment / task / risk / issue, matching each
// type's closure rule (Section 3). Reuses the existing endpoints.
function CloseItemPanel({ row, onClose, onDone }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [reason, setReason] = useState(row.kind === "risk" ? "no_longer_relevant" : row.kind === "issue" ? "condition_removed" : "");
  const [taskStatus, setTaskStatus] = useState("done");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const id = row.raw.id;
      if (row.kind === "commitment") await api.closeCommitment(id, { close_note: note || null });
      else if (row.kind === "task") await api.closeTask(id, { status: taskStatus, close_note: note || null });
      else if (row.kind === "risk") await api.closeRisk(id, { close_reason: reason, close_note: note || null });
      else if (row.kind === "issue") await api.resolveIssue(id, { resolution_type: reason, resolution_note: note || null });
      toast(row.kind === "issue" ? "Resolved" : "Closed");
      onDone();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }

  const verb = row.kind === "issue" ? "Resolve issue" : row.kind === "risk" ? "Close risk" : "Close " + row.kind;
  return (
    <SlideOver title={verb} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={saving}>{verb}</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{row.title}</div>
      {row.kind === "task" && (
        <div className="field"><label>Outcome</label>
          <select value={taskStatus} onChange={(e) => setTaskStatus(e.target.value)}>
            <option value="done">Done</option><option value="cancelled">Cancelled</option>
          </select>
        </div>
      )}
      {row.kind === "risk" && (
        <div className="field"><label>Why it closes</label>
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="no_longer_relevant">No longer relevant</option>
            <option value="no_longer_possible">No longer possible</option>
          </select>
        </div>
      )}
      {row.kind === "issue" && (
        <div className="field"><label>How it resolved</label>
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="condition_removed">Condition removed</option>
            <option value="workaround_operating">Workaround operating</option>
          </select>
        </div>
      )}
      <Input as="textarea" label="Note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="What happened (optional)" />
    </SlideOver>
  );
}
