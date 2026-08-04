import { createContext, useContext, useState, useCallback, useEffect, useId, useRef } from "react";
import { api } from "./api";
import { nextTabKey } from "./segTabs";

// Canvas/SVG charts can't use CSS var() in attributes — resolve the token to a concrete color,
// and re-render when the theme flips so both themes render correctly (DESIGN-GUIDE §8).
export function cssVar(name, fallback = "") {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
export function useThemeTick() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const obs = new MutationObserver(() => setTick((t) => t + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return tick;
}

// --- Toast (auto-save feedback; non-blocking, per Section 6) ---
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const show = useCallback((message, kind = "ok") => {
    setToast({ message, kind });
    setTimeout(() => setToast(null), 2600);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className={"toast" + (toast.kind === "err" ? " err" : "")}>{toast.message}</div>}
    </ToastCtx.Provider>
  );
}

// --- Shared primitives (DESIGN-GUIDE §6). Thin wrappers over the tokenized classes so
//     screens compose from one vocabulary instead of ad hoc markup. ---
export function Btn({ variant = "secondary", size = "default", className = "", children, ...rest }) {
  const v = variant === "primary" ? " primary" : variant === "ghost" ? " ghost" : variant === "danger" ? " danger" : "";
  const s = size === "small" ? " small" : "";
  return <button className={"btn" + v + s + (className ? " " + className : "")} {...rest}>{children}</button>;
}

export function Badge({ children, className = "" }) {
  return <span className={"badge" + (className ? " " + className : "")}>{children}</span>;
}

function trackSurfaceSpotlight(event) {
  const bounds = event.currentTarget.getBoundingClientRect();
  event.currentTarget.style.setProperty("--surface-spot-x", `${event.clientX - bounds.left}px`);
  event.currentTarget.style.setProperty("--surface-spot-y", `${event.clientY - bounds.top}px`);
}

function resetSurfaceSpotlight(event) {
  event.currentTarget.style.setProperty("--surface-spot-x", "50%");
  event.currentTarget.style.setProperty("--surface-spot-y", "0%");
}

export function Card({ as: Component = "div", className = "", children, spotlight = false,
  onPointerMove, onPointerLeave, ...rest }) {
  function handlePointerMove(event) {
    if (spotlight) trackSurfaceSpotlight(event);
    onPointerMove?.(event);
  }
  function handlePointerLeave(event) {
    if (spotlight) resetSurfaceSpotlight(event);
    onPointerLeave?.(event);
  }
  const classes = `card${spotlight ? " spotlight-surface" : ""}${className ? ` ${className}` : ""}`;
  return <Component className={classes} onPointerMove={handlePointerMove}
    onPointerLeave={handlePointerLeave} {...rest}>{children}</Component>;
}

export function PhaseBadge({ phase }) {
  return <span className="badge phase">{phase}</span>;
}

// Screen header: title, optional right-aligned meta, optional action cluster.
export function PageHeader({ title, meta, eyebrow, subtitle, children, spotlight = false, className = "" }) {
  return (
    <header className={`page-header${spotlight ? " page-header-feature spotlight-surface" : ""}${className ? ` ${className}` : ""}`}
      onPointerMove={spotlight ? trackSurfaceSpotlight : undefined}
      onPointerLeave={spotlight ? resetSurfaceSpotlight : undefined}>
      <div className="page-header-copy">
        {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <div className="page-subtitle">{subtitle}</div>}
      </div>
      <div className="spacer" />
      {meta && <span className="page-meta">{meta}</span>}
      {children}
    </header>
  );
}

// Segmented tabs (inner selectors, filter groups). tabs: [[key, label, count?], …]
export function SegTabs({ tabs, value, onChange, kind = "tab", ariaLabel = "Section", id, panelId }) {
  const cls = kind === "chip" ? "filter-chip" : "tab";
  const autoId = useId();
  const baseId = id || `seg-tabs-${autoId.replaceAll(":", "")}`;
  const refs = useRef(new Map());
  function onKeyDown(event) {
    const next = nextTabKey(tabs, value, event.key);
    if (!next) return;
    event.preventDefault();
    onChange(next);
    requestAnimationFrame(() => refs.current.get(next)?.focus());
  }
  return (
    <div className={kind === "chip" ? "chiprow" : "tabstrip inner"} role="tablist"
      aria-label={ariaLabel} onKeyDown={onKeyDown}>
      {tabs.map(([key, label, count]) => (
        <button key={key} id={`${baseId}-${key}-tab`} role="tab" aria-selected={value === key}
          aria-controls={panelId} tabIndex={value === key ? 0 : -1}
          ref={(node) => { if (node) refs.current.set(key, node); else refs.current.delete(key); }}
          className={cls + (value === key ? " active" : "")} onClick={() => onChange(key)}>
          {label}{count != null && <span className="chip-count">{count}</span>}
        </button>
      ))}
    </div>
  );
}

// Semantic table primitive. columns: [{ label, width?, align?, pad? }]; rows are the children
// (each a <tr>). Header alignment matches the column so numeric columns line up right.
export function Table({ columns, children }) {
  return (
    <table>
      <thead>
        <tr>{columns.map((c, i) => (
          <th key={i} scope="col" style={{ width: c.width, textAlign: c.align, padding: c.pad }}>{c.label}</th>
        ))}</tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

// Labeled form control (input / select / textarea). Errors state the next move, not the failure.
export function Input({ label, hint, error, required, as = "input", children, ...props }) {
  const Ctl = as;
  return (
    <div className="field">
      {label && <label>{label}{required && <span className="req"> *</span>}</label>}
      <Ctl {...props}>{children}</Ctl>
      {hint && <div className="hint">{hint}</div>}
      {error && <div className="hint" style={{ color: "var(--status-risk)" }}>{error}</div>}
    </div>
  );
}

// Hover/focus tooltip (the ⓘ affordance, reusable).
export function Tooltip({ text, children, label = "i" }) {
  if (!text) return children || null;
  return (
    <span className="pagehelp" tabIndex={0} role="note" aria-label={typeof text === "string" ? text : undefined}>
      {children || <span className="pagehelp-icon" aria-hidden="true">{label}</span>}
      <span className="pagehelp-tip" role="tooltip"><span>{text}</span></span>
    </span>
  );
}

// Stance = categorical (D-67): color from the data family + a shape, matching the graph, so it
// reads without color and never as health. ● supporter / ◆ skeptic / ▮ unconverted.
export function StanceLabel({ stance }) {
  if (!stance) return <span className="rowmeta">—</span>;
  return (
    <span className={"stance stance-" + stance}>
      <span className="stance-mark" aria-hidden="true" /> {stance}
    </span>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <div>{children}</div>
    </div>
  );
}

// --- Slide-over (detail/quick-entry; never a blocking modal for routine work) ---
// Keyboard contract (DESIGN-GUIDE §11): Escape closes, Tab cycles inside, and focus
// returns to wherever the operator was standing when the panel opened.
export function SlideOver({ title, onClose, children, footer }) {
  const panelRef = useRef(null);
  const closeRef = useRef(null);
  useEffect(() => {
    const opener = document.activeElement;
    closeRef.current?.focus();
    const key = (event) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(panelRef.current?.querySelectorAll(
        'button:not([disabled]), textarea:not([disabled]), select:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])') || [])];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("keydown", key); if (opener?.focus) opener.focus(); };
  }, [onClose]);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="slideover" role="dialog" aria-modal="true" aria-label={title} ref={panelRef}>
        <header>
          <h1>{title}</h1>
          <div className="spacer" />
          <button className="btn ghost" onClick={onClose} ref={closeRef}>Close</button>
        </header>
        <div className="body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </aside>
    </>
  );
}

