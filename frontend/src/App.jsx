import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "./api";
import { ToastProvider, fmtDate, Tooltip, SegTabs, AgeChip, ageDays, CommandPalette, TYPE_LABEL, Card } from "./ui";
import Accounts from "./views/Accounts";
import AccountDetail from "./views/AccountDetail";
import ProgramDetail from "./views/ProgramDetail";
import Ledger from "./views/Ledger";
import QuickEntry from "./views/QuickEntry";
import Queue from "./views/Queue";
import TeamUpdate from "./views/TeamUpdate";
import MutualActionPlan from "./views/MutualActionPlan";
import Library from "./views/Library";
import Commercial from "./views/Commercial";
import Timeline from "./views/Timeline";
import Metrics from "./views/Metrics";
import ValueLibrary from "./views/ValueLibrary";
import Artifacts from "./views/Artifacts";
import Campaigns from "./views/Campaigns";
import QBR from "./views/QBR";
import Operations from "./views/Operations";
import People from "./views/People";
import Checklists from "./views/Checklists";
import CalendarPanel from "./views/CalendarPanel";
import Comms from "./views/Comms";
import Extraction from "./views/Extraction";
import Plays from "./views/Plays";
import Internal from "./views/Internal";
import CopilotPanel from "./views/CopilotPanel";
import AdoptionComms from "./views/AdoptionComms";

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

// The account workspace tabs (DESIGN-GUIDE §2.2). Phase C builds the shell + tab strip and
// slots today's views into each tab as an interim; Phase D merges them (Ledger, etc.).
const WORKSPACE_TABS = [
  ["overview", "Overview"], ["ledger", "Ledger"], ["people", "People"],
  ["plan", "Plan"], ["commercial", "Commercial"], ["evidence", "Evidence"], ["outputs", "Outputs"],
  ["internal", "Internal"],
];

// Short "what is this" help text, keyed by destination or account-tab (topbar ⓘ).
const INFO = {
  today: "Cross-account attention queue — a ranked, explainable list of what needs you and why. This screen exists to be emptied.",
  library: "Link-first, tagged, searchable source references and files, with the records that cite each. Points to originals, never copies.",
  operations: "System health for this single-editor tool: imports, data freshness, backups, search-index health, and the plays engine.",
  overview: "Where this account stands right now: both statuses with rationale, the phase, and the top risks. Depth is one click away.",
  ledger: "One chronological record of everything on this account — interactions, commitments, tasks, decisions, risks, issues, and untriaged capture.",
  people: "The stakeholder network — stance, influence, relationships, and who has not been touched. Every assessment carries a date and evidence.",
  plan: "What is scheduled and what is gating: timeline, deployment moments, phase gates, and compliance lanes.",
  commercial: "Where the money is — expansion opportunities (staged budget), contract versions with your overlay, and the budget waterfall.",
  evidence: "What we can prove and how fresh the proof is: ingested metrics (stale renders unknown), benchmarks, and the value-story library.",
  outputs: "What we hand to someone else — QBR, weekly team update, and the client-facing mutual action plan. Client outputs include only promoted records.",
  internal: "The operating layer behind the account: forecast calls, internal asks, leadership reviews, and colleague coverage.",
};

