/* Funding intelligence (EXPANSION-ENGINE-SPEC.md §4).

   "Deals are won in the value case and lost in the funding mechanics." The ask calendar is the
   point of this screen: an ask that misses the planning window slips a full cycle, so every
   step and date between today and a funded ask is visible before anyone has to ask for it.

   Note the D-70 boundary: this is a status surface (late steps, pool states), so no financial
   chart shares a card with it. Pool amounts are plain figures in a table, not a waterfall. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast } from "../ui";

const POOL_KINDS = [
  ["recovered_vendor_spend", "Recovered vendor spend"],
  ["central_ld_budget", "Central L&D budget"],
  ["chro_discretionary", "CHRO discretionary"],
  ["bu_cross_charge", "BU cross-charge"],
  ["transformation_program", "Transformation program"],
  ["other", "Other"],
];
const POOL_STATUS = ["potential", "confirmed", "committed", "exhausted", "unavailable"];
// Status glyphs, never color alone.
const POOL_GLYPH = {
  // "Potential" is a neutral state: neutral ink, not --status-unknown, which fails 4.5:1
  // as a glyph (the Whitespace map sets the same precedent for its neutral states).
  potential: ["○", "--ink-secondary"], confirmed: ["◐", "--status-warn"],
  committed: ["●", "--status-ok"], exhausted: ["✕", "--status-risk"],
  unavailable: ["✕", "--status-risk"],
};
const money = (v, c) => (v == null ? "—" : `${c ? c + " " : ""}${Number(v).toLocaleString()}`);

export default function Funding({ accountId, reloadKey }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [panel, setPanel] = useState(null);
  const [tick, setTick] = useState(0);

  async function load() {
    if (!accountId) return;
    try { setData(await api.funding(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);
  const after = () => { setPanel(null); setTick((t) => t + 1); };

  if (!accountId) return <Empty title="No account selected">Pick an account.</Empty>;
  if (!data) return <div className="subtle" style={{ padding: 12 }}>Loading…</div>;

  const fm = data.fiscal_map;

  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <h3>Fiscal map</h3>
          <div className="spacer" />
          <button className="btn small" onClick={() => setPanel({ kind: "fiscal" })}>
            {fm ? "Edit" : "Set up"}
          </button>
        </div>
        {!fm ? (
          <Empty title="No fiscal map yet">
            Fiscal year end, the planning window, and budget deadlines. Entered once, confirmed
            annually — without them the ask calendar back-schedules from generic defaults.
          </Empty>
        ) : (
          <table>
            <tbody>
              <tr><th scope="row" style={th}>Fiscal year end</th><td>{fm.fiscal_year_end || "—"}</td></tr>
              <tr><th scope="row" style={th}>Planning window</th>
                  <td>{fm.planning_window_start || "—"} → {fm.planning_window_end || "—"}</td></tr>
              <tr><th scope="row" style={th}>Budget request deadline</th><td>{fm.budget_request_deadline || "—"}</td></tr>
              <tr><th scope="row" style={th}>Works council lead</th>
                  <td>{fm.works_council_lead_days != null ? `${fm.works_council_lead_days} days` : "—"}</td></tr>
              <tr><th scope="row" style={th}>Confirmed</th>
                  <td>{fm.confirmed_on
                    ? <>{fm.confirmed_on}{fm.confirmed_by ? ` · ${fm.confirmed_by}` : ""}</>
                    : <span className="rowmeta">never confirmed — treat these dates as unverified</span>}</td></tr>
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <h3>Funding pools</h3>
          <div className="spacer" />
          <button className="btn small" onClick={() => setPanel({ kind: "pool" })}>New pool</button>
        </div>
        {data.funding_pools.length === 0 ? (
          <Empty title="No funding pools yet">
            Named sources with the stakeholder who controls each one.
          </Empty>
        ) : (
          <table>
            <thead><tr>
              <th scope="col">Pool</th>
              <th scope="col" style={{ width: 150 }}>Controlled by</th>
              <th scope="col" style={{ width: 140 }}>Amount</th>
              <th scope="col" style={{ width: 130 }}>Status</th>
            </tr></thead>
            <tbody>
              {data.funding_pools.map((p) => {
                const [glyph, hue] = POOL_GLYPH[p.status];
                return (
                  <tr key={p.id}>
                    <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                      <button className="btn ghost" style={{ padding: 0 }} onClick={() => setPanel({ kind: "pool", current: p })}>{p.name}</button>
                      <div className="rowmeta">
                        {(POOL_KINDS.find((k) => k[0] === p.kind) || [])[1] || p.kind}
                        {p.client_visible ? " · shared" : " · internal"}
                      </div>
                    </th>
                    <td>{p.owner_name || <span className="rowmeta">unowned</span>}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>{money(p.amount, p.currency)}</td>
                    <td>
                      <span aria-hidden="true" style={{ color: `var(${hue})`, marginRight: 5 }}>{glyph}</span>
                      {p.status}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <h3>Ask calendars</h3>
          <div className="spacer" />
          {data.late_steps_total > 0 && (
            <span className="rowmeta" style={{ color: "var(--status-warn)" }}>
              ▲ {data.late_steps_total} late step{data.late_steps_total === 1 ? "" : "s"}
            </span>
          )}
          <button className="btn small" style={{ marginLeft: 8 }}
                  onClick={() => setPanel({ kind: "calendar" })}>New ask</button>
        </div>
        {data.ask_calendars.length === 0 ? (
          <Empty title="No ask in flight">
            Give a target close date and the tool back-schedules the whole chain: business case →
            sponsorship → budget window → procurement → works council → signature.
          </Empty>
        ) : data.ask_calendars.map((cal) => (
          <div key={cal.id} style={{ borderTop: "1px solid var(--line-hairline)" }}>
            <div style={{ padding: "10px 12px 4px" }}>
              <strong>{cal.name}</strong>
              <span className="rowmeta"> · closes {cal.target_close_date}</span>
              {cal.late_steps > 0 && (
                <span className="rowmeta" style={{ color: "var(--status-warn)" }}>
                  {" "}· ▲ {cal.late_steps} late
                </span>
              )}
            </div>
            <table>
              <thead><tr>
                <th scope="col">Step</th>
                <th scope="col" style={{ width: 110 }}>Due</th>
                <th scope="col" style={{ width: 120 }}>Status</th>
                <th scope="col" style={{ width: 90 }}></th>
              </tr></thead>
              <tbody>
                {cal.steps.map((s) => (
                  <tr key={s.id}>
                    <th scope="row" style={{ textAlign: "left", fontWeight: 400 }}>
                      {s.label}
                      {s.owner_name && <div className="rowmeta">{s.owner_name}</div>}
                    </th>
                    <td className="rowmeta">{s.due_date}</td>
                    <td>
                      {s.derived_late ? (
                        <><span aria-hidden="true" style={{ color: "var(--status-warn)" }}>▲</span> late</>
                      ) : s.status === "done" ? (
                        <><span aria-hidden="true" style={{ color: "var(--status-ok)" }}>●</span> done</>
                      ) : (
                        <span className="rowmeta">{s.status}</span>
                      )}
                    </td>
                    <td>
                      {s.status !== "done" && (
                        <button className="btn small" onClick={async () => {
                          try {
                            await api.patchAskStep(s.id, { status: "done" });
                            setTick((t) => t + 1);
                          } catch (e) { toast(e.message, "err"); }
                        }}>Done</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      {panel?.kind === "pool" && <PoolPanel accountId={accountId} current={panel.current} onClose={() => setPanel(null)} onSaved={after} />}
      {panel?.kind === "fiscal" && <FiscalPanel accountId={accountId} current={fm} onClose={() => setPanel(null)} onSaved={after} />}
      {panel?.kind === "calendar" && <CalendarPanel accountId={accountId} onClose={() => setPanel(null)} onSaved={after} />}
    </>
  );
}

function PoolPanel({ accountId, current, onClose, onSaved }) {
  const toast = useToast();
  const [people, setPeople] = useState([]);
  const [sources, setSources] = useState([]);
  const [f, setF] = useState({ name: current?.name || "", kind: current?.kind || "central_ld_budget",
    owner_person_id: current?.owner_person_id || "", status: current?.status || "potential",
    amount: current?.amount ?? "", currency: current?.currency || "EUR", notes: current?.notes || "",
    source_reference_id: current?.source_reference_id || "", client_visible: Boolean(current?.client_visible) });
  useEffect(() => {
    Promise.all([api.account(accountId), api.sourceReferences()]).then(([a, refs]) => {
      setPeople(a.people || []); setSources(refs);
    }).catch(() => {});
  }, [accountId]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <SlideOver title="New funding pool" onClose={onClose}>
      <form onSubmit={async (e) => {
        e.preventDefault();
        try {
          const body = {
            account_id: accountId, name: f.name, kind: f.kind, status: f.status,
            owner_person_id: f.owner_person_id || null,
            amount: f.amount === "" ? null : Number(f.amount),
            currency: f.currency || null,
            notes: f.notes || null, source_reference_id: f.source_reference_id || null,
            client_visible: f.client_visible,
          };
          if (current) await api.patchFundingPool(current.id, body); else await api.createFundingPool(body);
          toast(current ? "Pool updated" : "Pool added"); onSaved();
        } catch (err) { toast(err.message, "err"); }
      }}>
        <label style={lbl}>Name<input value={f.name} onChange={set("name")} required style={sel} /></label>
        <label style={lbl}>Kind
          <select value={f.kind} onChange={set("kind")} style={sel}>
            {POOL_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label style={lbl}>Controlled by
          <select value={f.owner_person_id} onChange={set("owner_person_id")} style={sel}>
            <option value="">unowned</option>
            {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...lbl, flex: 2 }}>Amount
            <input type="number" step="any" value={f.amount} onChange={set("amount")} style={sel} /></label>
          <label style={{ ...lbl, flex: 1 }}>Currency
            <input value={f.currency} onChange={set("currency")} style={sel} /></label>
        </div>
        <label style={lbl}>Status
          <select value={f.status} onChange={set("status")} style={sel}>
            {POOL_STATUS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label style={lbl}>Notes<textarea value={f.notes} onChange={set("notes")} rows={2} style={sel} /></label>
        <label style={lbl}>Source<select value={f.source_reference_id} onChange={set("source_reference_id")} style={sel}>
          <option value="">none</option>{sources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select></label>
        <label style={{ ...lbl, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={f.client_visible} onChange={set("client_visible")} />
          <span>Include in client-facing artifacts (requires a source)</span>
        </label>
        <button className="btn small primary" type="submit" style={{ marginTop: 8 }}>{current ? "Save pool" : "Add pool"}</button>
      </form>
    </SlideOver>
  );
}

function FiscalPanel({ accountId, current, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({
    fiscal_year_end: current?.fiscal_year_end || "",
    planning_window_start: current?.planning_window_start || "",
    planning_window_end: current?.planning_window_end || "",
    budget_request_deadline: current?.budget_request_deadline || "",
    works_council_lead_days: current?.works_council_lead_days ?? "",
    confirmed_on: current?.confirmed_on || "",
    confirmed_by: current?.confirmed_by || "",
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  return (
    <SlideOver title="Fiscal map" onClose={onClose}>
      <div className="rowmeta" style={{ marginBottom: 12 }}>
        Month-day values (MM-DD). Procurement lead time stays on the contract as canonical CRM
        data — the fiscal map points at it rather than keeping a copy that can drift.
      </div>
      <form onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api.putFiscalMap(accountId, {
            ...f,
            works_council_lead_days: f.works_council_lead_days === "" ? null : Number(f.works_council_lead_days),
          });
          toast("Fiscal map saved"); onSaved();
        } catch (err) { toast(err.message, "err"); }
      }}>
        <label style={lbl}>Fiscal year end
          <input placeholder="12-31" value={f.fiscal_year_end} onChange={set("fiscal_year_end")} style={sel} /></label>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...lbl, flex: 1 }}>Planning window opens
            <input placeholder="09-01" value={f.planning_window_start} onChange={set("planning_window_start")} style={sel} /></label>
          <label style={{ ...lbl, flex: 1 }}>closes
            <input placeholder="10-31" value={f.planning_window_end} onChange={set("planning_window_end")} style={sel} /></label>
        </div>
        <label style={lbl}>Budget request deadline
          <input placeholder="10-15" value={f.budget_request_deadline} onChange={set("budget_request_deadline")} style={sel} /></label>
        <label style={lbl}>Works council lead (days)
          <input type="number" value={f.works_council_lead_days} onChange={set("works_council_lead_days")} style={sel} /></label>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...lbl, flex: 1 }}>Confirmed on
            <input type="date" value={f.confirmed_on} onChange={set("confirmed_on")} style={sel} /></label>
          <label style={{ ...lbl, flex: 1 }}>by
            <input value={f.confirmed_by} onChange={set("confirmed_by")} style={sel} /></label>
        </div>
        <button className="btn small primary" type="submit" style={{ marginTop: 8 }}>Save</button>
      </form>
    </SlideOver>
  );
}

function CalendarPanel({ accountId, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", target_close_date: "", include_works_council: true });
  return (
    <SlideOver title="New ask" onClose={onClose}>
      <div className="rowmeta" style={{ marginBottom: 12 }}>
        Every step gets a date the moment you set the close date, so a missed planning window is
        visible now rather than in November.
      </div>
      <form onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api.createAskCalendar({ account_id: accountId, ...f });
          toast("Ask back-scheduled"); onSaved();
        } catch (err) { toast(err.message, "err"); }
      }}>
        <label style={lbl}>Name
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required style={sel} /></label>
        <label style={lbl}>Target close date
          <input type="date" value={f.target_close_date} required style={sel}
                 onChange={(e) => setF({ ...f, target_close_date: e.target.value })} /></label>
        <label style={{ ...lbl, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={f.include_works_council}
                 onChange={(e) => setF({ ...f, include_works_council: e.target.checked })} />
          <span>Works council consultation applies</span>
        </label>
        <button className="btn small primary" type="submit" style={{ marginTop: 8 }}>Back-schedule</button>
      </form>
    </SlideOver>
  );
}

const th = { textAlign: "left", fontWeight: 400, color: "var(--ink-tertiary)", width: 200 };
const lbl = { display: "flex", flexDirection: "column", gap: 4, marginBottom: 10, fontSize: 13 };
const sel = {
  padding: "6px 8px", borderRadius: "var(--r-sm)",
  border: "1px solid var(--line-hairline)", background: "var(--bg-surface)",
  color: "var(--ink-primary)",
};
