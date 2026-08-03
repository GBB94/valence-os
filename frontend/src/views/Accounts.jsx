import { useMemo, useState } from "react";
import { api } from "../api";
import { Empty, SegTabs, useToast } from "../ui";
import Onboarding from "./Onboarding";
import PortfolioAnalytics from "./PortfolioAnalytics";
import PortfolioInternal from "./PortfolioInternal";
import { SavedViewBar } from "../SavedViewControls";
import { useSavedViews } from "../useSavedViews";

const ACCOUNT_VIEWS = [
  { id: "all", label: "All accounts", state: { query: "", risk: "all", sort: "name" } },
  { id: "needs-attention", label: "Needs attention", state: { query: "", risk: "any", sort: "name" } },
  { id: "commercial-risk", label: "Commercial risk", state: { query: "", risk: "commercial", sort: "name" } },
  { id: "delivery-risk", label: "Delivery risk", state: { query: "", risk: "delivery", sort: "name" } },
];

const RISK_STATUSES = new Set(["at_risk", "off_track"]);
const STATUS_RANK = { off_track: 0, at_risk: 1, unknown: 2, on_track: 3 };
const ACCOUNT_RISK_KEYS = new Set(["all", "any", "commercial", "delivery"]);
const ACCOUNT_SORT_KEYS = new Set(["name", "commercial", "delivery"]);
function normalizeAccountView(state = {}) {
  return {
    query: typeof state.query === "string" ? state.query : "",
    risk: ACCOUNT_RISK_KEYS.has(state.risk) ? state.risk : "all",
    sort: ACCOUNT_SORT_KEYS.has(state.sort) ? state.sort : "name",
  };
}

