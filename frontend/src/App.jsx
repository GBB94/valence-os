import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import { ToastProvider } from "./ui";
import Accounts from "./views/Accounts";
import AccountDetail from "./views/AccountDetail";
import ProgramDetail from "./views/ProgramDetail";
import Inbox from "./views/Inbox";
import QuickEntry from "./views/QuickEntry";

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function Shell() {
  const [accounts, setAccounts] = useState([]);
  const [view, setView] = useState({ name: "accounts" });
  const [q, setQ] = useState("");
  const [quick, setQuick] = useState(null); // {accountId, programId} | null
  const [inboxCount, setInboxCount] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const loadAccounts = useCallback(async () => {
    const rows = await api.accounts();
    // decorate with program counts for the list (one call each is fine at this scale)
    const withCounts = await Promise.all(
      rows.map(async (a) => {
        try { const d = await api.account(a.id); return { ...a, program_count: d.programs.length }; }
        catch { return a; }
      })
    );
    setAccounts(withCounts);
  }, []);

  const refreshInbox = useCallback(async () => {
    try { const rows = await api.inbox("untriaged"); setInboxCount(rows.length); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadAccounts(); refreshInbox(); }, [loadAccounts, refreshInbox]);

  const bump = () => setReloadKey((k) => k + 1);
  const onSaved = () => { bump(); refreshInbox(); loadAccounts(); };

  const filtered = q
    ? accounts.filter((a) => a.name.toLowerCase().includes(q.toLowerCase()))
    : accounts;

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">Account OS <small>v0.1</small></div>
        <div className="nav">
          <div className="nav-label">Portfolio</div>
          <button className={"nav-item" + (view.name === "home" ? " active" : "")} onClick={() => setView({ name: "home" })}>
            Portfolio home
          </button>
          <button className={"nav-item" + (view.name === "inbox" ? " active" : "")} onClick={() => setView({ name: "inbox" })}>
            Capture inbox {inboxCount != null && <span className="muted">{inboxCount}</span>}
          </button>

          <div className="nav-label">Accounts</div>
          <button className={"nav-item" + (view.name === "accounts" ? " active" : "")} onClick={() => setView({ name: "accounts" })}>
            All accounts <span className="muted">{accounts.length}</span>
          </button>
          {filtered.map((a) => (
            <button
              key={a.id}
              className={"nav-item" + (view.name === "account" && view.accountId === a.id ? " active" : "")}
              onClick={() => setView({ name: "account", accountId: a.id })}
              title={a.name}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
            </button>
          ))}

          <div className="nav-label">Later slices</div>
          <button className="nav-item" style={{ color: "var(--text-3)" }} onClick={() => setView({ name: "later", which: "Execution board", slice: "v0.2" })}>Execution</button>
          <button className="nav-item" style={{ color: "var(--text-3)" }} onClick={() => setView({ name: "later", which: "History timeline", slice: "v0.4" })}>History</button>
        </div>
      </nav>

      <div className="main">
        <div className="topbar">
          <input
            placeholder="Search accounts…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button className="btn primary" onClick={() => setQuick({})}>Log interaction</button>
          <div className="who">Sam Rivera · single editor</div>
        </div>

        <div className="content">
          {view.name === "accounts" && (
            <Accounts accounts={filtered} onOpen={(id) => setView({ name: "account", accountId: id })} onChanged={loadAccounts} />
          )}
          {view.name === "account" && (
            <>
              <div className="crumb"><button onClick={() => setView({ name: "accounts" })}>Accounts</button> ›</div>
              <AccountDetail
                accountId={view.accountId}
                reloadKey={reloadKey}
                onOpenProgram={(pid) => setView({ name: "program", programId: pid, accountId: view.accountId })}
                onQuickEntry={(accountId) => setQuick({ accountId })}
              />
            </>
          )}
          {view.name === "program" && (
            <>
              <div className="crumb">
                <button onClick={() => setView({ name: "accounts" })}>Accounts</button> ›{" "}
                <button onClick={() => setView({ name: "account", accountId: view.accountId })}>Account</button> ›
              </div>
              <ProgramDetail
                programId={view.programId}
                reloadKey={reloadKey}
                onQuickEntry={(accountId, programId) => setQuick({ accountId, programId })}
              />
            </>
          )}
          {view.name === "inbox" && <Inbox reloadKey={reloadKey} onCountChange={setInboxCount} />}
          {view.name === "home" && <PortfolioPlaceholder inboxCount={inboxCount} onInbox={() => setView({ name: "inbox" })} />}
          {view.name === "later" && <Placeholder which={view.which} slice={view.slice} />}
        </div>
      </div>

      {quick && (
        <QuickEntry
          accounts={accounts}
          preAccount={quick.accountId}
          preProgram={quick.programId}
          onClose={() => setQuick(null)}
          onSaved={onSaved}
        />
      )}
    </div>
  );
}

function PortfolioPlaceholder({ inboxCount, onInbox }) {
  return (
    <div>
      <h1>Portfolio home</h1>
      <div className="subtle" style={{ marginBottom: 16 }}>The ranked, explainable attention queue is built in v0.3.</div>
      <div className="placeholder">
        <p>The morning queue — overdue commitments, blockers, at-risk milestones, untriaged notes, stale relationships, open tasks — arrives in <strong>v0.3</strong>, once execution objects (v0.2) exist to rank.</p>
        <p style={{ marginBottom: 0 }}>
          What works today from v0.1:{" "}
          <button className="btn small" onClick={onInbox}>Capture inbox{inboxCount != null ? ` (${inboxCount})` : ""}</button>
        </p>
      </div>
    </div>
  );
}

function Placeholder({ which, slice }) {
  return (
    <div>
      <h1>{which}</h1>
      <div className="placeholder">
        <p style={{ marginBottom: 0 }}>{which} arrives in <strong>{slice}</strong>. Not scaffolded ahead of its slice, per the build order.</p>
      </div>
    </div>
  );
}
