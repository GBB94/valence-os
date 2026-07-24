import { useEffect, useState, useCallback, useRef } from "react";
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
import StakeholderGraph from "./views/StakeholderGraph";
import Extraction from "./views/Extraction";
import Plays from "./views/Plays";

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
  const [quick, setQuick] = useState(null); // {accountId, programId} | null
  const [inboxCount, setInboxCount] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [execAccount, setExecAccount] = useState(null);
  const [histAccount, setHistAccount] = useState(null);
  const [commAccount, setCommAccount] = useState(null);
  const [tlAccount, setTlAccount] = useState(null);
  const [valAccount, setValAccount] = useState(null);
  const [qbrAccount, setQbrAccount] = useState(null);
  const [graphAccount, setGraphAccount] = useState(null);
  const [exAccount, setExAccount] = useState(null);
  const [notifs, setNotifs] = useState({ notifications: [], unread: 0 });
  const [showNotifs, setShowNotifs] = useState(false);

  const refreshNotifs = useCallback(async () => {
    try { setNotifs(await api.notifications()); } catch { /* ignore */ }
  }, []);
  useEffect(() => { refreshNotifs(); }, [refreshNotifs, reloadKey]);

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

  // Navigate to a global-search result: open its program if it has one, else its account.
  function navigateToResult(r) {
    if (r.object_type === "program" && r.object_id) setView({ name: "program", programId: r.object_id, accountId: r.account_id });
    else if (r.program_id) setView({ name: "program", programId: r.program_id, accountId: r.account_id });
    else if (r.account_id) setView({ name: "account", accountId: r.account_id });
  }

  const filtered = accounts;

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">Valence OS <small>v0.1</small></div>
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
          <button className={"nav-item" + (view.name === "graph" ? " active" : "")} onClick={() => setView({ name: "graph" })}>Stakeholder map</button>
          <button className={"nav-item" + (view.name === "history" ? " active" : "")} onClick={() => setView({ name: "history" })}>History</button>

          <div className="nav-label">Data &amp; evidence</div>
          <button className={"nav-item" + (view.name === "metrics" ? " active" : "")} onClick={() => setView({ name: "metrics" })}>Metrics</button>
          <button className={"nav-item" + (view.name === "value" ? " active" : "")} onClick={() => setView({ name: "value" })}>Value library</button>

          <div className="nav-label">AI &amp; automation</div>
          <button className={"nav-item" + (view.name === "extraction" ? " active" : "")} onClick={() => setView({ name: "extraction" })}>Transcript extraction</button>
          <button className={"nav-item" + (view.name === "plays" ? " active" : "")} onClick={() => setView({ name: "plays" })}>Plays</button>

          <div className="nav-label">Output</div>
          <button className={"nav-item" + (view.name === "team-update" ? " active" : "")} onClick={() => setView({ name: "team-update" })}>Weekly team update</button>
          <button className={"nav-item" + (view.name === "qbr" ? " active" : "")} onClick={() => setView({ name: "qbr" })}>QBR generator</button>
          <button className={"nav-item" + (view.name === "operations" ? " active" : "")} onClick={() => setView({ name: "operations" })}>Operations</button>
        </div>
      </nav>

      <div className="main">
        <div className="topbar">
          <GlobalSearch onNavigate={navigateToResult} reloadKey={reloadKey} />
          <button className="btn primary" onClick={() => setQuick({})}>Log interaction</button>
          <div style={{ position: "relative" }}>
            <button className="btn" onClick={() => setShowNotifs((v) => !v)} title="Notifications">
              🔔{notifs.unread > 0 && <span style={{ marginLeft: 4, color: "var(--risk)", fontWeight: 700 }}>{notifs.unread}</span>}
            </button>
            {showNotifs && (
              <div className="card" style={{ position: "absolute", right: 0, top: 36, width: 340, zIndex: 30, maxHeight: 380, overflowY: "auto" }}>
                <div className="card-h"><h3>Notifications</h3></div>
                {notifs.notifications.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>Nothing yet.</div> :
                  notifs.notifications.map((n) => (
                    <div key={n.id} style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)", opacity: n.read ? 0.5 : 1 }}>
                      <div style={{ fontSize: 12 }}>{n.message}</div>
                      <div className="actions"><span className="rowmeta">{n.created_at?.slice(0, 16).replace("T", " ")}</span><div className="spacer" />
                        {!n.read && <button className="btn small ghost" onClick={async () => { await api.readNotification(n.id); refreshNotifs(); }}>Mark read</button>}</div>
                    </div>
                  ))}
              </div>
            )}
          </div>
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
          {view.name === "graph" && (
            <StakeholderGraph accounts={accounts} accountId={graphAccount || accounts[0]?.id} setAccountId={setGraphAccount} reloadKey={reloadKey} />
          )}
          {view.name === "metrics" && <Metrics reloadKey={reloadKey} />}
          {view.name === "value" && (
            <ValueLibrary accounts={accounts} accountId={valAccount || accounts[0]?.id} setAccountId={setValAccount} reloadKey={reloadKey} />
          )}
          {view.name === "qbr" && (
            <QBR accounts={accounts} accountId={qbrAccount || accounts[0]?.id} setAccountId={setQbrAccount} reloadKey={reloadKey} />
          )}
          {view.name === "operations" && <Operations reloadKey={reloadKey} />}
          {view.name === "extraction" && (
            <Extraction accounts={accounts} accountId={exAccount || accounts[0]?.id} setAccountId={setExAccount} reloadKey={reloadKey} onApplied={onSaved} />
          )}
          {view.name === "plays" && <Plays reloadKey={reloadKey} onChanged={() => { bump(); refreshNotifs(); }} />}
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