export const ROLE_LABELS = {
  champion: "Champion", budget_owner: "Budget owner", program_owner: "Program owner",
  it: "IT", legal_dpo: "Legal / DPO", works_council_contact: "Works council", other: "Other",
};

export function fmtDate(d) {
  return d ? d.slice(0, 10) : "—";
}

// --- Freshness language (DESIGN-GUIDE §7). The signature motif: every dated record shows
//     its age in one monospaced form, and the decay ramp makes an aging screen look aging. ---
// Parse a date-only (YYYY-MM-DD) or full ISO timestamp; keep the time so the hours form works.
function ageParts(dateStr) {
  if (!dateStr) return null;
  const hasTime = dateStr.length > 10;
  const d = new Date(hasTime ? dateStr : dateStr.slice(0, 10) + "T00:00:00");
  if (isNaN(d)) return null;
  return { ms: Math.max(0, Date.now() - d.getTime()), hasTime };
}
export function ageDays(dateStr) {
  const p = ageParts(dateStr);
  return p ? Math.floor(p.ms / 86400000) : null;
}
// Shortest honest form: now / Nm / Nh (only when a time is known) → today / Nd / Nw / Nmo.
export function ageLabel(dateStr) {
  const p = ageParts(dateStr);
  if (!p) return "—";
  const days = Math.floor(p.ms / 86400000);
  const hours = Math.floor(p.ms / 3600000);
  if (p.hasTime && hours < 1) { const m = Math.floor(p.ms / 60000); return m < 1 ? "now" : `${m}m`; }
  if (p.hasTime && hours < 24) return `${hours}h`;
  if (days < 1) return "today";
  if (days < 21) return `${days}d`;
  if (days < 84) return `${Math.round(days / 7)}w`;
  return `${Math.round(days / 30)}mo`;
}
// bucket: fresh 0–7 · aging 8–21 · stale 22+  (§7 decay ramp)
export function bucketFor(days) {
  if (days == null) return "none";
  if (days <= 7) return "fresh";
  if (days <= 21) return "aging";
  return "stale";
}
// AgeChip renders from a date string, or from a pre-computed integer day count (`days`) for
// surfaces like the attention queue that only expose an age, not the underlying timestamp.
export function AgeChip({ date, days }) {
  if (date == null && days != null) {
    const label = days < 1 ? "today" : days < 21 ? `${days}d` : days < 84 ? `${Math.round(days / 7)}w` : `${Math.round(days / 30)}mo`;
    return <span className={"age age-" + bucketFor(days)}>{label}</span>;
  }
  return <span className={"age age-" + bucketFor(ageDays(date))} title={date ? `as of ${fmtDate(date)}` : undefined}>{ageLabel(date)}</span>;
}

