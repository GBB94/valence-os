/* Stage 7.5 account thesis: earned triggers, renewal defense, and named growth lines.
   Internal assumptions stay in this surface; the mutual-plan generator queries only promoted,
   sourced joint fields, so probability and competitive notes cannot leak. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, SlideOver, useToast, fmtDate } from "../ui";

export default function Growth({ accountId, reloadKey }) {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [panel, setPanel] = useState(null);
  const [tick, setTick] = useState(0);

  async function load() {
    if (!accountId) return;
    try {
      const [agreements, renewal, growth, account, ledger, funding, contracts, whitespace, sources] = await Promise.all([
        api.operationalAgreements(accountId), api.renewalCenter(accountId), api.growthPlan(accountId),
        api.account(accountId), api.ledger(accountId), api.funding(accountId), api.contracts(accountId),
        api.whitespace(accountId), api.sourceReferences(),
      ]);
      setData({ agreements, renewal, growth, account, ledger, funding, contracts, whitespace, sources });
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);
  const after = () => { setPanel(null); setTick((n) => n + 1); };

  if (!data) return <div className="subtle" style={{ padding: 12 }}>Loading…</div>;
  const { agreements, renewal, growth } = data;

  return <>
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card-h"><h3>Renewal command center</h3><div className="spacer" />
        {renewal.contract && <span className="badge">{renewal.contract.version_label}</span>}</div>
      {!renewal.contract ? <Empty title="No current contract">Sync a contract before building the renewal case.</Empty> : <>
        <div className="grid3" style={{ padding: 12 }}>
          <Stat label="Notice date" value={fmtDate(renewal.timeline.notice_date)} detail={countdown(renewal.timeline.days_to_notice)} />
          <Stat label="Decision date" value={fmtDate(renewal.timeline.decision_date)} detail={countdown(renewal.timeline.days_to_decision)} />
          <Stat label="Renewal date" value={fmtDate(renewal.timeline.renewal_date)} detail={renewal.fiscal_map ? "fiscal map overlaid" : "fiscal map missing"} />
        </div>
        <table><tbody>
          <tr><th style={th}>Value targets</th><td>{Object.entries(renewal.value.counts || {}).map(([k,v]) => `${k.replaceAll("_"," ")} ${v}`).join(" · ") || "—"}</td></tr>
          <tr><th style={th}>Penetration</th><td>{renewal.penetration.paid_seats?.toLocaleString()} of {renewal.penetration.addressable_seats?.toLocaleString()} seats · {renewal.penetration.basis}</td></tr>
          <tr><th style={th}>Open risks</th><td>{renewal.risks.length}{renewal.risks[0] ? ` · ${renewal.risks[0].description}` : ""}</td></tr>
          <tr><th style={th}>Expansion on same paper</th><td>{renewal.eligible_expansions.length} fully qualified of {renewal.opportunities.length} open</td></tr>
          <tr><th style={th}>Alternative landscape</th><td>{renewal.alternative_landscape || "Not recorded"}</td></tr>
        </tbody></table>
        {(renewal.agreement_gap || renewal.value.gaps.length) && <div className="callout warn" style={{ margin: 12 }}>
          {renewal.agreement_gap || `${renewal.value.gaps.length} value gap(s) need a closure plan before renewal.`}
        </div>}
      </>}
    </div>

    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card-h"><h3>Pre-agreed expansion triggers</h3><div className="spacer" />
        <button className="btn small ghost" onClick={async () => { try { const r = await api.evaluateOperationalAgreements(); toast(`${r.fired} trigger${r.fired === 1 ? "" : "s"} fired`); setTick(n => n + 1); } catch(e) { toast(e.message,"err"); } }}>Evaluate</button>
        <button className="btn small" onClick={() => setPanel({ kind: "agreement" })}>Add agreement</button></div>
      {agreements.agreements.length === 0 ? <Empty title="No pre-agreed triggers">Record the condition, authority, seat band, and agreed process.</Empty> :
        agreements.agreements.map((a) => <div key={a.id} style={{ padding: 12, borderTop: "1px solid var(--line-hairline)" }}>
          <div className="actions"><strong>{a.name}</strong><span className="badge">{a.contractual ? "contractual" : "operational"}</span><div className="spacer" />
            <span className="rowmeta">{a.seat_band_min.toLocaleString()}–{a.seat_band_max.toLocaleString()} seats</span></div>
          <div className="rowmeta">{a.agreed_process}</div>
          <Bullet value={a.realization.value} target={a.target.target_value} direction={a.target.direction} />
          <div className="actions" style={{ marginTop: 7 }}><span className="rowmeta">current {num(a.realization.value)} · bar {a.target.direction === "at_most" ? "≤" : "≥"} {num(a.target.target_value)} · through {fmtDate(a.realization.current_through)}</span><div className="spacer" />
            {a.event?.status === "fired" && <><span className="badge" style={{ color: "var(--status-warn)" }}>earned · act by {fmtDate(a.event.action_due_on)}</span>
              <button className="btn small primary" onClick={async () => { try { await api.actionOperationalAgreement(a.event.id); toast("Expansion drafted"); setTick(n=>n+1); } catch(e) { toast(e.message,"err"); } }}>Draft expansion</button></>}
            {a.event?.status === "actioned" && <span className="badge">actioned</span>}
          </div>
          {a.event?.risk_note && <div className="rowmeta" style={{ color: "var(--status-warn)", marginTop: 5 }}>{a.event.risk_note}</div>}
        </div>)}
    </div>

    <div className="card">
      <div className="card-h"><h3>Account growth plan</h3><div className="spacer" />
        <button className="btn small" onClick={() => setPanel({ kind: growth.plan ? "line" : "plan" })}>{growth.plan ? "Add line" : "Create plan"}</button></div>
      {!growth.plan ? <Empty title="No active growth plan">Set the seat target and date, then name the lines that close the gap.</Empty> : <>
        <div style={{ padding: 12 }}><div className="actions"><strong>{growth.plan.name}</strong><div className="spacer" /><span className="rowmeta">target {growth.plan.target_seats.toLocaleString()} by {fmtDate(growth.plan.target_date)}</span></div>
          <Bridge rollup={growth.rollup} />
          {!growth.rollup.additive && <div className="callout warn" style={{ marginTop: 10 }}>{growth.rollup.basis} Resolve the overlap before using the bridge.</div>}
        </div>
        <table><thead><tr><th>Named line</th><th>Seats</th><th>Stage</th><th>Probability assumption</th><th>Ask</th><th>Shared</th></tr></thead><tbody>
          {growth.lines.map((l) => <tr key={l.id}><td>{l.name}<div className="rowmeta">{l.population}{l.cell_use_case ? ` · ${l.cell_use_case}` : " · grouped line"}{l.budget_owner_name ? ` · ${l.budget_owner_name}` : ""}</div></td>
            <td>{l.seat_count.toLocaleString()}</td><td><select value={l.status} style={{width:110}} onChange={async e=>{try{await api.patchGrowthPlanLine(l.id,{status:e.target.value});toast("Line stage updated");setTick(n=>n+1);}catch(err){toast(err.message,"err");}}}>{["planned","committed","funded","slipped","declined"].map(s=><option key={s}>{s}</option>)}</select></td>
            <td>{Math.round(l.probability*100)}%<div className="rowmeta">{l.probability_author} · {fmtDate(l.probability_assessed_on)}</div></td>
            <td>{fmtDate(l.ask_date)}</td><td><button className="btn small ghost" disabled={!l.source_reference_id}
              onClick={async () => { try { await api.patchGrowthPlanLine(l.id,{client_visible:!l.client_visible}); toast(l.client_visible?"Removed from mutual plan":"Shared to mutual plan"); setTick(n=>n+1); } catch(e){toast(e.message,"err");} }}>{l.client_visible ? "★ shared" : "☆ internal"}</button></td></tr>)}
        </tbody></table>
      </>}
    </div>

    {panel?.kind === "agreement" && <AgreementForm data={data} accountId={accountId} onClose={() => setPanel(null)} onSaved={after} />}
    {panel?.kind === "plan" && <PlanForm accountId={accountId} onClose={() => setPanel(null)} onSaved={after} />}
    {panel?.kind === "line" && <LineForm data={data} onClose={() => setPanel(null)} onSaved={after} />}
  </>;
}

function AgreementForm({ data, accountId, onClose, onSaved }) {
  const toast = useToast(); const current = data.contracts.find(c => c.is_current);
  const [f,setF] = useState({ name:"", value_target_id:data.ledger.targets[0]?.id||"", source_kind:"signed_paper", source_reference_id:"", source_interaction_id:"", effective_on:new Date().toISOString().slice(0,10), expires_on:"", seat_band_min:"", seat_band_max:"", unit_price:"", currency:current?.currency||"", agreed_process:"", budget_owner_person_id:"", action_window_days:"14", client_visible:false });
  const set = k => e => setF({...f,[k]:e.target.type === "checkbox" ? e.target.checked : e.target.value});
  async function save(){ try { await api.createOperationalAgreement({account_id:accountId,contract_version_id:current.id,...f,seat_band_min:Number(f.seat_band_min),seat_band_max:Number(f.seat_band_max),unit_price:f.unit_price?Number(f.unit_price):null,action_window_days:Number(f.action_window_days),expires_on:f.expires_on||null,source_reference_id:f.source_kind==="signed_paper"?f.source_reference_id:null,source_interaction_id:f.source_kind==="agreed_conversation"?f.source_interaction_id:null,budget_owner_person_id:f.budget_owner_person_id||null,currency:f.currency||null}); toast("Agreement added"); onSaved(); } catch(e){toast(e.message,"err");} }
  return <SlideOver title="Pre-agreed expansion trigger" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save} disabled={!current}>Add agreement</button></>}>
    {!current && <div className="callout warn">A current contract is required.</div>}
    <Field label="Name"><input value={f.name} onChange={set("name")} autoFocus /></Field>
    <Field label="Value target"><select value={f.value_target_id} onChange={set("value_target_id")}>{data.ledger.targets.map(t=><option key={t.id} value={t.id}>{t.metric} · {t.population} · {t.target_value}</option>)}</select></Field>
    <Field label="Authority"><select value={f.source_kind} onChange={set("source_kind")}><option value="signed_paper">Signed paper (contractual)</option><option value="agreed_conversation">Agreed conversation (operational)</option></select></Field>
    {f.source_kind === "signed_paper" ? <Field label="Source document"><select value={f.source_reference_id} onChange={set("source_reference_id")}><option value="">—</option>{data.sources.map(s=><option key={s.id} value={s.id}>{s.label}</option>)}</select></Field> : <Field label="Source interaction"><select value={f.source_interaction_id} onChange={set("source_interaction_id")}><option value="">—</option>{data.account.interactions.map(i=><option key={i.id} value={i.id}>{fmtDate(i.occurred_on)} · {i.summary||i.type}</option>)}</select></Field>}
    <div className="grid2"><Field label="Effective"><input type="date" value={f.effective_on} onChange={set("effective_on")} /></Field><Field label="Expires"><input type="date" value={f.expires_on} onChange={set("expires_on")} /></Field></div>
    <div className="grid2"><Field label="Seat band min"><input type="number" value={f.seat_band_min} onChange={set("seat_band_min")} /></Field><Field label="Seat band max"><input type="number" value={f.seat_band_max} onChange={set("seat_band_max")} /></Field></div>
    <div className="grid2"><Field label="Unit price"><input type="number" value={f.unit_price} onChange={set("unit_price")} /></Field><Field label="Currency"><input value={f.currency} maxLength={3} onChange={set("currency")} /></Field></div>
    <Field label="Budget owner"><select value={f.budget_owner_person_id} onChange={set("budget_owner_person_id")}><option value="">—</option>{data.account.people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
    <Field label="Agreed process"><textarea value={f.agreed_process} onChange={set("agreed_process")} /></Field>
    <div className="field checkline"><input id="oa-share" type="checkbox" checked={f.client_visible} onChange={set("client_visible")} /><label htmlFor="oa-share">Show in client-facing value and mutual plans</label></div>
  </SlideOver>;
}

function PlanForm({ accountId,onClose,onSaved }) { const toast=useToast(); const [f,setF]=useState({name:"",target_seats:"",target_date:"",notes:""}); const set=k=>e=>setF({...f,[k]:e.target.value}); async function save(){try{await api.createGrowthPlan({account_id:accountId,...f,target_seats:Number(f.target_seats),notes:f.notes||null});toast("Growth plan created");onSaved();}catch(e){toast(e.message,"err");}} return <SlideOver title="Account growth plan" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Create</button></>}><Field label="Plan name"><input value={f.name} onChange={set("name")} autoFocus /></Field><div className="grid2"><Field label="Target seats"><input type="number" value={f.target_seats} onChange={set("target_seats")} /></Field><Field label="Target date"><input type="date" value={f.target_date} onChange={set("target_date")} /></Field></div><Field label="Notes"><textarea value={f.notes} onChange={set("notes")} /></Field></SlideOver>; }

function LineForm({ data, onClose, onSaved }) {
  const toast = useToast();
  const pops = [
    ...data.whitespace.segment_rows.map((r) => ({ id: `s:${r.id}`, name: r.name,
      cells: r.cells.filter((slot) => slot.cell).map((slot) => ({ id: slot.cell.id, name: slot.use_case })) })),
    ...data.whitespace.view_rows.map((r) => ({ id: `v:${r.id}`, name: `${r.name} (overlapping view)`,
      cells: r.cells.filter((slot) => slot.cell).map((slot) => ({ id: slot.cell.id, name: slot.use_case })) })),
  ];
  const [f, setF] = useState({ name: "", population: pops[0]?.id || "", cell_id: "", seat_count: "",
    seat_price_low: "", seat_price_high: "", seat_price_currency: "", seat_price_basis: "", probability: "0.5",
    probability_assessed_on: new Date().toISOString().slice(0, 10), ask_date: "", status: "planned",
    opportunity_id: "", budget_owner_person_id: "", funding_pool_id: "", ask_calendar_id: "",
    source_reference_id: "", client_visible: false, competitive_notes: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const selected = pops.find((p) => p.id === f.population);
  async function save() {
    const [kind, id] = f.population.split(":");
    try {
      await api.createGrowthPlanLine({ plan_id: data.growth.plan.id, name: f.name,
        segment_id: kind === "s" ? id : null, view_id: kind === "v" ? id : null,
        cell_id: f.cell_id || null, seat_count: Number(f.seat_count),
        seat_price_low: f.seat_price_low ? Number(f.seat_price_low) : null,
        seat_price_high: f.seat_price_high ? Number(f.seat_price_high) : null,
        seat_price_currency: f.seat_price_currency || null, seat_price_basis: f.seat_price_basis || null,
        probability: Number(f.probability), probability_author: "operator",
        probability_assessed_on: f.probability_assessed_on, ask_date: f.ask_date || null,
        status: f.status, opportunity_id: f.opportunity_id || null,
        budget_owner_person_id: f.budget_owner_person_id || null,
        funding_pool_id: f.funding_pool_id || null, ask_calendar_id: f.ask_calendar_id || null,
        source_reference_id: f.source_reference_id || null, client_visible: f.client_visible,
        competitive_notes: f.competitive_notes || null });
      toast("Growth line added"); onSaved();
    } catch (e) { toast(e.message, "err"); }
  }
  return <SlideOver title="Named growth line" onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Add line</button></>}>
    <Field label="Line name"><input value={f.name} onChange={set("name")} autoFocus /></Field>
    <Field label="Population"><select value={f.population} onChange={(e) => setF({ ...f, population: e.target.value, cell_id: "" })}>{pops.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
    <Field label="Whitespace cell / use case"><select value={f.cell_id} onChange={set("cell_id")}>
      <option value="">Grouped line — velocity unavailable</option>{(selected?.cells || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      <div className="hint">Link a cell when this line funds one use case; grouped lines stay explicitly excluded from Proven → funded velocity.</div></Field>
    <div className="grid2"><Field label="Seats"><input type="number" value={f.seat_count} onChange={set("seat_count")} /></Field><Field label="Probability"><input type="number" min="0" max="1" step="0.05" value={f.probability} onChange={set("probability")} /></Field></div>
    <div className="grid2"><Field label="Seat price low"><input type="number" value={f.seat_price_low} onChange={set("seat_price_low")} /></Field><Field label="Seat price high"><input type="number" value={f.seat_price_high} onChange={set("seat_price_high")} /></Field></div>
    <div className="grid2"><Field label="Price currency"><input maxLength={3} value={f.seat_price_currency} onChange={set("seat_price_currency")} placeholder="EUR" /></Field><Field label="Price basis"><select value={f.seat_price_basis} onChange={set("seat_price_basis")}><option value="">unknown — exclude from projection</option><option value="annual_recurring">annual recurring / seat</option><option value="term_total">term total / seat</option><option value="one_time">one-time / seat</option></select></Field></div>
    <div className="grid2"><Field label="Assessed on"><input type="date" value={f.probability_assessed_on} onChange={set("probability_assessed_on")} /></Field><Field label="Ask date"><input type="date" value={f.ask_date} onChange={set("ask_date")} /></Field></div>
    <Field label="Stage"><select value={f.status} onChange={set("status")}>{["planned","committed","funded","slipped","declined"].map((s) => <option key={s}>{s}</option>)}</select></Field>
    <Field label="Opportunity"><select value={f.opportunity_id} onChange={set("opportunity_id")}><option value="">—</option>{data.renewal.opportunities.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
    <Field label="Budget owner"><select value={f.budget_owner_person_id} onChange={set("budget_owner_person_id")}><option value="">—</option>{data.account.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
    <Field label="Funding pool"><select value={f.funding_pool_id} onChange={set("funding_pool_id")}><option value="">—</option>{data.funding.funding_pools.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
    <Field label="Ask calendar"><select value={f.ask_calendar_id} onChange={set("ask_calendar_id")}><option value="">—</option>{data.funding.ask_calendars.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
    <Field label="Source"><select value={f.source_reference_id} onChange={set("source_reference_id")}><option value="">—</option>{data.sources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select></Field>
    <Field label="Competitive notes (internal)"><textarea value={f.competitive_notes} onChange={set("competitive_notes")} /></Field>
    <div className="field checkline"><input id="line-share" type="checkbox" checked={f.client_visible} onChange={set("client_visible")} /><label htmlFor="line-share">Share joint fields to mutual plan</label></div>
  </SlideOver>;
}

function Bullet({value,target,direction}) { const scale=Math.max(value||0,target||0,0.0001)*1.15; const pct=n=>`${Math.min(100,(n||0)/scale*100)}%`; const met=value!=null&&(direction==="at_most"?value<=target:value>=target); return <div aria-label={`Current ${num(value)}, target ${num(target)}, ${met?"met":"not met"}`} style={{position:"relative",height:9,background:"var(--data-muted)",borderRadius:5,marginTop:8,border:"1px solid var(--line-hairline)"}}><div style={{position:"absolute",inset:"0 auto 0 0",width:pct(value),background:"var(--data-1)",borderRadius:5}}/><div title="agreed bar" style={{position:"absolute",left:pct(target),top:-3,bottom:-3,width:2,background:"var(--ink-primary)"}}/></div>; }
function Bridge({rollup}) { const [mode,setMode]=useState("committed"); if(!rollup.additive)return null; const weighted=mode==="weighted"; const uplift=weighted?rollup.probability_weighted_seats:rollup.committed_seats; const gap=weighted?rollup.weighted_gap:rollup.unfunded_gap; const vals=[{l:"Current",v:rollup.current_seats},{l:weighted?"Probability-weighted":"Committed",v:uplift},{l:"Unfunded gap",v:gap}]; return <><div className="actions" style={{marginTop:10}}><button className={`btn small ${!weighted?"primary":"ghost"}`} onClick={()=>setMode("committed")}>Committed</button><button className={`btn small ${weighted?"primary":"ghost"}`} onClick={()=>setMode("weighted")}>Probability-weighted</button><span className="rowmeta">Assumption view; target remains {rollup.target_seats.toLocaleString()} seats.</span></div><div className="grid3" style={{marginTop:8}}>{vals.map(x=><Stat key={x.l} label={x.l} value={x.v?.toLocaleString()??"—"} detail={x.l==="Unfunded gap"?`target ${rollup.target_seats.toLocaleString()}`:"seats"}/>)}</div></>; }
function Stat({label,value,detail}){return <div style={{padding:10,background:"var(--bg-sunken)",border:"1px solid var(--line-hairline)",borderRadius:"var(--r-md)"}}><div className="rowmeta">{label}</div><div className="mono" style={{fontSize:"var(--t-h2)",fontWeight:500}}>{value}</div><div className="rowmeta">{detail}</div></div>;}
function Field({label,children}){return <div className="field"><label>{label}</label>{children}</div>;}
const th={width:190,textAlign:"left",paddingLeft:12};
const num=v=>v==null?"unknown":Number(v).toLocaleString();
const countdown=d=>d==null?"date unavailable":d<0?`${Math.abs(d)} days past`:`T−${d} days`;
