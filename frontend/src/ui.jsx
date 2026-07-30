import { createContext, useContext, useState, useCallback } from "react";

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