export default function Accounts({ accounts, onOpen, onChanged, viewId, onViewChange }) {
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [ctx, setCtx] = useState("");
  const [onboarding, setOnboarding] = useState(null); // the just-created account being onboarded
  const [view, setView] = useState("accounts");
  const views = useSavedViews({
    surface: "accounts", builtIns: ACCOUNT_VIEWS, defaultId: "all", requestedId: viewId, onActivate: onViewChange,
    normalizeState: normalizeAccountView,
  });

  const visibleAccounts = useMemo(() => {
    const query = views.state.query.trim().toLowerCase();
    const matchesRisk = (account) => {
      const delivery = RISK_STATUSES.has(account.delivery_status);
      const commercial = RISK_STATUSES.has(account.commercial_status);
      if (views.state.risk === "delivery") return delivery;
      if (views.state.risk === "commercial") return commercial;
      if (views.state.risk === "any") return delivery || commercial;
      return true;
    };
    return accounts.filter((account) => matchesRisk(account) && (!query ||
      [account.name, account.short_context].filter(Boolean).some((value) => value.toLowerCase().includes(query))))
      .sort((a, b) => {
        if (views.state.sort === "delivery" || views.state.sort === "commercial") {
          const key = `${views.state.sort}_status`;
          const difference = (STATUS_RANK[a[key]] ?? 4) - (STATUS_RANK[b[key]] ?? 4);
          if (difference) return difference;
        }
        return a.name.localeCompare(b.name);
      });
  }, [accounts, views.state]);

  async function create() {
    if (!name.trim()) return;
    try {
      const a = await api.createAccount({ name: name.trim(), short_context: ctx || null });
      toast("Account created");
      setName(""); setCtx(""); setAdding(false);
      onChanged?.();
      setOnboarding(a);  // §1 — creating an account triggers the guided onboarding flow
    } catch (e) {
      toast(e.message, "err");
    }
  }

  async function importFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const bundle = JSON.parse(await file.text());
      const r = await api.importAccount(bundle);
      toast("Account restored");
      onChanged?.();
      onOpen(r.account_id);
    } catch (err) {
      toast(err.message?.includes("already exists") ? "That account already exists here" : (err.message || "Import failed"), "err");
    }
  }

  return (
    <div>
      <div className="actions" style={{ marginBottom: 16 }}>
        <h1>Accounts</h1>
        <div className="spacer" />
        <label className="btn" style={{ cursor: "pointer" }}>
          Import
          <input type="file" accept="application/json" style={{ display: "none" }} onChange={importFile} />
        </label>
        <button className={"btn" + (adding ? " selected" : "")} aria-pressed={adding} onClick={() => setAdding((v) => !v)}>New account</button>
      </div>

      <div style={{ marginBottom: 14 }}><SegTabs tabs={[["accounts", "Book"], ["analytics", "Portfolio analytics"], ["internal", "Internal"]]} value={view} onChange={setView} /></div>

      {view === "internal" ? <PortfolioInternal onOpen={onOpen} /> : view === "analytics" ? <PortfolioAnalytics /> : <>

      <SavedViewBar model={views}>
        <label className="view-filter">
          <span className="rowmeta">Status</span>
          <select aria-label="Filter accounts by status" value={views.state.risk}
            onChange={(event) => views.setState((current) => ({ ...current, risk: event.target.value }))}>
            <option value="all">All statuses</option>
            <option value="any">Needs attention</option>
            <option value="commercial">Commercial risk</option>
            <option value="delivery">Delivery risk</option>
          </select>
        </label>
        <label className="view-filter">
          <span className="rowmeta">Sort</span>
          <select aria-label="Sort accounts" value={views.state.sort}
            onChange={(event) => views.setState((current) => ({ ...current, sort: event.target.value }))}>
            <option value="name">Account name</option>
            <option value="commercial">Commercial status</option>
            <option value="delivery">Delivery status</option>
          </select>
        </label>
        <input aria-label="Search accounts" placeholder="Search accounts…" value={views.state.query}
          onChange={(event) => views.setState((current) => ({ ...current, query: event.target.value }))} />
      </SavedViewBar>

      {adding && (
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <div className="grid2">
            <div className="field">
              <label>Name <span className="req">*</span></label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Enterprise name (mock)" autoFocus />
            </div>
            <div className="field">
              <label>Short context</label>
              <input value={ctx} onChange={(e) => setCtx(e.target.value)} placeholder="One line" />
            </div>
          </div>
          <div className="actions">
            <button className="btn primary" onClick={create}>Create account</button>
            <button className="btn" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="card">
        {accounts.length === 0 ? (
          <Empty title="No accounts yet">Create your first account to start capturing.</Empty>
        ) : visibleAccounts.length === 0 ? (
          <Empty title="No matching accounts">Change this view's status or search filters.</Empty>
        ) : (
          <table>
            <thead>
              <tr><th scope="col">Account</th><th scope="col">Context</th><th scope="col" style={{ width: 130 }}>Delivery</th><th scope="col" style={{ width: 130 }}>Commercial</th><th scope="col" className="num" style={{ width: 90 }}>Programs</th></tr>
            </thead>
            <tbody>
              {visibleAccounts.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => onOpen(a.id)}>
                  <td><strong>{a.name}</strong></td>
                  <td className="subtle">{a.short_context || <span className="rowmeta">—</span>}</td>
                  <td><AccountStatus value={a.delivery_status} /></td>
                  <td><AccountStatus value={a.commercial_status} /></td>
                  <td className="rowmeta num">{a.program_count ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      </>}

      {onboarding && (
        <Onboarding
          account={onboarding}
          onClose={() => setOnboarding(null)}
          onDone={() => { onChanged?.(); onOpen(onboarding.id); }}
        />
      )}
    </div>
  );
}

function AccountStatus({ value }) {
  const label = (value || "unknown").replaceAll("_", " ");
  const mark = value === "on_track" ? "ok" : value === "at_risk" ? "warn" : value === "off_track" ? "risk" : "unknown";
  return <span className="state-badge"><span className={`state-mark ${mark}`} aria-hidden="true" />{label}</span>;
}
