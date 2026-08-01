/* The value realization ledger (EXPANSION-ENGINE-SPEC.md §2).

   Promised-vs-realized as a record instead of a memory. Two things this screen refuses to do:
   render a stale observation as a good state (past its freshness threshold it is Unknown, not
   last quarter's number), and report a realization RATE (counts and denominators only — a
   percentage over a handful of targets implies precision the sample cannot support). */
import { useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, SlideOver, Unknown, useToast } from "../ui";

// Status -> (glyph, hue). Same rule as the heatmap: never state by color alone.
const REALIZATION = {
  realized:         { glyph: "●", hue: "--status-ok",      label: "Realized" },
  on_track:         { glyph: "◐", hue: "--status-ok",      label: "On track" },
  at_risk:          { glyph: "◑", hue: "--status-warn",    label: "At risk" },
  not_demonstrated: { glyph: "○", hue: "--status-risk",    label: "Not demonstrated" },
  unknown:          { glyph: "?", hue: "--status-unknown", label: "Unknown" },
  // The cohort is too small for its metric to leave the service (§1.2). Distinct from
  // "unknown" (stale) — this value exists and is deliberately withheld.
  suppressed:       { glyph: "▨", hue: "--status-unknown", label: "Suppressed" },
};
// A status the backend adds later must not blank the screen.
const FALLBACK = { glyph: "?", hue: "--status-unknown", label: "Unknown" };

