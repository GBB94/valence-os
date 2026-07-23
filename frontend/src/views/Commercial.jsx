import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast, fmtDate } from "../ui";

const BUDGET_STATES = ["conceptually_supported", "in_planning", "formally_allocated",
                       "requisition_created", "procurement_approved", "executed"];
const OUTCOMES = ["won", "lost", "deferred", "merged", "no_decision"];
const money = (v) => (v == null ? "—" : "$" + Number(v).toLocaleString());

export default function Commercial({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [expansions, setExpansions] = useState(null);
  const [contracts, setContracts] = useState(null);
  const [people, setPeople] = useState([]);
  const [panel, setPanel] = useState(null); // {kind:'expansion'|'contract'|'close'|'overlay', ...}
  const [tick, setTick] = useState(0);

  async function load() {
    if (!accountId) return;
    try {
      const [x, c, acct] = await Promise.all([api.expansions(accountId), api.contracts(accountId), api.account(accountId)]);
      setExpansions(x); setContracts(c); setPeople(acct.people);
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);
  const after = () => { setPanel(null); setTick((t) => t + 1); };

  async function advance(xo) {
    const i = BUDGET_STATES.indexOf(xo.budget_state);
    if (i >= BUDGET_STATES.length - 1) return;
    try { await api.patchExpansion(xo.id, { budget_state: BUDGET_STATES[i + 1] }); toast("Budget state advanced"); setTick((t) => t + 1); }
    catch (e) { toast(e.message, "err"); }
  }

  if (!accounts.length) return <Empty title="No accounts yet">Create an account first.</Empty>;

  return (
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Commercial</h1>
        <select value={accountId || ""} onChange={(e) => setAccountId(e.target.value)} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <div className="spacer" />
      </div>

      <div className="card">
        <div className="card-h"><h3>Expansion opportunities</h3><div className="spacer" />
          <button className="btn small" onClick={() => setPanel({ kind: "expansion" })}>New expansion</button></div>
        {!expansions ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> :
          expansions.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No expansion opportunities yet.</div> : (
          <table>
            <thead><tr><th>Opportunity</th><th style={{ width: 90 }}>Target</th><th style={{ width: 240 }}>Budget state</th><th style={{ width: 130 }}>Status</th><th style={{ width: 120 }}></th></tr></thead>
            <tbody>
              {expansions.map((x) => (
                <tr key={x.id}>
                  <td>{x.name}<div className="rowmeta">{x.use_case || ""}{x.budget_owner_name ? ` · budget: ${x.budget_owner_name}` : ""} · {money(x.expected_value)}{x.blockers ? ` · blockers: ${x.blockers}` : ""}</div></td>
                  <td className="rowmeta">{x.target_seats ? x.target_seats.toLocaleString() + " seats" : "—"}</td>
                  <td><BudgetStepper state={x.budget_state} closed={x.status === "closed"} /></td>
                  <td>{x.status === "closed"
                    ? <span><span className="dot ok" /> {x.outcome}</span>
                    : <span className="rowmeta">open</span>}
                    {x.status === "closed" && x.outcome_reason ? <div className="rowmeta">{x.outcome_reason}</div> : null}
                  </td>
                  <td>{x.status === "open" && (
                    <div className="actions">
                      <button className="btn small" onClick={() => advance(x)} disabled={x.budget_state === "executed"}>Advance</button>
                      <button className="btn small ghost" onClick={() => setPanel({ kind: "close", xo: x })}>Close</button>
                    </div>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-h"><h3>Contracts</h3><div className="spacer" />
          <button className="btn small" onClick={() => setPanel({ kind: "contract" })}>New version</button></div>
        {!contracts ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> :
          contracts.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No contract versions synced.</div> : (
          <table>
            <thead><tr><th>Version</th><th style={{ width: 80 }}>Seats</th><th style={{ width: 110 }}>Renewal</th><th>Overlay (operational)</th><th style={{ width: 90 }}></th></tr></thead>
            <tbody>
              {contracts.map((c) => (
                <tr key={c.id}>
                  <td>{c.version_label} {c.is_current && <span className="badge" style={{ borderColor: "var(--accent)", color: "var(--accent)" }}>current</span>}
                    <div className="rowmeta">{money(c.price)}{c.source_system ? ` · source: ${c.source_system} (read-only)` : ""}</div></td>
                  <td className="rowmeta">{c.seats ?? "—"}</td>
                  <td className="rowmeta">{fmtDate(c.renewal_date)}{c.notice_period_days ? <div>notice {c.notice_period_days}d</div> : null}</td>
                  <td className="rowmeta">
                    {c.overlay_expected_decision_date
                      ? <>expected decision {c.overlay_expected_decision_date}<div>{c.overlay_rationale}</div></>
                      : <span>—</span>}
                  </td>
                  <td><button className="btn small ghost" onClick={() => setPanel({ kind: "overlay", contract: c })}>Overlay</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="rowmeta" style={{ padding: "8px 12px" }}>Canonical contract data is a read-only synced copy; operational interpretation lives in the overlay, never overwriting the canonical date.</div>
      </div>

      {panel?.kind === "expansion" && <ExpansionForm accountId={accountId} people={people} onClose={() => setPanel(null)} onSaved={after} />}
      {panel?.kind === "close" && <CloseExpansion xo={panel.xo} onClose={() => setPanel(null)} onSaved={after} />}
      {panel?.kind === "contract" && <ContractForm accountId={accountId} contracts={contracts} onClose={() => setPanel(null)} onSaved={after} />}
      {panel?.kind === "overlay" && <OverlayForm contract={panel.contract} onClose={() => setPanel(null)} onSaved={after} />}
    </div>
  );
}

function BudgetStepper({ state, closed }) {
  const i = BUDGET_STATES.indexOf(state);
  return (
    <div style={{ display: "flex", gap: 3, alignItems: "center" }}>
      {BUDGET_STATES.map((s, j) => (
        <span key={s} title={s.replace(/_/g, " ")}
          style={{ width: 22, height: 6, borderRadius: 3, background: j <= i ? (closed ? "var(--text-3)" : "var(--accent)") : "var(--surface-2)", border: "1px solid var(--border)" }} />
      ))}
      <span className="rowmeta" style={{ marginLeft: 6 }}>{state.replace(/_/g, " ")}</span>
    </div>
  );
}

function ExpansionForm({ accountId, people, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", use_case: "", target_seats: "", expected_value: "", budget_owner_person_id: "", blockers: "", next_action: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    if (!f.name.trim()) { toast("Name is required", "err"); return; }
    try {
      await api.createExpansion({
        account_id: accountId, name: f.name.trim(), use_case: f.use_case || null,
        target_seats: f.target_seats ? Number(f.target_seats) : null,
        expected_value: f.expected_value ? Number(f.expected_value) : null,
        budget_owner_person_id: f.budget_owner_person_id || null,
        blockers: f.blockers || null, next_action: f.next_action || null,
      });
      toast("Expansion created"); onSaved();
    } catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="New expansion opportunity" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Create</button></>}>
      <div className="field"><label>Name <span className="req">*</span></label><input value={f.name} onChange={set("name")} placeholder="e.g. Scale to 3,000 seats" autoFocus /></div>
      <div className="field"><label>Use case</label><input value={f.use_case} onChange={set("use_case")} /></div>
      <div className="grid2">
        <div className="field"><label>Target seats</label><input type="number" value={f.target_seats} onChange={set("target_seats")} /></div>
        <div className="field"><label>Expected value ($)</label><input type="number" value={f.expected_value} onChange={set("expected_value")} /></div>
      </div>
      <div className="field"><label>Budget owner</label>
        <select value={f.budget_owner_person_id} onChange={set("budget_owner_person_id")}>
          <option value="">—</option>
          {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></div>
      <div className="field"><label>Blockers</label><input value={f.blockers} onChange={set("blockers")} /></div>
      <div className="field"><label>Next action</label><input value={f.next_action} onChange={set("next_action")} /></div>
    </SlideOver>
  );
}

function CloseExpansion({ xo, onClose, onSaved }) {
  const toast = useToast();
  const [outcome, setOutcome] = useState("won");
  const [reason, setReason] = useState("");
  async function save() {
    if (!reason.trim()) { toast("A reason is required", "err"); return; }
    try { await api.closeExpansion(xo.id, { outcome, outcome_reason: reason.trim() }); toast("Closed"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="Close expansion" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Close opportunity</button></>}>
      <div className="subtle" style={{ marginBottom: 12 }}>{xo.name}</div>
      <div className="field"><label>Outcome <span className="req">*</span></label>
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>{OUTCOMES.map((o) => <option key={o} value={o}>{o}</option>)}</select></div>
      <div className="field"><label>Reason <span className="req">*</span></label><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></div>
    </SlideOver>
  );
}

function ContractForm({ accountId, contracts, onClose, onSaved }) {
  const toast = useToast();
  const current = contracts?.find((c) => c.is_current);
  const [f, setF] = useState({ version_label: "", seats: "", price: "", renewal_date: "", notice_period_days: "", supersede: !!current });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function save() {
    if (!f.version_label.trim()) { toast("Version label required", "err"); return; }
    try {
      await api.createContract({
        account_id: accountId, version_label: f.version_label.trim(),
        seats: f.seats ? Number(f.seats) : null, price: f.price ? Number(f.price) : null,
        renewal_date: f.renewal_date || null, notice_period_days: f.notice_period_days ? Number(f.notice_period_days) : null,
        supersedes_id: f.supersede && current ? current.id : null,
      });
      toast("Contract version added"); onSaved();
    } catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="New contract version" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Add version</button></>}>
      <div className="field"><label>Version label <span className="req">*</span></label><input value={f.version_label} onChange={set("version_label")} placeholder="e.g. FY27 renewal" autoFocus /></div>
      <div className="grid2">
        <div className="field"><label>Seats</label><input type="number" value={f.seats} onChange={set("seats")} /></div>
        <div className="field"><label>Price ($)</label><input type="number" value={f.price} onChange={set("price")} /></div>
      </div>
      <div className="grid2">
        <div className="field"><label>Renewal date</label><input type="date" value={f.renewal_date} onChange={set("renewal_date")} /></div>
        <div className="field"><label>Notice period (days)</label><input type="number" value={f.notice_period_days} onChange={set("notice_period_days")} /></div>
      </div>
      {current && <div className="field checkline"><input id="sup" type="checkbox" checked={f.supersede} onChange={(e) => setF({ ...f, supersede: e.target.checked })} /><label htmlFor="sup" style={{ margin: 0 }}>Supersede current ({current.version_label}) — keeps history</label></div>}
    </SlideOver>
  );
}

function OverlayForm({ contract, onClose, onSaved }) {
  const toast = useToast();
  const [d, setD] = useState(contract.overlay_expected_decision_date || "");
  const [r, setR] = useState(contract.overlay_rationale || "");
  async function save() {
    if (!d || !r.trim()) { toast("Date and rationale required", "err"); return; }
    try { await api.setOverlay(contract.id, { overlay_expected_decision_date: d, overlay_rationale: r.trim() }); toast("Overlay saved"); onSaved(); }
    catch (e) { toast(e.message, "err"); }
  }
  return (
    <SlideOver title="Operational overlay" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save overlay</button></>}>
      <div className="rowmeta" style={{ marginBottom: 12 }}>Canonical renewal date ({fmtDate(contract.renewal_date)}) is never overwritten. The overlay records your operational expectation with a rationale.</div>
      <div className="field"><label>Expected decision date <span className="req">*</span></label><input type="date" value={d} onChange={(e) => setD(e.target.value)} /></div>
      <div className="field"><label>Rationale <span className="req">*</span></label><textarea value={r} onChange={(e) => setR(e.target.value)} placeholder="e.g. procurement requires ~10 weeks" /></div>
    </SlideOver>
  );
}

const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