const TYPE_LABEL = {
  account: "account", program: "program", person: "person", interaction: "interaction",
  commitment: "commitment", risk: "risk", issue: "issue", decision: "decision", task: "task",
  milestone: "milestone", value_story: "value story", expansion_opportunity: "expansion",
  capture_inbox_item: "inbox note", scope_change: "scope change",
};

// Global full-text search (Section 8) — debounced, results dropdown, keyboard-dismissable.
function GlobalSearch({ onNavigate, reloadKey }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const boxRef = useRef(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!q.trim()) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      try { const r = await api.search(q); setResults(r.results); setOpen(true); } catch { /* ignore */ }
    }, 180);
    return () => timer.current && clearTimeout(timer.current);
  }, [q, reloadKey]);

  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function go(r) { onNavigate(r); setOpen(false); setQ(""); }

  return (
    <div ref={boxRef} style={{ position: "relative", flex: 1, maxWidth: 420 }}>
      <input
        placeholder="Search everything…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => q && setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); if (e.key === "Enter" && results[0]) go(results[0]); }}
        style={{ width: "100%" }}
      />
      {open && q.trim() && (
        <div className="card" style={{ position: "absolute", top: 34, left: 0, right: 0, zIndex: 40, maxHeight: 420, overflowY: "auto", boxShadow: "0 6px 20px rgba(0,0,0,.12)" }}>
          {results.length === 0 ? (
            <div className="rowmeta" style={{ padding: 12 }}>No matches for “{q}”.</div>
          ) : (
            results.map((r) => (
              <button key={r.object_type + r.object_id} onClick={() => go(r)}
                style={{ display: "block", width: "100%", textAlign: "left", border: 0, borderBottom: "1px solid var(--border)", background: "none", padding: "8px 12px", cursor: "pointer" }}
                onMouseDown={(e) => e.preventDefault()}>
                <div style={{ fontSize: 13 }}>
                  <span className="badge" style={{ marginRight: 6 }}>{TYPE_LABEL[r.object_type] || r.object_type}</span>
                  {(r.title || "").slice(0, 70)}
                </div>
                <div className="rowmeta">{r.account_name}{r.snippet ? ` · ${r.snippet}` : ""}</div>
              </button>
            ))
          )}
        </div>
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