function Shell() {
  const [accounts, setAccounts] = useState([]);
  // nav: { dest: 'today'|'account'|'library'|'operations', accountId?, tab?, programId? }
  const [nav, setNav] = useState({ dest: "today" });
  const [quick, setQuick] = useState(null);
  const [palette, setPalette] = useState(false);
  const [inboxCount, setInboxCount] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [notifs, setNotifs] = useState({ notifications: [], unread: 0 });
  const [showNotifs, setShowNotifs] = useState(false);
  const [theme, setTheme] = useState(getStoredThemeChoice);
  const [railCollapsed, setRailCollapsed] = useState(() => {
    try { return localStorage.getItem("valence-rail") === "1"; } catch { return false; }
  });
  const [density, setDensity] = useState(() => {
    try { return localStorage.getItem("valence-density") || "compact"; } catch { return "compact"; }
  });
  const [copilot, setCopilot] = useState(null);
  const copilotTriggerRef = useRef(null);
  const copilotReturnFocusRef = useRef(null);

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

  useEffect(() => {
    document.documentElement.dataset.density = density;
    try { localStorage.setItem("valence-density", density); } catch { /* ignore */ }
  }, [density]);
  useEffect(() => {
    try { localStorage.setItem("valence-rail", railCollapsed ? "1" : "0"); } catch { /* ignore */ }
  }, [railCollapsed]);
  useEffect(() => {
    // DESIGN-GUIDE §11: split-screen at ~900px collapses the rail to icons. Auto-collapse on
    // entering a narrow viewport; the operator can still re-expand explicitly.
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(max-width: 1000px)");
    const apply = () => { if (mq.matches) setRailCollapsed(true); };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const refreshNotifs = useCallback(async () => {
    try { setNotifs(await api.notifications()); } catch { /* ignore */ }
  }, []);
  useEffect(() => { refreshNotifs(); }, [refreshNotifs, reloadKey]);

  const loadAccounts = useCallback(async () => {
    const rows = await api.accounts();
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

  const capturePrefill = useCallback(() => {
    if (nav.dest === "account") return { accountId: nav.accountId, programId: nav.programId };
    return {};
  }, [nav]);

  // Keyboard: cmd/ctrl-K opens the palette; "c" opens capture from anywhere (Section 2.4).
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      const typing = ["input", "textarea", "select"].includes((t.tagName || "").toLowerCase()) || t.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); return; }
      if (!typing && !e.metaKey && !e.ctrlKey && !e.altKey && e.key.toLowerCase() === "c") {
        e.preventDefault(); setQuick(capturePrefill());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [capturePrefill]);

  const bump = () => setReloadKey((k) => k + 1);
  const onSaved = () => { bump(); refreshInbox(); loadAccounts(); };

  const openAccount = (id, tab = "overview") => setNav({ dest: "account", accountId: id, tab, programId: undefined });
  const setTab = (tab) => setNav((n) => ({ ...n, tab }));
  const setProgramFilter = (programId) => setNav((n) => ({ ...n, programId: programId || undefined }));

  const copilotScope = nav.dest === "account"
    ? (nav.programId
      ? { scope_type: "program", account_id: nav.accountId, program_id: nav.programId }
      : { scope_type: "account", account_id: nav.accountId })
    : { scope_type: "portfolio" };
  const openCopilot = useCallback((intent = "fact", question = "") => {
    copilotReturnFocusRef.current = document.activeElement;
    setCopilot({ intent, question });
  }, []);
  const closeCopilot = useCallback(() => {
    setCopilot(null);
    requestAnimationFrame(() => {
      const target = copilotReturnFocusRef.current;
      (target?.isConnected ? target : copilotTriggerRef.current)?.focus?.();
    });
  }, []);

  function navigateToResult(r) {
    if (r.object_type === "attention_item") { setNav({ dest: "today" }); return; }
    const acct = r.account_id || (r.object_type === "account" ? r.object_id : null);
    if (!acct) return;
    // route search hits into the most relevant workspace tab
    const tabByType = {
      person: "people", stakeholder_role: "people",
      commitment: "ledger", task: "ledger", decision: "ledger", risk: "ledger", issue: "ledger",
      interaction: "ledger", capture_inbox_item: "ledger",
      value_story: "evidence", expansion_opportunity: "commercial", scope_change: "plan",
      whitespace_cell: "commercial", population_segment: "commercial", population_view: "commercial",
      value_target: "commercial", metric_observation: "evidence", funding_pool: "commercial",
      operational_agreement: "commercial", growth_plan_line: "commercial",
      contract_version: "commercial", forecast_entry: "internal", forecast_change: "internal",
      status_assessment: "internal", status_change: "internal", internal_ask: "internal",
      ask_change: "internal", internal_roster: "internal", escalation: "internal",
      product_feedback: "internal", product_feedback_occurrence: "internal",
      signal_episode: "commercial", calendar_event: "plan", org_change_flag: "people",
      adoption_campaign: "plan", campaign_change: "plan", comms_sequence: "plan",
      generated_document: "outputs",
      commitment_change: "ledger", decision_change: "ledger", risk_change: "ledger",
      issue_change: "ledger", task_change: "ledger", milestone_change: "ledger",
      program: "overview", account: "overview",
    };
    openAccount(acct, tabByType[r.object_type] || "overview");
  }

  return (
    <div className={"shell" + (railCollapsed ? " rail-collapsed" : "")}>
      <Rail
        accounts={accounts}
        nav={nav}
        collapsed={railCollapsed}
        onToggleCollapse={() => setRailCollapsed((v) => !v)}
        inboxCount={inboxCount}
        go={setNav}
        openAccount={openAccount}
      />

      <div className="main">
        <div className="topbar">
          <Breadcrumb nav={nav} accounts={accounts} go={setNav} />
          <GlobalSearch onNavigate={navigateToResult} reloadKey={reloadKey} />
          <button className="btn primary small" onClick={() => setQuick(capturePrefill())} title="Log interaction (c)">Log interaction</button>
          <button ref={copilotTriggerRef} className="btn small" onClick={() => openCopilot("fact")} title="Ask grounded questions in the visible scope">Ask</button>
          <div style={{ position: "relative" }}>
            <button className="btn small" onClick={() => setShowNotifs((v) => !v)} title="Notifications" aria-label="Notifications">
              🔔{notifs.unread > 0 && <span style={{ marginLeft: 4, fontWeight: 600 }}>{notifs.unread}</span>}
            </button>
            {showNotifs && (
              <Card style={{ position: "absolute", right: 0, top: 34, width: 340, zIndex: 30, maxHeight: 380, overflowY: "auto", boxShadow: "var(--shadow-panel)" }}>
                <div className="card-h"><h3>Notifications</h3></div>
                {notifs.notifications.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>Nothing yet.</div> :
                  notifs.notifications.map((n) => (
                    <div key={n.id} style={{ padding: "8px 12px", borderBottom: "1px solid var(--line-hairline)", opacity: n.read ? 0.5 : 1 }}>
                      <div style={{ fontSize: "var(--t-small)" }}>{n.message}</div>
                      <div className="actions"><span className="rowmeta">{n.created_at?.slice(0, 16).replace("T", " ")}</span><div className="spacer" />
                        {!n.read && <button className="btn small ghost" onClick={async () => { await api.readNotification(n.id); refreshNotifs(); }}>Mark read</button>}</div>
                    </div>
                  ))}
              </Card>
            )}
          </div>
          <DensityToggle density={density} setDensity={setDensity} />
          <Tooltip text={INFO[nav.dest === "account" ? nav.tab : nav.dest]} />
          <button className="btn small" onClick={() => setPalette(true)} title="Command palette (⌘K)" aria-label="Command palette">⌘K</button>
          <button className="btn small" onClick={() => setTheme((t) => THEME_CYCLE[t])}
            title={`Theme: ${THEME_LABEL[theme]} — click to change`} aria-label={`Theme: ${THEME_LABEL[theme]}. Click to change.`}>
            {THEME_ICON[theme]}
          </button>
        </div>

        {nav.dest === "today" && (
          <div className="content">
            <Queue reloadKey={reloadKey} onOpenAccount={(id) => openAccount(id)} onChanged={onSaved} />
          </div>
        )}
        {nav.dest === "accounts" && (
          <div className="content">
            <Accounts accounts={accounts} onOpen={(id) => openAccount(id)} onChanged={loadAccounts} />
          </div>
        )}
        {nav.dest === "library" && <div className="content"><Library reloadKey={reloadKey} /></div>}
        {nav.dest === "operations" && (
          <div className="content">
            <Operations reloadKey={reloadKey} />
            <Plays reloadKey={reloadKey} onChanged={() => { bump(); refreshNotifs(); }} />
          </div>
        )}
        {nav.dest === "account" && (
          <AccountWorkspace
            key={nav.accountId}
            accounts={accounts}
            accountId={nav.accountId}
            tab={nav.tab}
            programId={nav.programId}
            reloadKey={reloadKey}
            setTab={setTab}
            setProgramFilter={setProgramFilter}
            openAccount={openAccount}
            onQuickEntry={(accountId, programId) => setQuick({ accountId, programId })}
            onSaved={onSaved}
            setInboxCount={setInboxCount}
            refreshNotifs={refreshNotifs}
            openCopilot={openCopilot}
          />
        )}
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
          go={setNav}
          openAccount={openAccount}
          openQuick={() => setQuick(capturePrefill())}
          openCopilot={openCopilot}
        />
      )}

      {copilot && <CopilotPanel scope={copilotScope}
        accountName={accounts.find((account) => account.id === copilotScope.account_id)?.name}
        starter={copilot} onClose={closeCopilot}
        onNavigateSource={(source) => {
          const type = source.record_type === "account_snapshot" ? "account" : source.record_type;
          navigateToResult({ object_type: type, object_id: source.record_id,
            account_id: source.account_id, program_id: source.program_id });
          closeCopilot();
        }} />}
    </div>
  );
}

