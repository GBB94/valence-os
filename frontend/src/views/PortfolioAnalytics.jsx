import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty, useToast } from "../ui";

const n = (value) => value == null ? "—" : Number(value).toLocaleString();

export default function PortfolioAnalytics() {
  const toast = useToast();
  const [days, setDays] = useState(90);
  const [data, setData] = useState(null);
  useEffect(() => {
    setData(null);
    api.commercialAnalytics(days).then(setData).catch((e) => toast(e.message, "err"));
  }, [days]);
  if (!data) return <div className="subtle" style={{ padding: 12 }}>Loading portfolio facts…</div>;
  const bridge = data.portfolio_bridge;
  return <div>
    <div className="actions" style={{ marginBottom: 14 }}>
      <div><h2 style={{ margin: 0 }}>Portfolio commercial analytics</h2>
        <div className="rowmeta">{data.portfolio_account_count} accounts · {data.window.start}–{data.window.end}</div></div>
      <div className="spacer" />
      <label className="rowmeta">Window&nbsp;
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={30}>30 days</option><option value={90}>90 days</option>
          <option value={180}>180 days</option><option value={365}>365 days</option>
        </select>
      </label>
    </div>

    <div className="grid3" style={{ marginBottom: 14 }}>
      <Fact title="Cell transitions" value={data.whitespace.transition_count}
        note={`from ${data.whitespace.tracked_cell_count} tracked cells`} />
      <Fact title="Proven → funded" value={data.time_to_expansion.median_days == null ? "insufficient data" : `${data.time_to_expansion.median_days} days`}
        note={`${data.time_to_expansion.sample_count} dated samples`} />
      <Fact title="Case → funded" value={data.ask_cycle.median_days == null ? "insufficient data" : `${data.ask_cycle.median_days} days`}
        note={`${data.ask_cycle.sample_count} dated samples`} />
    </div>

    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card-h"><h3>Growth-plan bridge</h3><div className="spacer" />
        <span className="rowmeta">{bridge.accounts_in_total} of {bridge.portfolio_account_count} accounts in totals</span></div>
      {!bridge.totals ? <Empty title="Insufficient data">No non-overlapping active growth plan can be totalled yet.</Empty> : <>
        <div className="grid3" style={{ padding: 12 }}>
          <Fact title="Current seats" value={n(bridge.totals.current_seats)} />
          <Fact title="Named lines" value={n(bridge.totals.named_seats)} />
          <Fact title="Unfunded gap" value={n(bridge.totals.unfunded_gap)} />
        </div>
        <table><thead><tr><th>Account</th><th>Current</th><th>Named</th><th>Committed</th><th>Target</th><th>Gap</th></tr></thead>
          <tbody>{bridge.accounts.map((r) => <tr key={r.account_id}>
            <td>{r.account_name}{!r.additive && <div className="rowmeta">excluded: overlapping lines</div>}</td>
            <td>{n(r.current_seats)}</td><td>{n(r.named_seats)}</td><td>{n(r.committed_seats)}</td>
            <td>{n(r.target_seats)}</td><td>{n(r.unfunded_gap)}</td>
          </tr>)}</tbody></table>
      </>}
      <div className="rowmeta" style={{ padding: "8px 12px" }}>{bridge.basis}</div>
    </div>

    <div className="grid2">
      <div className="card">
        <div className="card-h"><h3>Whitespace movement</h3></div>
        {data.whitespace.transitions.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>Zero dated transitions in this window.</div> :
          <table><thead><tr><th>Transition</th><th>Cells</th><th>Accounts</th></tr></thead><tbody>
            {data.whitespace.transitions.map((r) => <tr key={`${r.from}-${r.to}`}><td>{r.from} → {r.to}</td><td>{r.count}</td><td>{r.account_count}</td></tr>)}
          </tbody></table>}
        <div className="rowmeta" style={{ padding: "8px 12px" }}>{data.whitespace.history_coverage_note}</div>
      </div>
      <div className="card">
        <div className="card-h"><h3>Value targets</h3><div className="spacer" /><span className="rowmeta">{data.value_realization.total} total</span></div>
        {data.value_realization.total === 0 ? <div className="rowmeta" style={{ padding: 12 }}>Insufficient data: no active targets.</div> :
          <table><tbody>{Object.entries(data.value_realization.counts).sort().map(([status, count]) =>
            <tr key={status}><td>{status.replace(/_/g, " ")}</td><td style={{ width: 60 }}>{count}</td></tr>)}</tbody></table>}
      </div>
    </div>

    <div className="card" style={{ marginTop: 14 }}>
      <div className="card-h"><h3>Recurring revenue movement</h3><div className="spacer" />
        <span className="rowmeta">absolute movement; never blended across currencies</span></div>
      <table><thead><tr><th>Account</th><th>Currency</th><th>Base ARR</th><th>Actual movement</th><th>Ending ARR</th><th>Projected expansion</th><th>Events</th></tr></thead>
        <tbody>{data.revenue.accounts.map((r) => <tr key={r.account_id}>
          <td>{r.account_name}</td><td>{r.currency || "unknown"}</td><td>{n(r.base_arr)}</td>
          <td>{n(r.net_movement)}</td><td>{n(r.ending_arr)}</td><td>{r.projected_expansion.insufficient_data ?
            <span className="rowmeta">insufficient data<div>{r.projected_expansion.reason}</div></span> :
            <>{n(r.projected_expansion.low)}–{n(r.projected_expansion.high)}<div className="rowmeta">weighted {n(r.projected_expansion.probability_weighted)}</div></>}</td><td>{r.event_count}</td>
        </tr>)}</tbody></table>
      <div className="rowmeta" style={{ padding: "8px 12px" }}>{data.revenue.note}</div>
    </div>
  </div>;
}

function Fact({ title, value, note }) {
  return <div className="card" style={{ padding: 12 }}><div className="rowmeta">{title}</div>
    <div style={{ fontSize: 22, fontWeight: 600, marginTop: 3 }}>{value}</div>{note && <div className="rowmeta">{note}</div>}</div>;
}
