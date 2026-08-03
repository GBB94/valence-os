import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, Loading, SlideOver, useToast, PageHeader, AgeChip, Table } from "../ui";
import { SavedViewBar } from "../SavedViewControls";
import { useSavedViews } from "../useSavedViews";
import { accountFilterOptions } from "../queueView";

const TODAY_VIEWS = [
  { id: "all", label: "All attention", state: { band: "all", accountId: "", query: "" } },
  { id: "needs-now", label: "Needs you now", state: { band: "now", accountId: "", query: "" } },
  { id: "this-week", label: "This week", state: { band: "week", accountId: "", query: "" } },
  { id: "keep-an-eye", label: "Keep an eye", state: { band: "watch", accountId: "", query: "" } },
];
const TODAY_BAND_KEYS = new Set(["all", "now", "week", "watch"]);
function normalizeTodayView(state = {}) {
  return {
    band: TODAY_BAND_KEYS.has(state.band) ? state.band : "all",
    accountId: typeof state.accountId === "string" ? state.accountId : "",
    query: typeof state.query === "string" ? state.query : "",
  };
}

// Portfolio home — the ranked, explainable attention queue (Module A).
export default function Queue({ reloadKey, onOpenAccount, onChanged, viewId, onViewChange }) {
  const toast = useToast();
  const [q, setQ] = useState(null);
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [snoozing, setSnoozing] = useState(null); // item
  const [resolving, setResolving] = useState(null); // item
  const views = useSavedViews({
    surface: "today", builtIns: TODAY_VIEWS, defaultId: "all", requestedId: viewId, onActivate: onViewChange,
    normalizeState: normalizeTodayView,
  });

  async function load() {
    try { setQ(await api.queue()); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [reloadKey]);

  const after = () => { setSnoozing(null); setResolving(null); load(); onChanged?.(); };

  if (!q) return <Loading what="attention queue" />;

  const query = views.state.query.trim().toLowerCase();
  const visibleItems = q.items.filter((item) => {
    const band = BANDS.find((candidate) => candidate.match(item.priority))?.key;
    if (views.state.band !== "all" && band !== views.state.band) return false;
    if (views.state.accountId && item.account_id !== views.state.accountId) return false;
    if (!query) return true;
    return [item.title, item.because, item.next_action, item.account_name, item.program_name]
      .filter(Boolean).some((value) => value.toLowerCase().includes(query));
  });
  const bands = BANDS.map((b) => ({ ...b, items: visibleItems.filter((it) => b.match(it.priority)) })).filter((b) => b.items.length);
  // Portfolio-level attention (for example, a stale global metric definition) deliberately has
  // no account. It belongs in the queue, but not in an account filter whose labels must be sortable.
  const accountOptions = accountFilterOptions(q.items);

  return (
    <div>
      <PageHeader title="Today" meta={`${visibleItems.length}${visibleItems.length !== q.items.length ? ` of ${q.items.length}` : ""} to act · as of ${q.as_of}`} />
      <div className="rowmeta" style={{ marginBottom: 14 }}>
        Ranked by rule, grouped by urgency, and every item explains itself. This screen exists to be emptied.
      </div>

      <SavedViewBar model={views}>
        <label className="view-filter">
          <span className="rowmeta">Account</span>
          <select aria-label="Filter attention by account" value={views.state.accountId}
            onChange={(event) => views.setState((current) => ({ ...current, accountId: event.target.value }))}>
            <option value="">All accounts</option>
            {accountOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        <input aria-label="Search attention" placeholder="Search attention…" value={views.state.query}
          onChange={(event) => views.setState((current) => ({ ...current, query: event.target.value }))} />
      </SavedViewBar>

      {q.items.length === 0 ? (
        <div className="card"><Empty title="Queue clear">Nothing needs attention right now.</Empty></div>
      ) : visibleItems.length === 0 ? (
        <div className="card"><Empty title="No matching attention">Change this view's account or search filters.</Empty></div>
      ) : (
        bands.map((b) => (
          <div key={b.key} style={{ marginBottom: 18 }}>
            <div className="band-head"><span className={"state-mark " + b.band} /> {b.label} <span className="rowmeta">{b.items.length}</span></div>
            <div className="card">
              <Table columns={[{ width: 2, pad: 0 }, { label: "What needs you" }, { label: "Account", width: 160 }, { label: "Age", width: 76 }, { label: "", width: 150 }]}>
                {b.items.map((it) => <QueueRow key={it.key} it={it} band={b.band} onOpenAccount={onOpenAccount} onSnooze={() => setSnoozing(it)} onResolve={() => setResolving(it)} />)}
              </Table>
            </div>
          </div>
        ))
      )}

      {q.snoozed_count > 0 && (
        <div style={{ marginTop: 10 }}>
          <button className="btn small ghost" onClick={() => setShowSnoozed((v) => !v)}>
            {showSnoozed ? "Hide" : "Show"} snoozed ({q.snoozed_count})
          </button>
          {showSnoozed && (
            <div className="card" style={{ marginTop: 8 }}>
              <table>
                <tbody>
                  {q.snoozed.map((it) => (
                    <tr key={it.key}>
                      <td>{it.title}<div className="rowmeta">{it.account_name}{it.program_name ? ` · ${it.program_name}` : ""}</div></td>
                      <td className="rowmeta">{it.snooze_until ? `until ${it.snooze_until}` : it.resurface_condition}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {snoozing && <SnoozePanel item={snoozing} onClose={() => setSnoozing(null)} onDone={after} />}
      {resolving && <ResolvePanel item={resolving} onClose={() => setResolving(null)} onDone={after} />}
    </div>
  );
}

// Urgency bands (DESIGN-GUIDE §2.5): grouped, not one flat list. Priority 1–6 from the queue.
const BANDS = [
  { key: "now", label: "Needs you now", band: "risk", match: (p) => p <= 2 },
  { key: "week", label: "This week", band: "warn", match: (p) => p === 3 },
  { key: "watch", label: "Keep an eye", band: "neutral", match: (p) => p >= 4 },
];

function QueueRow({ it, band, onOpenAccount, onSnooze, onResolve }) {
  return (
    <tr>
      <td className={"rail-cell band-" + band} style={{ padding: 0 }}></td>
      <td>
        <div className="cell-title">{it.title}</div>
        <div className="rowmeta">
          {it.because} <span style={{ color: "var(--accent)" }}>{it.next_action}</span>
        </div>
      </td>
      <td>
        {it.account_id && it.account_name
          ? <button className="linklike" onClick={() => onOpenAccount(it.account_id)}>{it.account_name}</button>
          : <span className="rowmeta">Portfolio</span>}
        {it.program_name ? <div className="rowmeta">{it.program_name}</div> : null}
      </td>
      <td><AgeChip days={it.age_days} />{it.due_date ? <div className="rowmeta">due {it.due_date}</div> : null}</td>
      <td>
        <div className="actions">
          <button className="btn small" onClick={onSnooze}>Snooze</button>
          <button className="btn small ghost" onClick={onResolve}>Resolve</button>
        </div>
      </td>
    </tr>
  );
}

function SnoozePanel({ item, onClose, onDone }) {
  const toast = useToast();
  const [until, setUntil] = useState("");
  const [cond, setCond] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    if (!until && !cond.trim()) { toast("Give a return date or a resurfacing condition.", "err"); return; }
    setSaving(true);
    try {
      await api.snoozeQueue({ item_key: item.key, snooze_until: until || null, resurface_condition: cond.trim() || null });
      toast("Snoozed"); onDone();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }
  return (
    <SlideOver title="Snooze item" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={saving}>Snooze</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{item.title}</div>
      <div className="field"><label>Return date</label><input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></div>
      <div style={{ textAlign: "center", color: "var(--ink-tertiary)", margin: "6px 0" }}>or</div>
      <div className="field"><label>Resurfacing condition</label>
        <input value={cond} onChange={(e) => setCond(e.target.value)} placeholder="e.g. if works-council review isn't scheduled by next week" />
        <div className="hint">The item also resurfaces automatically if its underlying facts change.</div>
      </div>
    </SlideOver>
  );
}

function ResolvePanel({ item, onClose, onDone }) {
  const toast = useToast();
  const [desc, setDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const canCreate = !!item.program_id;
  async function save() {
    if (!desc.trim()) { toast("Describe the follow-up action.", "err"); return; }
    setSaving(true);
    try {
      const task = await api.createTask({ program_id: item.program_id, description: desc.trim() });
      await api.resolveQueue({ item_key: item.key, successor_action_type: "task", successor_action_id: task.id });
      toast("Resolved with a follow-up task"); onDone();
    } catch (e) { toast(e.message, "err"); } finally { setSaving(false); }
  }
  return (
    <SlideOver title="Resolve item" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={saving || !canCreate}>Resolve</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{item.title}</div>
      {canCreate ? (
        <div className="field"><label>Link a follow-up task <span className="req">*</span></label>
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Resolving requires a successor action, so risk is never just hidden." />
          <div className="hint">Creates a task in {item.program_name} and marks this item resolved.</div>
        </div>
      ) : (
        <div className="placeholder">This item isn’t tied to a program, so a follow-up task can’t be auto-created here. Convert it or act on it directly.</div>
      )}
    </SlideOver>
  );
}