// ---- Rail (240px, collapsible; three destinations + account list + Operations at the foot) ----
function Rail({ accounts, nav, collapsed, onToggleCollapse, inboxCount, go, openAccount }) {
  const item = (active, label, icon, onClick, badge) => (
    <button className={"rail-item" + (active ? " active" : "")} onClick={onClick} title={label}>
      <span className="rail-icon" aria-hidden="true">{icon}</span>
      {!collapsed && <span className="rail-label">{label}</span>}
      {!collapsed && badge != null && <span className="muted">{badge}</span>}
    </button>
  );
  return (
    <nav className="sidebar">
      <div className="brand">
        {!collapsed && <span>Valence OS</span>}
        <button className="rail-collapse" onClick={onToggleCollapse} title={collapsed ? "Expand" : "Collapse"} aria-label="Toggle sidebar">
          {collapsed ? "»" : "«"}
        </button>
      </div>
      <div className="nav">
        {item(nav.dest === "today", "Today", "◎", () => go({ dest: "today" }))}

        <button className={"rail-item" + (nav.dest === "accounts" ? " active" : "")} onClick={() => go({ dest: "accounts" })} title="All accounts">
          <span className="rail-icon" aria-hidden="true">▤</span>
          {!collapsed && <span className="rail-label">Accounts</span>}
          {!collapsed && <span className="muted">{accounts.length}</span>}
        </button>
        {accounts.map((a) => (
          <button
            key={a.id}
            className={"rail-item indent" + (nav.dest === "account" && nav.accountId === a.id ? " active" : "")}
            onClick={() => openAccount(a.id)}
            title={a.name}
          >
            <span className="rail-icon" aria-hidden="true">▪</span>
            {!collapsed && <span className="rail-label">{a.name}</span>}
          </button>
        ))}

        {item(nav.dest === "library", "Library", "❏", () => go({ dest: "library" }))}
      </div>
      <div className="rail-foot">
        {item(nav.dest === "operations", "Operations", "⚙", () => go({ dest: "operations" }))}
      </div>
    </nav>
  );
}