// Forward-looking counterpart to AgeChip. AgeChip clamps future dates to "today", which
// silently misreads a due date or find-by date; this renders "in Nd" (or overdue via the
// stale treatment) instead. Same mono/micro form, no decay ramp — the future doesn't age.
export function DueChip({ date }) {
  if (!date) return null;
  const due = new Date(date.slice(0, 10) + "T00:00:00");
  if (isNaN(due)) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = Math.round((due.getTime() - today.getTime()) / 86400000);
  const label = days < 0 ? `${-days}d over` : days === 0 ? "today" : days < 21 ? `in ${days}d` : days < 84 ? `in ${Math.round(days / 7)}w` : `in ${Math.round(days / 30)}mo`;
  return <span className={"age " + (days < 0 ? "age-stale" : "age-fresh")} title={`due ${fmtDate(date)}`}>{label}</span>;
}

// The one Loading treatment: quiet, left-aligned, consistent copy.
export function Loading({ what }) {
  return <div className="subtle" style={{ padding: 12 }}>Loading{what ? ` ${what}` : ""}…</div>;
}

// The unknown treatment: cross-hatched tint + "Unknown" + the age chip that explains why.
// For a metric-derived indicator whose inputs passed their freshness threshold — never a
// carried-forward last value (§7, and the trust boundary in CLAUDE.md).
export function Unknown({ since }) {
  return (
    <span className="unknown-chip" title="Inputs are stale — value unknown, not carried forward">
      <span className="unknown-hatch" aria-hidden="true" />
      Unknown{since && <span className="age age-stale" style={{ marginLeft: 6 }}>{ageLabel(since)}</span>}
    </span>
  );
}