export default function ValueLedger({ accountId, reloadKey }) {
  const toast = useToast();
  const [led, setLed] = useState(null);
  const [panel, setPanel] = useState(null);
  const [evidenceTarget, setEvidenceTarget] = useState(null);
  const [tick, setTick] = useState(0);

  async function load() {
    if (!accountId) return;
    try { setLed(await api.ledger(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);

  if (!accountId) return <Empty title="No account selected">Pick an account.</Empty>;
  if (!led) return <div className="subtle" style={{ padding: 12 }}>Loading…</div>;

  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <h3>Value realization ledger</h3>
          <div className="spacer" />
          <button className="btn small" onClick={() => setPanel({ kind: "target" })}>New value target</button>
        </div>

        {/* Counts, never a rate (§10). */}
        <div style={countsBar}>
          {Object.keys(REALIZATION).map((k) => (
            led.counts[k] ? (
              <span key={k} style={countChip}>
                <span aria-hidden="true" style={{ color: `var(${REALIZATION[k].hue})` }}>
                  {REALIZATION[k].glyph}
                </span>
                <span className="rowmeta">{led.counts[k]} {REALIZATION[k].label.toLowerCase()}</span>
              </span>
            ) : null
          ))}
          <span className="rowmeta" style={{ marginLeft: "auto" }}>
            {led.total} target{led.total === 1 ? "" : "s"} of record
          </span>
        </div>

        {led.targets.length === 0 ? (
          <Empty title="No value targets yet">
            Every business case, renewal, and expansion should carry the bar it promised: the
            metric, the target, the population, the timeframe, and who accepted it.
          </Empty>
        ) : (
          <table>
            <thead><tr>
              <th scope="col">Metric &amp; population</th>
              <th scope="col" style={{ width: 120 }}>Bar</th>
              <th scope="col" style={{ width: 120 }}>Current</th>
              <th scope="col" style={{ width: 160 }}>Status</th>
              <th scope="col" style={{ width: 110 }}>By</th>
              <th scope="col" style={{ width: 92 }}></th>
            </tr></thead>
            <tbody>
              {led.targets.map((t) => {
                const r = t.realization;
                const st = REALIZATION[r.status] || FALLBACK;
                return (
                  <tr key={t.id}>
                    <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                      {t.metric}
                      <div className="rowmeta">
                        {t.population}
                        {t.accepted_by_name ? ` · accepted by ${t.accepted_by_name}` : " · not accepted"}
                        {t.version > 1 ? ` · v${t.version}` : ""}
                      </div>
                    </th>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {t.direction === "at_most" ? "≤ " : "≥ "}{t.target_value}
                      {t.unit ? ` ${t.unit}` : ""}
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {r.value == null ? <Unknown since={r.current_through} /> : r.value}
                      {r.current_through && r.value != null && <AgeChip date={r.current_through} />}
                    </td>
                    <td>
                      <span aria-hidden="true" style={{ color: `var(${st.hue})`, marginRight: 5 }}>
                        {st.glyph}
                      </span>
                      {st.label}
                      {r.reason && <div className="rowmeta">{r.reason}</div>}
                    </td>
                    <td className="rowmeta">{t.timeframe_end}</td>
                    <td><button className="btn small ghost" onClick={() => setEvidenceTarget(t)}>Evidence</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* The value gap: paid and active with nothing demonstrated. Same condition as the map's
          "Penetrated, unevidenced" state, computed once so the two can never disagree. */}
      {led.value_gaps.length > 0 && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="card-h">
            <h3>Value gaps</h3>
            <div className="spacer" />
            <span className="rowmeta">{led.value_gaps.length} cohort{led.value_gaps.length === 1 ? "" : "s"}</span>
          </div>
          <div className="rowmeta" style={{ padding: "0 12px 8px" }}>
            High usage with undemonstrated outcomes looks healthy and churns anyway. Close these
            before the renewal window opens.
          </div>
          <table>
            <thead><tr>
              <th scope="col">Cohort</th>
              <th scope="col" style={{ width: 90 }}>Paid</th>
              <th scope="col">Why it is a gap</th>
            </tr></thead>
            <tbody>
              {led.value_gaps.map((g) => (
                <tr key={g.cell_id}>
                  <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                    {g.population}
                    <div className="rowmeta">{g.use_case}</div>
                  </th>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>{g.paid_seats.toLocaleString()}</td>
                  <td className="rowmeta">{g.because}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {panel && (
        <TargetPanel accountId={accountId} onClose={() => setPanel(null)}
                     onSaved={() => { setPanel(null); setTick((t) => t + 1); }} />
      )}
      {evidenceTarget && <TargetEvidence target={evidenceTarget} onClose={() => setEvidenceTarget(null)}
                         onSaved={() => { setEvidenceTarget(null); setTick((t) => t + 1); }} />}
    </>
  );
}

function TargetPanel({ accountId, onClose, onSaved }) {
  const toast = useToast();
  const [defs, setDefs] = useState([]);
  const [segments, setSegments] = useState([]);
  const [views, setViews] = useState([]);
  const [people, setPeople] = useState([]);
  const [sources, setSources] = useState([]);
  const [f, setF] = useState({
    definition_id: "", population_id: "", target_value: "", direction: "at_least",
    timeframe_start: "", timeframe_end: "", accepted_by_person_id: "", accepted_on: "",
    client_accepted: false, client_visible: false, source_reference_id: "",
  });

  useEffect(() => {
    (async () => {
      try {
        const [d, part, acct, vs, refs] = await Promise.all([
          api.metricDefinitions(), api.partition(accountId).catch(() => null), api.account(accountId),
          api.populationViews(accountId), api.sourceReferences(),
        ]);
        setDefs(d); setSegments(part?.segments || []); setPeople(acct.people || []);
        setViews(vs); setSources(refs);
      } catch (e) { toast(e.message, "err"); }
    })();
  }, [accountId]);

  async function save(e) {
    e.preventDefault();
    try {
      await api.createValueTarget({
        account_id: accountId,
        definition_id: f.definition_id,
        segment_id: f.population_id.startsWith("segment:") ? f.population_id.slice(8) : null,
        view_id: f.population_id.startsWith("view:") ? f.population_id.slice(5) : null,
        target_value: Number(f.target_value),
        direction: f.direction,
        timeframe_start: f.timeframe_start || null,
        timeframe_end: f.timeframe_end,
        accepted_by_person_id: f.accepted_by_person_id || null,
        accepted_on: f.accepted_on || null,
        client_accepted: f.client_accepted,
        client_visible: f.client_visible,
        source_reference_id: f.source_reference_id || null,
      });
      toast("Value target recorded");
      onSaved();
    } catch (err) { toast(err.message, "err"); }
  }

  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <SlideOver title="New value target" onClose={onClose}>
      <form onSubmit={save}>
        <label style={lbl}>Metric
          <select value={f.definition_id} onChange={set("definition_id")} required style={sel}>
            <option value="">choose…</option>
            {defs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
        <label style={lbl}>Population
          <select value={f.population_id} onChange={set("population_id")} style={sel}>
            <option value="">Account-wide</option>
            {segments.map((s) => <option key={s.id} value={`segment:${s.id}`}>{s.name} (segment)</option>)}
            {views.map((v) => <option key={v.id} value={`view:${v.id}`}>{v.name} (composite)</option>)}
          </select>
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...lbl, flex: 1 }}>Direction
            <select value={f.direction} onChange={set("direction")} style={sel}>
              <option value="at_least">at least</option>
              <option value="at_most">at most</option>
            </select>
          </label>
          <label style={{ ...lbl, flex: 1 }}>Target
            <input type="number" step="any" value={f.target_value} onChange={set("target_value")}
                   required style={sel} />
          </label>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...lbl, flex: 1 }}>From<input type="date" value={f.timeframe_start} onChange={set("timeframe_start")} style={sel} /></label>
          <label style={{ ...lbl, flex: 1 }}>By when<input type="date" value={f.timeframe_end} onChange={set("timeframe_end")} required style={sel} /></label>
        </div>

        <label style={{ ...lbl, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={f.client_accepted} onChange={set("client_accepted")} />
          <span>The client accepted this bar</span>
        </label>
        {f.client_accepted && (
          <>
            <div className="rowmeta" style={{ marginBottom: 8 }}>
              An accepted target needs who accepted it and when — otherwise it is an aspiration.
            </div>
            <label style={lbl}>Accepted by
              <select value={f.accepted_by_person_id} onChange={set("accepted_by_person_id")} required style={sel}>
                <option value="">choose…</option>
                {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label style={lbl}>Accepted on
              <input type="date" value={f.accepted_on} onChange={set("accepted_on")} required style={sel} />
            </label>
          </>
        )}
        <label style={lbl}>Source
          <select value={f.source_reference_id} onChange={set("source_reference_id")} style={sel}>
            <option value="">none</option>{sources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        <label style={{ ...lbl, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={f.client_visible} onChange={set("client_visible")} />
          <span>Include in client-facing artifacts (requires acceptance and a source)</span>
        </label>
        <button className="btn small primary" type="submit" style={{ marginTop: 8 }}>Record target</button>
      </form>
    </SlideOver>
  );
}

function TargetEvidence({ target, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ object_type: "metric_observation", object_id: "", note: "" });
  const [stories, setStories] = useState([]);
  const [observations, setObservations] = useState([]);
  useEffect(() => {
    Promise.all([api.valueStories(target.account_id), api.accountMetricObservations(target.account_id)])
      .then(([storyRows, obsRows]) => { setStories(storyRows); setObservations(obsRows); })
      .catch((e) => toast(e.message, "err"));
  }, [target.account_id]);
  return <SlideOver title={`Evidence — ${target.metric}`} onClose={onClose}>
    <div className="rowmeta" style={{ marginBottom: 10 }}>Only evidence from this account and matching cohort can be linked.</div>
    {(target.evidence || []).map((e) => <div key={e.id} className="rowmeta">{e.object_type} · {e.object_id}{e.note ? ` — ${e.note}` : ""}</div>)}
    <form onSubmit={async (e) => { e.preventDefault(); try {
      await api.linkValueTargetEvidence(target.id, f); toast("Evidence linked"); onSaved();
    } catch (err) { toast(err.message, "err"); } }} style={{ marginTop: 12 }}>
      <label style={lbl}>Evidence type<select value={f.object_type} onChange={(e) => setF({ ...f, object_type: e.target.value, object_id: "" })} style={sel}>
        <option value="metric_observation">metric observation</option><option value="value_story">value story</option>
      </select></label>
      <label style={lbl}>Evidence<select value={f.object_id} onChange={(e) => setF({ ...f, object_id: e.target.value })} required style={sel}>
        <option value="">choose…</option>
        {(f.object_type === "value_story" ? stories : observations).map((row) => <option key={row.id} value={row.id}>
          {f.object_type === "value_story" ? row.outcome : `${row.metric_name} · ${row.segment_name || row.view_name || row.program_name || "account"} · ${row.current_through}`}
        </option>)}
      </select></label>
      <label style={lbl}>Note<textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} rows={2} style={sel} /></label>
      <button className="btn small primary" type="submit">Link evidence</button>
    </form>
  </SlideOver>;
}

const countsBar = {
  display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center",
  padding: "8px 12px", borderBottom: "1px solid var(--line-hairline)",
};
const countChip = { display: "inline-flex", alignItems: "center", gap: 5 };
const lbl = { display: "flex", flexDirection: "column", gap: 4, marginBottom: 10, fontSize: 13 };
const sel = {
  padding: "6px 8px", borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--line-hairline)", background: "var(--surface-1, transparent)",
  color: "var(--ink-primary)",
};