function Breadcrumb({ nav, accounts, go }) {
  const acct = accounts.find((a) => a.id === nav.accountId);
  const tabLabel = WORKSPACE_TABS.find(([k]) => k === nav.tab)?.[1];
  if (nav.dest === "today") return <div className="crumb-bar">Today</div>;
  if (nav.dest === "library") return <div className="crumb-bar">Library</div>;
  if (nav.dest === "operations") return <div className="crumb-bar">Operations</div>;
  return (
    <div className="crumb-bar">
      <button onClick={() => go({ dest: "accounts" })}>Accounts</button>
      <span className="crumb-sep">›</span>
      <span className="crumb-cur">{acct?.name || "Account"}</span>
      {tabLabel && <><span className="crumb-sep">·</span><span className="crumb-cur">{tabLabel}</span></>}
    </div>
  );
}

function DensityToggle({ density, setDensity }) {
  const next = density === "compact" ? "default" : "compact";
  return (
    <button className="btn small" onClick={() => setDensity(next)}
      title={`Row density: ${density} — click for ${next}`} aria-label={`Row density: ${density}. Click to change.`}>
      {density === "compact" ? "▤" : "▦"}
    </button>
  );
}

function Collapsible({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="collapsible">
      <button className="collapsible-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="rail-icon">{open ? "▾" : "▸"}</span> {title}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}

// ---- Account workspace: sticky context header + tab strip + tab content ----
function AccountWorkspace({ accounts, accountId, tab, programId, reloadKey, setTab, setProgramFilter, openAccount, onQuickEntry, onSaved, setInboxCount, refreshNotifs, openCopilot }) {
  const [detail, setDetail] = useState(null);
  const [renewal, setRenewal] = useState(null);

  useEffect(() => {
    if (!accountId) return;
    let live = true;
    api.account(accountId).then((d) => { if (live) setDetail(d); }).catch(() => {});
    api.contracts(accountId).then((cs) => {
      if (!live) return;
      const cur = (cs || []).find((c) => c.is_current) || (cs || [])[0];
      setRenewal(cur?.renewal_date || null);
    }).catch(() => setRenewal(null));
    return () => { live = false; };
  }, [accountId, reloadKey]);

  const programs = detail?.programs ?? [];
  const selProgram = programs.find((p) => p.id === programId) || null;
  const setAcct = (id) => openAccount(id, tab);

  return (
    <>
      <ContextHeader detail={detail} programs={programs} programId={programId} selProgram={selProgram} setProgramFilter={setProgramFilter} renewal={renewal} />
      <div className="tabstrip" role="tablist">
        {WORKSPACE_TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key}
            className={"tab" + (tab === key ? " active" : "")} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      <div className="content">
        {tab === "overview" && (
          <AccountDetail accountId={accountId} reloadKey={reloadKey}
            onOpenProgram={() => setTab("plan")} onQuickEntry={(aid) => onQuickEntry(aid, programId)} />
        )}
        {tab === "ledger" && (
          <div className="stack">
            <Ledger accountId={accountId} programId={programId} reloadKey={reloadKey} onChanged={onSaved} />
            <Collapsible title="Communications (email + recordings)">
              <Comms accountId={accountId} reloadKey={reloadKey} onSaved={onSaved} />
            </Collapsible>
            <Collapsible title="Extract from a transcript">
              <Extraction accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} onApplied={onSaved} />
            </Collapsible>
          </div>
        )}
        {tab === "people" && (
          <People accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} />
        )}
        {tab === "plan" && (
          <div className="stack">
            <Checklists accountId={accountId} programId={programId} reloadKey={reloadKey} onSaved={onSaved} />
            <CalendarPanel accountId={accountId} programId={programId} reloadKey={reloadKey} />
            <AdoptionComms accountId={accountId} programId={programId} reloadKey={reloadKey} />
            <Campaigns accountId={accountId} reloadKey={reloadKey} />
            {selProgram
              ? <ProgramDetail programId={selProgram.id} reloadKey={reloadKey} onQuickEntry={(aid, pid) => onQuickEntry(aid, pid)} />
              : <Timeline accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} />}
          </div>
        )}
        {tab === "commercial" && (
          <Commercial accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} openCopilot={openCopilot} />
        )}
        {tab === "evidence" && (
          <div className="stack">
            <ValueLibrary accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} />
            <Metrics reloadKey={reloadKey} />
          </div>
        )}
        {tab === "outputs" && (
          <OutputsTab accounts={accounts} accountId={accountId} programId={programId}
                      setAcct={setAcct} reloadKey={reloadKey} />
        )}
        {tab === "internal" && (
          <Internal accountId={accountId} reloadKey={reloadKey} onChanged={onSaved} />
        )}
      </div>
    </>
  );
}