// Object-type display labels (shared by the command palette and global search).
export const TYPE_LABEL = {
  account: "account", program: "program", person: "person", interaction: "interaction",
  commitment: "commitment", risk: "risk", issue: "issue", decision: "decision", task: "task",
  milestone: "milestone", value_story: "value story", expansion_opportunity: "expansion",
  capture_inbox_item: "inbox note", scope_change: "scope change",
  whitespace_cell: "whitespace cell", value_target: "value target", funding_pool: "funding pool",
  operational_agreement: "operational agreement", growth_plan_line: "growth plan line",
  signal_episode: "signal", calendar_event: "calendar", org_change_flag: "org change",
  comms_sequence: "comms sequence",
};

// Command palette (Section 6: keyboard-first, cmd-K). Nav commands + account jumps + live search.
const NAV_COMMANDS = [
  ["Today", { dest: "today" }], ["Library", { dest: "library" }], ["Operations", { dest: "operations" }],
];

export function CommandPalette({ accounts, onClose, onNavigate, go, openAccount, openQuick, openCopilot }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [sel, setSel] = useState(0);
  const timer = useRef(null);

  const ql = q.trim().toLowerCase();
  const commands = [
    { kind: "action", label: "Log interaction", hint: "capture", run: () => { openQuick(); onClose(); } },
    { kind: "action", label: "Ask current scope", hint: "copilot", run: () => { openCopilot?.("fact"); onClose(); } },
    { kind: "action", label: "What changed", hint: "copilot", run: () => { openCopilot?.("changes", "What changed since last week?"); onClose(); } },
    { kind: "action", label: "Plan this week", hint: "copilot", run: () => { openCopilot?.("weekly", "What needs my attention this week?"); onClose(); } },
    ...NAV_COMMANDS.map(([label, dest]) => ({ kind: "nav", label, hint: "go to", run: () => { go(dest); onClose(); } })),
    ...accounts.map((a) => ({ kind: "account", label: a.name, hint: "account", run: () => { openAccount(a.id); onClose(); } })),
  ].filter((c) => !ql || c.label.toLowerCase().includes(ql));
  const items = [...commands, ...results.map((r) => ({ kind: "result", label: r.title, hint: (TYPE_LABEL[r.object_type] || r.object_type) + " · " + (r.account_name || ""), run: () => { onNavigate(r); onClose(); } }))];

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!ql) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      try { const r = await api.search(q); setResults(r.results.slice(0, 8)); } catch { /* ignore */ }
    }, 160);
    return () => timer.current && clearTimeout(timer.current);
  }, [q]);
  useEffect(() => { setSel(0); }, [q, results.length]);

  function onKey(e) {
    if (e.key === "Escape") { onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && items[sel]) { e.preventDefault(); items[sel].run(); }
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="palette">
        <div className="card" style={{ boxShadow: "var(--shadow-panel)", overflow: "hidden" }}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            placeholder="Type a command or search…" role="combobox" aria-expanded="true" aria-autocomplete="list"
            aria-controls="palette-listbox" aria-activedescendant={items[sel] ? `palette-opt-${sel}` : undefined}
            style={{ width: "100%", border: 0, borderBottom: "1px solid var(--line-hairline)", padding: "12px 16px", fontSize: "var(--t-body-lg)", outline: "none", background: "var(--bg-surface)" }} />
          <div style={{ maxHeight: 360, overflowY: "auto" }} role="listbox" id="palette-listbox" aria-label="Commands and results">
            {items.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No matches.</div> :
              items.map((it, i) => (
                <div key={it.kind + it.label + i} onMouseEnter={() => setSel(i)} onClick={it.run}
                  role="option" id={`palette-opt-${i}`} aria-selected={i === sel}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 16px", cursor: "pointer",
                    background: i === sel ? "var(--accent-tint)" : "transparent" }}>
                  <span style={{ flex: 1, fontSize: "var(--t-body)", color: i === sel ? "var(--accent)" : "var(--ink-primary)" }}>{(it.label || "").slice(0, 64)}</span>
                  <span className="rowmeta">{it.hint}</span>
                </div>
              ))}
          </div>
          <div className="rowmeta" style={{ padding: "6px 16px", borderTop: "1px solid var(--line-hairline)" }}>↑↓ move · ↵ open · esc close</div>
        </div>
      </div>
    </>
  );
}
