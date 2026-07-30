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
import MutualActionPlan from "./views/MutualActionPlan";
import Library from "./views/Library";
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

// Theme: three-state choice (System / Light / Dark), persisted. "System" tracks the OS
// preference live. The stored value is the CHOICE; resolveTheme() maps it to an applied theme.
const THEME_CYCLE = { system: "light", light: "dark", dark: "system" };
const THEME_ICON = { system: "◐", light: "☀", dark: "☾" };
const THEME_LABEL = { system: "System", light: "Light", dark: "Dark" };

function getStoredThemeChoice() {
  try {
    const s = localStorage.getItem("valence-theme");
    if (s === "system" || s === "light" || s === "dark") return s;
  } catch { /* ignore */ }
  return "system";
}
function resolveTheme(choice) {
  if (choice === "system") {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return choice;
}

function Shell() {
  const [accounts, setAccounts] = useState([]);
  const [view, setView] = useState({ name: "home" });
  const [quick, setQuick] = useState(null); // {accountId, programId} | null
  const [palette, setPalette] = useState(false);
  const [inboxCount, setInboxCount] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [execAccount, setExecAccount] = useState(null);
  const [histAccount, setHistAccount] = useState(null);
  const [commAccount, setCommAccount] = useState(null);
  const [tlAccount, setTlAccount] = useState(null);
  const [valAccount, setValAccount] = useState(null);
  const [qbrAccount, setQbrAccount] = useState(null);
  const [mapAccount, setMapAccount] = useState(null);
  const [graphAccount, setGraphAccount] = useState(null);
  const [exAccount, setExAccount] = useState(null);
  const [notifs, setNotifs] = useState({ notifications: [], unread: 0 });
  const [showNotifs, setShowNotifs] = useState(false);
  const [theme, setTheme] = useState(getStoredThemeChoice);

  useEffect(() => {
    try { localStorage.setItem("valence-theme", theme); } catch { /* ignore */ }
    const apply = () => { document.documentElement.dataset.theme = resolveTheme(theme); };
    apply();
    if (theme === "system" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [theme]);

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

  // cmd-K / ctrl-K opens the command palette (Section 6: keyboard-first).
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
          <button className={"nav-item" + (view.name === "library" ? " active" : "")} onClick={() => setView({ name: "library" })}>Files &amp; context</button>

          <div className="nav-label">Data &amp; evidence</div>
          <button className={"nav-item" + (view.name === "metrics" ? " active" : "")} onClick={() => setView({ name: "metrics" })}>Metrics</button>
          <button className={"nav-item" + (view.name === "value" ? " active" : "")} onClick={() => setView({ name: "value" })}>Value library</button>

          <div className="nav-label">AI &amp; automation</div>
          <button className={"nav-item" + (view.name === "extraction" ? " active" : "")} onClick={() => setView({ name: "extraction" })}>Transcript extraction</button>
          <button className={"nav-item" + (view.name === "plays" ? " active" : "")} onClick={() => setView({ name: "plays" })}>Plays</button>

          <div className="nav-label">Output</div>
          <button className={"nav-item" + (view.name === "map" ? " active" : "")} onClick={() => setView({ name: "map" })}>Mutual action plan</button>
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
          <PageHelp name={view.name} />
          <button className="btn small" onClick={() => setTheme((t) => THEME_CYCLE[t])}
            title={`Theme: ${THEME_LABEL[theme]} — click to change`} aria-label={`Theme: ${THEME_LABEL[theme]}. Click to change.`}>
            {THEME_ICON[theme]}
          </button>
          <button className="btn small" onClick={() => setPalette(true)} title="Command palette">⌘K</button>
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
          {view.name === "map" && (
            <MutualActionPlan accounts={accounts} accountId={mapAccount || accounts[0]?.id} setAccountId={setMapAccount} reloadKey={reloadKey} />
          )}
          {view.name === "library" && <Library reloadKey={reloadKey} />}
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

      {palette && (
        <CommandPalette
          accounts={accounts}
          onClose={() => setPalette(false)}
          onNavigate={navigateToResult}
          setView={setView}
          openQuick={() => setQuick({})}
        />
      )}
    </div>
  );
}

// One-line "what is this page for" help text per view, shown as a topbar ⓘ tooltip.
// Grounded in the scoping doc; keep trust boundaries visible (promoted-only, stale=unknown, etc.).
const PAGE_INFO = {
  home: { title: "Portfolio home", body: "Your attention queue: a rules-based, explainable ranking of what needs you across every account — and why each item surfaced. Start your day here." },
  inbox: { title: "Capture inbox", body: "Untriaged notes from quick capture wait here. Convert each into a commitment, risk, issue, decision, task, or milestone — no retyping." },
  accounts: { title: "All accounts", body: "Every account you run. Open one to see its programs, stakeholders, execution, and commercial picture." },
  account: { title: "Account", body: "One account end to end: its programs, stakeholders, and delivery + commercial status (each with rationale), plus recent interactions." },
  program: { title: "Program", body: "One bounded deployment or commercial motion — its phase, scope, success criteria, stakeholders, and execution items." },
  execution: { title: "Execution", body: "Commitments, tasks, risks, issues, decisions, and milestones across a program, with owners and due dates. ★ promotes an item onto the client-facing Mutual Action Plan." },
  commercial: { title: "Commercial", body: "Expansion opportunities (staged budget) and contract versions — the canonical copy plus your operational overlay. Renewal and notice dates live here." },
  timeline: { title: "Timeline", body: "A swimlane view of interactions, commitments, milestones, and deployment moments over time for one account." },
  graph: { title: "Stakeholder map", body: "The stakeholder network for an account — stance, influence, and relationships. Every assessment carries a date and an evidence note." },
  history: { title: "History", body: "The full interaction and change history for an account, filterable by person or program. Last-touch dates are derived here, never hand-edited." },
  library: { title: "Files & context", body: "Link-first, tagged, searchable pointers to source material (decks, transcripts, CRM records), plus which records cite each one. Points to originals, never copies." },
  metrics: { title: "Metrics", body: "Metrics ingested from the Data team — never recomputed. Freshness is tracked; stale figures render as unknown, not carried-forward good state." },
  value: { title: "Value library", body: "Documented wins and negative evidence for an account, each tied to a source. Feeds the QBR and team update." },
  extraction: { title: "Transcript extraction", body: "Paste a transcript to get proposed structured updates for per-item accept or reject. The backend is pluggable — currently the offline mock; no external LLM is wired." },
  plays: { title: "Plays", body: "Predefined trigger-and-response rules, each with an owner and due date. Evaluate to surface the plays whose conditions are now met." },
  map: { title: "Mutual action plan", body: "The client-facing joint plan for an account, assembled only from items you've promoted (★). Internal-only material never appears here." },
  "team-update": { title: "Weekly team update", body: "A one-click weekly internal status roll-up for the Valence team, generated from your captured work." },
  qbr: { title: "QBR generator", body: "Generates a client-facing quarterly business review for an account — built by construction from only client-safe, promoted material, with provenance on claims." },
  operations: { title: "Operations", body: "System health for this single-editor tool: failed imports, data freshness, backup/restore status, storage, and search-index health — so you know when something's broken without reading logs." },
};

function PageHelp({ name }) {
  const info = PAGE_INFO[name];
  if (!info) return null;
  return (
    <span className="pagehelp" tabIndex={0} role="note" aria-label={`About this page — ${info.title}: ${info.body}`}>
      <span className="pagehelp-icon" aria-hidden="true">i</span>
      <span className="pagehelp-tip" role="tooltip">
        <strong>{info.title}</strong>
        <span>{info.body}</span>
      </span>
    </span>
  );
}

const TYPE_LABEL = {
  account: "account", program: "program", person: "person", interaction: "interaction",
  commitment: "commitment", risk: "risk", issue: "issue", decision: "decision", task: "task",
  milestone: "milestone", value_story: "value story", expansion_opportunity: "expansion",
  capture_inbox_item: "inbox note", scope_change: "scope change",
};

// Command palette (Section 6: keyboard-first, cmd-K). Fuzzy commands + live search,
// arrow-key navigation, Enter to run, Esc to close.
const NAV_COMMANDS = [
  ["Portfolio home", { name: "home" }], ["Capture inbox", { name: "inbox" }],
  ["All accounts", { name: "accounts" }], ["Execution board", { name: "execution" }],
  ["Commercial", { name: "commercial" }], ["Timeline", { name: "timeline" }],
  ["Stakeholder map", { name: "graph" }], ["History", { name: "history" }],
  ["Metrics", { name: "metrics" }], ["Value library", { name: "value" }],
  ["Transcript extraction", { name: "extraction" }], ["Plays", { name: "plays" }],
  ["Weekly team update", { name: "team-update" }], ["QBR generator", { name: "qbr" }],
  ["Operations", { name: "operations" }],
];

function CommandPalette({ accounts, onClose, onNavigate, setView, openQuick }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [sel, setSel] = useState(0);
  const timer = useRef(null);

  // Build the item list: an action, nav commands + account jumps (fuzzy filtered), then search hits.
  const ql = q.trim().toLowerCase();
  const commands = [
    { kind: "action", label: "Log interaction", hint: "capture", run: () => { openQuick(); onClose(); } },
    ...NAV_COMMANDS.map(([label, view]) => ({ kind: "nav", label, hint: "go to", run: () => { setView(view); onClose(); } })),
    ...accounts.map((a) => ({ kind: "account", label: a.name, hint: "account", run: () => { setView({ name: "account", accountId: a.id }); onClose(); } })),
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
      <div style={{ position: "fixed", top: "12vh", left: "50%", transform: "translateX(-50%)", width: 560, maxWidth: "92vw", zIndex: 60 }}>
        <div className="card" style={{ boxShadow: "0 12px 40px rgba(0,0,0,.28)", overflow: "hidden" }}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            placeholder="Type a command or search…"
            style={{ width: "100%", border: 0, borderBottom: "1px solid var(--border)", padding: "12px 14px", fontSize: 15, outline: "none" }} />
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {items.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No matches.</div> :
              items.map((it, i) => (
                <div key={it.kind + it.label + i} onMouseEnter={() => setSel(i)} onClick={it.run}
                  style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", cursor: "pointer",
                    background: i === sel ? "var(--accent-weak)" : "transparent" }}>
                  <span style={{ flex: 1, fontSize: 13, color: i === sel ? "var(--accent)" : "var(--text)" }}>{(it.label || "").slice(0, 64)}</span>
                  <span className="rowmeta">{it.hint}</span>
                </div>
              ))}
          </div>
          <div className="rowmeta" style={{ padding: "6px 14px", borderTop: "1px solid var(--border)" }}>↑↓ move · ↵ open · esc close</div>
        </div>
      </div>
    </>
  );
}

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