function renewalText(dateStr) {
  if (!dateStr) return null;
  const until = Math.round((new Date(dateStr.slice(0, 10) + "T00:00:00").getTime() - Date.now()) / 86400000);
  const fmt = (n) => (n < 45 ? `${n}d` : n < 365 ? `${Math.round(n / 30)}mo` : `${(n / 365).toFixed(1)}y`);
  if (until < 0) return { text: `overdue ${fmt(-until)}`, warn: true };
  return { text: `in ${fmt(until)}`, warn: until <= 90 };
}

function ContextHeader({ detail, programs, programId, selProgram, setProgramFilter, renewal }) {
  if (!detail) return <div className="ctx-header"><div className="ctx-name subtle">Loading…</div></div>;
  const phase = selProgram?.phase;
  const ren = renewalText(renewal);
  return (
    <div className="ctx-header">
      <div className="ctx-name">{detail.name}</div>
      <select className="ctx-prog" value={programId || ""} onChange={(e) => setProgramFilter(e.target.value)}>
        <option value="">All programs</option>
        {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <StatusStat label="Delivery" status={detail.delivery_status} assessed={detail.delivery_status_assessed_on} />
      <StatusStat label="Commercial" status={detail.commercial_status} assessed={detail.commercial_status_assessed_on} />
      {ren && (
        <div className="ctx-stat">
          <span className="ctx-k">Renewal</span>
          <span className="ctx-v" style={ren.warn ? { color: "var(--status-warn)" } : undefined}>{ren.warn ? "▲ " : ""}{ren.text}</span>
          <span className="rowmeta mono">{fmtDate(renewal)}</span>
        </div>
      )}
      {phase && (
        <div className="ctx-stat">
          <span className="ctx-k">Phase</span>
          <span className="ctx-v badge phase">{phase}</span>
        </div>
      )}
    </div>
  );
}

// Manually-assessed status (§7): keeps its color, but past the 30-day reassessment interval
// it gains a dotted outline + the age chip, so a stale judgment can't pass as a fresh one.
function StatusStat({ label, status, assessed }) {
  const stale = ageDays(assessed) != null && ageDays(assessed) > 30;
  return (
    <div className="ctx-stat">
      <span className="ctx-k">{label}</span>
      <span className={"ctx-v" + (stale ? " status-stale-outline" : "")}>{(status || "—").replace(/_/g, " ")}</span>
      <AgeChip date={assessed} />
    </div>
  );
}

// Outputs tab: an inner selector across the three generators (interim; Phase D refines).
function OutputsTab({ accounts, accountId, programId, setAcct, reloadKey }) {
  const [which, setWhich] = useState("artifacts");
  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <SegTabs tabs={[["artifacts", "Artifacts"], ["qbr", "QBR"], ["team", "Team update"], ["map", "Mutual action plan"]]} value={which} onChange={setWhich} />
      </div>
      {which === "artifacts" && <Artifacts accounts={accounts} accountId={accountId}
        programId={programId} setAccountId={setAcct} reloadKey={reloadKey} />}
      {which === "qbr" && <QBR accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} />}
      {which === "team" && <TeamUpdate reloadKey={reloadKey} />}
      {which === "map" && <MutualActionPlan accounts={accounts} accountId={accountId} setAccountId={setAcct} reloadKey={reloadKey} />}
    </div>
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
        <div className="card" style={{ position: "absolute", top: 34, left: 0, right: 0, zIndex: 40, maxHeight: 420, overflowY: "auto", boxShadow: "var(--shadow-panel)" }}>
          {results.length === 0 ? (
            <div className="rowmeta" style={{ padding: 12 }}>No matches for “{q}”.</div>
          ) : (
            results.map((r) => (
              <button key={r.object_type + r.object_id} onClick={() => go(r)}
                style={{ display: "block", width: "100%", textAlign: "left", border: 0, borderBottom: "1px solid var(--line-hairline)", background: "none", padding: "8px 12px", cursor: "pointer" }}
                onMouseDown={(e) => e.preventDefault()}>
                <div style={{ fontSize: "var(--t-body)" }}>
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
