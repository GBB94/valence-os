import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import { ToastProvider } from "./ui";
import Accounts from "./views/Accounts";
import AccountDetail from "./views/AccountDetail";
import ProgramDetail from "./views/ProgramDetail";
import Inbox from "./views/Inbox";
import QuickEntry from "./views/QuickEntry";
import ExecutionBoard from "./views/ExecutionBoard";
import Queue from "./views/Queue";
import History from "./views/History";
import TeamUpdate from "./views/TeamUpdate";
import Commercial from "./views/Commercial";
import Timeline from "./views/Timeline";
import Metrics from "./views/Metrics";
import ValueLibrary from "./views/ValueLibrary";
import QBR from "./views/QBR";
import Operations from "./views/Operations";

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function Shell() {
  const [accounts, setAccounts] = useState([]);
  const [view, setView] = useState({ name: "home" });
  const [q, setQ] = useState("");
  const [quick, setQuick] = useState(null); // {accountId, programId} | null
  const [inboxCount, setInboxCount] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [execAccount, setExecAccount] = useState(null);
  const [histAccount, setHistAccount] = useState(null);
  const [commAccount, setCommAccount] = useState(null);
  const [tlAccount, setTlAccount] = useState(null);
  const [valAccount, setValAccount] = useState(null);
  const [qbrAccount, setQbrAccount] = useState(null);

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

          <div className="nav-label">Work</div>
          <button className={"nav-item" + (view.name === "execution" ? " active" : "")} onClick={() => setView({ name: "execution" })}>Execution</button>
          <button className={"nav-item" + (view.name === "commercial" ? " active" : "")} onClick={() => setView({ name: "commercial" })}>Commercial</button>
          <button className={"nav-item" + (view.name === "timeline" ? " active" : "")} onClick={() => setView({ name: "timeline" })}>Timeline</button>
          <button className={"nav-item" + (view.name === "history" ? " active" : "")} onClick={() => setView({ name: "history" })}>History</button>

          <div className="nav-label">Data &amp; evidence</div>
          <button className={"nav-item" + (view.name === "metrics" ? " active" : "")} onClick={() => setView({ name: "metrics" })}>Metrics</button>
          <button className={"nav-item" + (view.name === "value" ? " active" : "")} onClick={() => setView({ name: "value" })}>Value library</button>

          <div className="nav-label">Output</div>
          <button className={"nav-item" + (view.name === "team-update" ? " active" : "")} onClick={() => setView({ name: "team-update" })}>Weekly team update</button>
          <button className={"nav-item" + (view.name === "qbr" ? " active" : "")} onClick={() => setView({ name: "qbr" })}>QBR generator</button>
          <button className={"nav-item" + (view.name === "operations" ? " active" : "")} onClick={() => setView({ name: "operations" })}>Operations</button>
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
          {view.name === "inbox" && <Inbox reloadKey={reloadKey} onCountChange={setInboxCount} onConverted={onSaved} />}
          {view.name === "execution" && (
            <ExecutionBoard
              accounts={accounts}
              accountId={execAccount || accounts[0]?.id}
              setAccountId={setExecAccount}
              reloadKey={reloadKey}
              onChanged={onSaved}
            />
          )}
          {view.name === "home" && (
            <Queue
              reloadKey={reloadKey}
              onOpenAccount={(id) => setView({ name: "account", accountId: id })}
              onChanged={onSaved}
            />
          )}
          {view.name === "history" && (
            <History accounts={accounts} accountId={histAccount || accounts[0]?.id} setAccountId={setHistAccount} reloadKey={reloadKey} />
          )}
          {view.name === "commercial" && (
            <Commercial accounts={accounts} accountId={commAccount || accounts[0]?.id} setAccountId={setCommAccount} reloadKey={reloadKey} />
          )}
          {view.name === "timeline" && (
            <Timeline accounts={accounts} accountId={tlAccount || accounts[0]?.id} setAccountId={setTlAccount} reloadKey={reloadKey} />
          )}
          {view.name === "metrics" && <Metrics reloadKey={reloadKey} />}
          {view.name === "value" && (
            <ValueLibrary accounts={accounts} accountId={valAccount || accounts[0]?.id} setAccountId={setValAccount} reloadKey={reloadKey} />
          )}
          {view.name === "qbr" && (
            <QBR accounts={accounts} accountId={qbrAccount || accounts[0]?.id} setAccountId={setQbrAccount} reloadKey={reloadKey} />
          )}
          {view.name === "operations" && <Operations reloadKey={reloadKey} />}
          {view.name === "team-update" && <TeamUpdate reloadKey={reloadKey} />}
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
