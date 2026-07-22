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

export function PhaseBadge({ phase }) {
  return <span className="badge phase">{phase}</span>;
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
