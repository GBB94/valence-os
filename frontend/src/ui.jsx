import { createContext, useContext, useState, useCallback, useEffect } from "react";

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

export function Card({ className = "", children, ...rest }) {
  return <div className={"card" + (className ? " " + className : "")} {...rest}>{children}</div>;
}

export function PhaseBadge({ phase }) {
  return <span className="badge phase">{phase}</span>;
}

// Screen header: title, optional right-aligned meta, optional action cluster.
export function PageHeader({ title, meta, children }) {
  return (
    <div className="actions" style={{ marginBottom: 12 }}>
      <h1>{title}</h1>
      <div className="spacer" />
      {meta && <span className="rowmeta">{meta}</span>}
      {children}
    </div>
  );
}

// Segmented tabs (inner selectors, filter groups). tabs: [[key, label, count?], …]
export function SegTabs({ tabs, value, onChange, kind = "tab" }) {
  const cls = kind === "chip" ? "filter-chip" : "tab";
  return (
    <div className={kind === "chip" ? "chiprow" : "tabstrip inner"} role="tablist">
      {tabs.map(([key, label, count]) => (
        <button key={key} role="tab" aria-selected={value === key}
          className={cls + (value === key ? " active" : "")} onClick={() => onChange(key)}>
          {label}{count != null && <span className="chip-count">{count}</span>}
        </button>
      ))}
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

export function StanceLabel({ stance }) {
  if (!stance) return <span className="rowmeta">—</span>;
  const dot = stance === "supporter" ? "ok" : stance === "skeptic" ? "risk" : "";
  return (
    <span className={"stance-" + stance}>
      <span className={"dot " + dot} /> {stance}
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
export function SlideOver({ title, onClose, children, footer }) {
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="slideover" role="dialog" aria-label={title}>
        <header>
          <h1>{title}</h1>
          <div className="spacer" />
          <button className="btn ghost" onClick={onClose}>Close</button>
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
