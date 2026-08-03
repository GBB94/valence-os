/* The whitespace map — the Commercial tab's signature surface
   (EXPANSION-ENGINE-SPEC.md §1, DESIGN-GUIDE.md amendment in §1.3).

   Design constraints this component exists to honor:

   * NO NEW COLOR SYSTEM. The cell states ARE statuses, so the grid reuses --status-ok /
     --status-warn / --status-risk / --status-unknown. The guide's "budget waterfall is the
     single non-status color exception" rule therefore stands unamended — this is an
     extension of the existing status palette, not a carve-out from it.
   * NO STATE BY COLOR ALONE. Seven states over four hues, so every cell carries a glyph AND
     a label. That is also what keeps Penetrated and Penetrated-unevidenced distinguishable
     sitting next to each other.
   * INTENSITY ENCODES DENSITY ONLY. Paid density is a lightness ramp *within* the cell's own
     hue via the tint token. Intensity is never the difference between two states.
   * SEMANTIC TABLE. Real <table> with scope-associated headers, arrow-key cell navigation,
     and a per-cell accessible name reading population, use case, state, and density — the
     map has to be usable without seeing it.
   * D-70 ADJACENCY. This is a status surface, so no financial chart shares its card. */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, SlideOver, Unknown, useToast } from "../ui";

// state -> (glyph, hue token, tint token, ink). `hue` tints the fill and the border; `ink`
// is what the glyph is drawn in.
//
// The two neutral states draw their glyph in --ink-secondary rather than --status-unknown:
// measured on the unknown tint, --status-unknown gives 3.74:1, under the 4.5:1 floor. They
// have no status hue to carry anyway ("no status" is the point), so neutral ink is both more
// legible and more honest. The four real status states keep their hue, which clears the floor.
const STATE_STYLE = {
  penetrated:             { glyph: "●", hue: "--status-ok",      tint: "--status-ok-tint",      ink: "--status-ok" },
  penetrated_unevidenced: { glyph: "◐", hue: "--status-warn",    tint: "--status-warn-tint",    ink: "--status-warn" },
  proven:                 { glyph: "◑", hue: "--status-warn",    tint: "--status-warn-tint",    ink: "--status-warn" },
  target:                 { glyph: "○", hue: "--status-unknown", tint: "--status-unknown-tint", ink: "--ink-secondary" },
  white:                  { glyph: "·", hue: "--status-unknown", tint: "--status-unknown-tint", ink: "--ink-secondary" },
  blocked:                { glyph: "▲", hue: "--status-risk",    tint: "--status-risk-tint",    ink: "--status-risk" },
  declined:               { glyph: "✕", hue: "--status-risk",    tint: "--status-risk-tint",    ink: "--status-risk" },
};

const FACTS = {
  penetration: ["none", "pilot", "paid"],
  evidence_state: ["none", "anecdotal", "measured"],
  blocker_state: ["clear", "gated"],
  pursuit_outcome: ["none", "declined", "won", "deferred"],
};
const LANES = ["works_council", "it", "legal", "localization", "other"];
const pct = (v) => (v == null ? "—" : (v * 100).toFixed(0) + "%");

export default function Whitespace({ accountId, reloadKey }) {
  const toast = useToast();
  const [map, setMap] = useState(null);
  const [next, setNext] = useState(null);
  const [outside, setOutside] = useState(null);
  const [showOutside, setShowOutside] = useState(false);
  const [openCell, setOpenCell] = useState(null);
  const [setup, setSetup] = useState(false);
  const [tick, setTick] = useState(0);
  const gridRef = useRef(null);

  async function load() {
    if (!accountId) return;
    try {
      const [m, n, o] = await Promise.all([api.whitespace(accountId), api.nextSeats(accountId), api.companyWorkspace(accountId)]);
      setMap(m); setNext(n); setOutside(o.overlay || null);
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);

  const rows = useMemo(
    () => (map ? [...map.segment_rows, ...map.view_rows] : []), [map]);

  // Arrow-key navigation across the grid: a heatmap you can only reach with a mouse is not
  // usable, and tabbing through 60 cells is not navigation.
  function onGridKeyDown(e) {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    const cell = e.target.closest("td[data-r]");
    if (!cell) return;
    e.preventDefault();
    const r = Number(cell.dataset.r), c = Number(cell.dataset.c);
    const d = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
    const target = gridRef.current?.querySelector(`td[data-r="${r + d[0]}"][data-c="${c + d[1]}"] button`);
    target?.focus();
  }

  if (!accountId) return <Empty title="No account selected">Pick an account to see its map.</Empty>;
  if (!map) return <div className="subtle" style={{ padding: 12 }}>Loading…</div>;

  if (!map.partition) {
    return (<>
      <div className="card">
        <div className="card-h"><h3>Whitespace map</h3></div>
        <Empty title="No base partition yet">
          The map needs a base population partition first — a set of mutually exclusive segments
          covering the account's total FTE. It is the only additive dimension, so nothing can be
          counted until it exists.
          <div style={{ marginTop: 10 }}><button className="btn small primary" onClick={() => setSetup(true)}>Set up base population</button></div>
        </Empty>
      </div>
      {setup && <PopulationSetup accountId={accountId} onClose={() => setSetup(false)}
                                 onChanged={() => { setSetup(false); setTick((t) => t + 1); }} />}
    </>);
  }

  const rec = map.reconciliation;

  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-h">
          <h3>Whitespace map</h3>
          <div className="spacer" />
          <span className="rowmeta">
            {map.rollup.paid_seats.toLocaleString()} paid of{" "}
            {map.rollup.addressable_seats.toLocaleString()} addressable
          </span>
          <button className="btn small" onClick={() => setSetup(true)}>Manage populations</button>
          <button className="btn small ghost" aria-pressed={showOutside} onClick={() => setShowOutside((v) => !v)}>
            {showOutside ? "Hide" : "Show"} outside-in
          </button>
        </div>

        {/* Reconciliation: the visible remainder is what stops the map claiming more
            addressable seats than the company has people (§1.1). */}
        <div style={reconBar} role="note">
          {rec.total_fte == null ? (
            <span className="rowmeta">No total FTE on the partition — the map cannot reconcile.</span>
          ) : rec.reconciles ? (
            <span className="rowmeta">
              Reconciles: {rec.allocated_headcount.toLocaleString()} allocated +{" "}
              {(rec.unallocated_headcount || 0).toLocaleString()} unallocated ={" "}
              {rec.total_fte.toLocaleString()} FTE
            </span>
          ) : (
            <span className="rowmeta" style={{ color: "var(--status-warn)" }}>
              ⚠ {rec.allocated_headcount.toLocaleString()} allocated against{" "}
              {rec.total_fte.toLocaleString()} FTE — {Math.abs(rec.remainder).toLocaleString()}{" "}
              {rec.remainder > 0 ? "unaccounted for" : "over the company headcount"}
            </span>
          )}
        </div>

        <div style={{ overflowX: "auto" }} onKeyDown={onGridKeyDown} ref={gridRef}>
          <table style={{ minWidth: 640 }}>
            <caption style={srOnly}>
              Whitespace map: populations by use case. Segment rows are additive; composite view
              rows overlap their segments and are not additive.
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ minWidth: 190 }}>Population</th>
                <th scope="col" style={{ width: 96 }}>Headcount</th>
                {map.use_cases.map((u) => (
                  <th key={u.id} scope="col" style={{ minWidth: 132 }}>
                    {u.name}
                    {showOutside && <OutsideMarker events={outside?.use_cases?.[u.id]} />}
                    {!u.portfolio_comparable && (
                      <div className="rowmeta" style={{ fontWeight: 400 }}>account-specific</div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={`${row.row_type}-${row.id}`}>
                  <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                    {row.name}
                    {showOutside && <OutsideMarker events={outside?.[row.row_type === "view" ? "views" : "segments"]?.[row.id]} />}
                    <div className="rowmeta">
                      {row.row_type === "view" ? "composite · not additive" :
                        row.is_unallocated ? "unallocated remainder" : "segment"}
                      {row.paid_seats > 0 && ` · ${row.paid_seats.toLocaleString()} paid`}
                    </div>
                  </th>
                  <td>
                    {row.headcount == null ? <Unknown /> : (
                      <>
                        {row.headcount.toLocaleString()}
                        {row.headcount_as_of && <AgeChip date={row.headcount_as_of} />}
                      </>
                    )}
                  </td>
                  {row.cells.map((slot, ci) => (
                    <td key={slot.use_case_id} data-r={ri} data-c={ci} style={{ padding: 4 }}>
                      <CellButton
                        slot={slot} row={row}
                        onOpen={() => slot.cell
                          ? setOpenCell(slot.cell.id)
                          : createCell(slot, row)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Legend />
        <div className="rowmeta" style={{ padding: "8px 12px 12px" }}>
          A seat is one person-license owned by the row. Use cases are entitlements on a seat,
          not separate inventories — cell figures do not sum across a row.
        </div>
      </div>

      {next && next.rows.length > 0 && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="card-h">
            <h3>Where the next seats live</h3>
            <div className="spacer" />
            <span className="rowmeta">{next.total_unpenetrated.toLocaleString()} unpenetrated</span>
          </div>
          <table>
            <thead><tr>
              <th scope="col">Population</th>
              <th scope="col" style={{ width: 130 }}>Unpenetrated</th>
              <th scope="col">Cheapest next move</th>
            </tr></thead>
            <tbody>
              {next.rows.map((r) => (
                <tr key={r.segment_id}>
                  <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                    {r.segment}
                    <div className="rowmeta">
                      {r.paid_seats.toLocaleString()} paid of {(r.headcount || 0).toLocaleString()}
                      {r.headcount_source ? ` · ${r.headcount_source}` : ""}
                      {r.headcount_as_of && <AgeChip date={r.headcount_as_of} />}
                    </div>
                  </th>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>
                    {r.unpenetrated_seats.toLocaleString()}
                  </td>
                  <td className="rowmeta">
                    {r.best_motion
                      ? <>{r.best_motion.use_case} — {r.best_motion.move}</>
                      : "No cells yet for this population"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {openCell && (
        <CellPanel cellId={openCell} accountId={accountId} onClose={() => setOpenCell(null)}
                   onChanged={() => { setTick((t) => t + 1); }} />
      )}
      {setup && <PopulationSetup accountId={accountId} partition={map.partition}
                                 segments={map.segment_rows} onClose={() => setSetup(false)}
                                 onChanged={() => { setSetup(false); setTick((t) => t + 1); }} />}
    </>
  );

  async function createCell(slot, row) {
    try {
      const body = { account_id: accountId, use_case_id: slot.use_case_id };
      if (row.row_type === "segment") body.segment_id = row.id; else body.view_id = row.id;
      const c = await api.createCell(body);
      setTick((t) => t + 1);
      setOpenCell(c.id);
    } catch (e) { toast(e.message, "err"); }
  }
}

function CellButton({ slot, row, onOpen }) {
  const cell = slot.cell;
  if (!cell) {
    return (
      <button onClick={onOpen} style={emptyCell}
              aria-label={`${row.name}, ${slot.use_case}: no cell yet. Activate to create one.`}>
        <span aria-hidden="true">+</span>
      </button>
    );
  }
  const st = STATE_STYLE[cell.state];
  const density = cell.paid_density;
  // Intensity encodes density only, as an alpha ramp over the state's own tint, so it can
  // never be mistaken for a different state.
  const fill = density?.suppressed || density?.value == null ? 0 : Math.min(density.value, 1);
  const label =
    `${row.name}, ${slot.use_case}: ${cell.state_label}. ` +
    `${cell.paid_seats.toLocaleString()} paid seats. ` +
    (density?.suppressed ? "Density suppressed, cohort too small."
      : density?.value != null ? `Density ${pct(density.value)}.` : "Density unknown.") +
    ` Next: ${cell.state_move}.`;

  return (
    <button onClick={onOpen} aria-label={label} title={cell.state_move}
            style={{
              ...cellBtn,
              background: `color-mix(in srgb, var(${st.hue}) ${Math.round(fill * 34)}%, var(${st.tint}))`,
              borderColor: `var(${st.hue})`,
            }}>
      <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
        <span aria-hidden="true" style={{ color: `var(${st.ink})`, fontSize: 13, lineHeight: 1 }}>
          {st.glyph}
        </span>
        <span style={{ fontSize: 11, fontWeight: 500 }}>{cell.state_label}</span>
      </span>
      {/* --ink-tertiary (the .rowmeta default) drops to 4.1:1 against a tinted cell, so the
          density line steps up to --ink-secondary rather than inheriting. */}
      <span className="rowmeta" style={{ fontSize: 10, color: "var(--ink-secondary)" }}>
        {cell.paid_seats > 0 ? `${cell.paid_seats.toLocaleString()} paid` : "—"}
        {density?.suppressed ? " · suppressed" : density?.value != null ? ` · ${pct(density.value)}` : ""}
      </span>
    </button>
  );
}

function Legend() {
  return (
    <div style={legendWrap}>
      {Object.entries(STATE_STYLE).map(([state, st]) => (
        <span key={state} style={legendItem}>
          <span aria-hidden="true" style={{ color: `var(${st.ink})` }}>{st.glyph}</span>
          <span className="rowmeta">{state.replace(/_/g, " ")}</span>
        </span>
      ))}
      <span style={{ ...legendItem, marginLeft: "auto" }}>
        <span className="rowmeta">Fill intensity = paid density</span>
      </span>
    </div>
  );
}

function OutsideMarker({ events }) {
  if (!events?.length) return null;
  const title = events.map((event) => event.summary).join("\n");
  // Focusable, and the aria-label carries the summaries themselves: the content must not
  // exist only behind a hover-only title tooltip.
  return <span className="badge" title={title} tabIndex={0}
    aria-label={`${events.length} confirmed outside-in event${events.length === 1 ? "" : "s"}: ${title.replaceAll("\n", "; ")}`}
    style={{ marginLeft: 6, whiteSpace: "nowrap" }}>⚑ {events.length}</span>;
}

/* The cell card. Shows ALL FOUR stored facts even though the heatmap shows one derived state,
   so nothing is hidden by the display precedence. Facts change only with a reason (§1.3). */
function CellPanel({ cellId, accountId, onClose, onChanged }) {
  const toast = useToast();
  const [cell, setCell] = useState(null);
  const [fact, setFact] = useState("penetration");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [lane, setLane] = useState("works_council");
  const [people, setPeople] = useState([]);
  const [sources, setSources] = useState([]);
  const [stories, setStories] = useState([]);
  const [observations, setObservations] = useState([]);
  const [matches, setMatches] = useState(null);
  const [edit, setEdit] = useState({ estimated_seats: "", paid_seats: "", sponsor_person_id: "",
    next_action: "", notes: "", source_reference_id: "", client_visible: false });
  const [evidence, setEvidence] = useState({ object_type: "value_story", object_id: "", note: "" });

  async function load() {
    try {
      const [c, ps, refs, storyRows, obsRows, matchRows] = await Promise.all([
        api.cell(cellId), api.persons(accountId), api.sourceReferences(),
        api.valueStories(accountId), api.accountMetricObservations(accountId), api.playbookMatches(cellId)]);
      setCell(c); setPeople(ps); setSources(refs); setStories(storyRows); setObservations(obsRows);
      setMatches(matchRows);
      setEdit({ estimated_seats: c.estimated_seats ?? "", paid_seats: c.paid_seats ?? "",
        sponsor_person_id: c.sponsor_person_id || "", next_action: c.next_action || "",
        notes: c.notes || "", source_reference_id: c.source_reference_id || "",
        client_visible: Boolean(c.client_visible) });
    } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [cellId]);

  async function submitFact(e) {
    e.preventDefault();
    try {
      const body = { fact, value, reason };
      if (fact === "blocker_state" && value === "gated") body.blocker_lane = lane;
      await api.setCellFact(cellId, body);
      toast("Recorded with reason");
      setReason(""); setValue("");
      await load(); onChanged();
    } catch (err) { toast(err.message, "err"); }
  }

  async function reopen() {
    if (!reason.trim()) { toast("A reopen needs the changed reason", "err"); return; }
    try {
      await api.reopenCell(cellId, { reason });
      toast("Reopened"); setReason(""); await load(); onChanged();
    } catch (err) { toast(err.message, "err"); }
  }

  if (!cell) return <SlideOver title="Cell" onClose={onClose}><div className="subtle">Loading…</div></SlideOver>;
  const st = STATE_STYLE[cell.state];

  return (
    <SlideOver title={cell.state_label} onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span aria-hidden="true" style={{ color: `var(${st.ink})`, fontSize: 16 }}>{st.glyph}</span>
        <strong>{cell.state_label}</strong>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>{cell.state_move}</div>

      <h4 style={h4}>Stored facts</h4>
      <div className="rowmeta" style={{ marginBottom: 8 }}>
        The heatmap shows one derived state; these four are what is actually recorded.
      </div>
      <table style={{ marginBottom: 16 }}>
        <tbody>
          {Object.keys(FACTS).map((f) => (
            <tr key={f}>
              <th scope="row" style={{ textAlign: "left", fontWeight: 400 }} className="rowmeta">
                {f.replace(/_/g, " ")}
              </th>
              <td>{cell[f]}
                {f === "blocker_state" && cell.blocker_lane ? ` · ${cell.blocker_lane.replace(/_/g, " ")}` : ""}
                {f === "pursuit_outcome" && cell.declined_on ? ` · ${cell.declined_on}` : ""}
              </td>
            </tr>
          ))}
          <tr>
            <th scope="row" style={{ textAlign: "left", fontWeight: 400 }} className="rowmeta">paid seats</th>
            <td>{cell.paid_seats.toLocaleString()}</td>
          </tr>
        </tbody>
      </table>

      <h4 style={h4}>Change a fact</h4>
      <form onSubmit={submitFact}>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <select value={fact} onChange={(e) => { setFact(e.target.value); setValue(""); }} style={sel}>
            {Object.keys(FACTS).map((f) => <option key={f} value={f}>{f.replace(/_/g, " ")}</option>)}
          </select>
          <select value={value} onChange={(e) => setValue(e.target.value)} style={sel} required>
            <option value="">choose…</option>
            {FACTS[fact].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        {fact === "blocker_state" && value === "gated" && (
          <select value={lane} onChange={(e) => setLane(e.target.value)} style={{ ...sel, marginBottom: 8 }}>
            {LANES.map((l) => <option key={l} value={l}>{l.replace(/_/g, " ")}</option>)}
          </select>
        )}
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} required
                  placeholder="Reason — required. Cell states change only with a reason logged."
                  style={ta} />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="btn small primary" type="submit">Record change</button>
          {cell.pursuit_outcome === "declined" && (
            <button className="btn small" type="button" onClick={reopen}>
              Reopen — the reason changed
            </button>
          )}
        </div>
      </form>

      <h4 style={{ ...h4, marginTop: 20 }}>Commercial details &amp; sharing</h4>
      <form onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api.patchCell(cellId, { ...edit,
            estimated_seats: edit.estimated_seats === "" ? null : Number(edit.estimated_seats),
            paid_seats: edit.paid_seats === "" ? 0 : Number(edit.paid_seats),
            sponsor_person_id: edit.sponsor_person_id || null,
            source_reference_id: edit.source_reference_id || null });
          toast("Cell details saved"); await load(); onChanged();
        } catch (err) { toast(err.message, "err"); }
      }}>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ ...field, flex: 1 }}>Estimated seats<input type="number" value={edit.estimated_seats} onChange={(e) => setEdit({ ...edit, estimated_seats: e.target.value })} style={sel} /></label>
          <label style={{ ...field, flex: 1 }}>Paid seats<input type="number" value={edit.paid_seats} onChange={(e) => setEdit({ ...edit, paid_seats: e.target.value })} style={sel} /></label>
        </div>
        <label style={field}>Sponsor<select value={edit.sponsor_person_id} onChange={(e) => setEdit({ ...edit, sponsor_person_id: e.target.value })} style={sel}>
          <option value="">none</option>{people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label>
        <label style={field}>Next action<input value={edit.next_action} onChange={(e) => setEdit({ ...edit, next_action: e.target.value })} style={sel} /></label>
        <label style={field}>Notes<textarea value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} rows={2} style={ta} /></label>
        <label style={field}>Source<select value={edit.source_reference_id} onChange={(e) => setEdit({ ...edit, source_reference_id: e.target.value })} style={sel}>
          <option value="">none</option>{sources.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select></label>
        <label style={{ ...field, flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={edit.client_visible} onChange={(e) => setEdit({ ...edit, client_visible: e.target.checked })} />
          Include this cell in client-facing artifacts (requires a source)
        </label>
        <button className="btn small" type="submit">Save details</button>
      </form>

      <h4 style={{ ...h4, marginTop: 20 }}>Evidence</h4>
      {(cell.evidence || []).map((e) => <div className="rowmeta" key={e.id}>{e.object_type} · {e.object_id}{e.note ? ` — ${e.note}` : ""}</div>)}
      <form className="actions" style={{ marginTop: 8 }} onSubmit={async (e) => {
        e.preventDefault();
        try { await api.linkCellEvidence(cellId, evidence); toast("Evidence linked"); setEvidence({ ...evidence, object_id: "", note: "" }); await load(); }
        catch (err) { toast(err.message, "err"); }
      }}>
        <select value={evidence.object_type} onChange={(e) => setEvidence({ ...evidence, object_type: e.target.value, object_id: "" })} style={sel}>
          <option value="value_story">value story</option><option value="metric_observation">metric observation</option>
        </select>
        <select value={evidence.object_id} onChange={(e) => setEvidence({ ...evidence, object_id: e.target.value })} required style={{ ...sel, flex: 1 }}>
          <option value="">choose evidence…</option>
          {(evidence.object_type === "value_story" ? stories : observations).map((row) => (
            <option key={row.id} value={row.id}>{evidence.object_type === "value_story"
              ? row.outcome : `${row.metric_name} · ${row.segment_name || row.view_name || row.program_name || "account"} · ${row.current_through}`}</option>
          ))}
        </select>
        <button className="btn small" type="submit">Link</button>
      </form>

      <h4 style={{ ...h4, marginTop: 20 }}>History</h4>
      {cell.history.length === 0 ? (
        <div className="rowmeta">No changes recorded yet.</div>
      ) : (
        <table>
          <thead><tr>
            <th scope="col">What</th><th scope="col">Reason</th><th scope="col" style={{ width: 92 }}>When</th>
          </tr></thead>
          <tbody>
            {cell.history.map((h) => (
              <tr key={h.id}>
                <td className="rowmeta">
                  {h.fact === "reopened" ? "reopened" : `${h.fact.replace(/_/g, " ")}: ${h.before_value} → ${h.after_value}`}
                </td>
                <td>{h.reason}</td>
                <td className="rowmeta">{h.changed_on}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 style={{ ...h4, marginTop: 20 }}>Nearest playbook learning</h4>
      {!matches?.cross_account_eligible ? <div className="rowmeta">{matches?.reason}</div> :
        matches.matches.length === 0 ? <div className="rowmeta">No learned motion for this global use case yet.</div> :
        matches.matches.slice(0, 5).map((entry) => <div className="card" key={entry.id} style={{ padding: 10, marginBottom: 8 }}>
          <div><strong>{entry.motion_run}</strong> <span className="badge">{entry.transition_to}</span></div>
          <div className="rowmeta">{entry.match_reason} · {entry.account_name} · {entry.transitioned_on}</div>
          {entry.what_worked && <div style={{ marginTop: 5 }}>{entry.what_worked}</div>}
          {entry.what_differently && <div className="rowmeta">Next time: {entry.what_differently}</div>}
        </div>)}
    </SlideOver>
  );
}

function PopulationSetup({ accountId, partition, segments = [], onClose, onChanged }) {
  const toast = useToast();
  const [mode, setMode] = useState(partition ? "segment" : "partition");
  const [selectedSegments, setSelectedSegments] = useState([]);
  const [f, setF] = useState({ total_fte: "", basis: "Business unit", fte_source: "", fte_as_of: "",
    name: "", headcount: "", headcount_source: "", headcount_as_of: "", paid_seats: "",
    paid_seats_source: "", paid_seats_as_of: "", is_unallocated: false, use_case: "", slug: "",
    view_name: "", view_headcount: "", view_source: "", view_as_of: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  async function save(e) {
    e.preventDefault();
    try {
      if (mode === "partition") await api.createPartition({ account_id: accountId, basis: f.basis,
        total_fte: f.total_fte === "" ? null : Number(f.total_fte), fte_source: f.fte_source || null,
        fte_as_of: f.fte_as_of || null });
      if (mode === "segment") await api.createSegment({ partition_id: partition.id, name: f.name,
        headcount: f.headcount === "" ? null : Number(f.headcount), headcount_source: f.headcount_source || null,
        headcount_as_of: f.headcount_as_of || null, paid_seats: f.paid_seats === "" ? null : Number(f.paid_seats),
        paid_seats_source: f.paid_seats_source || null, paid_seats_as_of: f.paid_seats_as_of || null,
        is_unallocated: f.is_unallocated });
      if (mode === "use_case") await api.createUseCase({ account_id: accountId, name: f.use_case,
        slug: f.slug || f.use_case.toLowerCase().replace(/[^a-z0-9]+/g, "-") });
      if (mode === "view") await api.createPopulationView({ account_id: accountId, name: f.view_name,
        segment_ids: selectedSegments, tag_ids: [],
        estimated_headcount: f.view_headcount === "" ? null : Number(f.view_headcount),
        headcount_source: f.view_source || null, headcount_as_of: f.view_as_of || null });
      toast("Population setup saved"); onChanged();
    } catch (err) { toast(err.message, "err"); }
  }
  return <SlideOver title="Population setup" onClose={onClose}>
    {partition && <div className="actions" style={{ marginBottom: 12 }}>
      <button className={`btn small ${mode === "segment" ? "primary" : ""}`} onClick={() => setMode("segment")}>Add segment</button>
      <button className={`btn small ${mode === "use_case" ? "primary" : ""}`} onClick={() => setMode("use_case")}>Add use case</button>
      <button className={`btn small ${mode === "view" ? "primary" : ""}`} onClick={() => setMode("view")}>Add composite view</button>
    </div>}
    <form onSubmit={save}>
      {mode === "partition" && <>
        <label style={field}>Total FTE<input type="number" min="0" value={f.total_fte} onChange={set("total_fte")} required style={sel} /></label>
        <label style={field}>Partition basis<input value={f.basis} onChange={set("basis")} required style={sel} /></label>
        <label style={field}>Headcount source<input value={f.fte_source} onChange={set("fte_source")} required style={sel} /></label>
        <label style={field}>As of<input type="date" value={f.fte_as_of} onChange={set("fte_as_of")} required style={sel} /></label>
      </>}
      {mode === "segment" && <>
        <div className="rowmeta" style={{ marginBottom: 10 }}>{segments.length} current segment{segments.length === 1 ? "" : "s"}. Segments must stay mutually exclusive.</div>
        <label style={field}>Name<input value={f.name} onChange={set("name")} required style={sel} /></label>
        <div style={{ display: "flex", gap: 8 }}><label style={{ ...field, flex: 1 }}>Headcount<input type="number" min="0" value={f.headcount} onChange={set("headcount")} style={sel} /></label>
          <label style={{ ...field, flex: 1 }}>Paid inventory<input type="number" min="0" value={f.paid_seats} onChange={set("paid_seats")} style={sel} /></label></div>
        <label style={field}>Headcount source<input value={f.headcount_source} onChange={set("headcount_source")} style={sel} /></label>
        <label style={field}>Headcount as of<input type="date" value={f.headcount_as_of} onChange={set("headcount_as_of")} style={sel} /></label>
        <label style={field}>Paid-seat source<input value={f.paid_seats_source} onChange={set("paid_seats_source")} style={sel} /></label>
        <label style={field}>Paid-seat as of<input type="date" value={f.paid_seats_as_of} onChange={set("paid_seats_as_of")} style={sel} /></label>
        <label style={{ ...field, flexDirection: "row", gap: 8 }}><input type="checkbox" checked={f.is_unallocated} onChange={set("is_unallocated")} />Unallocated remainder</label>
      </>}
      {mode === "use_case" && <>
        <label style={field}>Use case name<input value={f.use_case} onChange={set("use_case")} required style={sel} /></label>
        <label style={field}>Slug<input value={f.slug} onChange={set("slug")} placeholder="generated from name" style={sel} /></label>
      </>}
      {mode === "view" && <>
        <div className="rowmeta" style={{ marginBottom: 10 }}>Composite views overlap base segments and never contribute to totals.</div>
        <label style={field}>View name<input value={f.view_name} onChange={set("view_name")} required style={sel} /></label>
        <label style={field}>Estimated headcount<input type="number" min="0" value={f.view_headcount} onChange={set("view_headcount")} style={sel} /></label>
        <label style={field}>Headcount source<input value={f.view_source} onChange={set("view_source")} style={sel} /></label>
        <label style={field}>As of<input type="date" value={f.view_as_of} onChange={set("view_as_of")} style={sel} /></label>
        <div style={{ marginBottom: 10 }}><div className="rowmeta">Constituent segments</div>
          {segments.filter((s) => !s.is_unallocated).map((s) => <label key={s.id} style={{ display: "flex", gap: 8, marginTop: 5 }}>
            <input type="checkbox" checked={selectedSegments.includes(s.id)} onChange={(e) => setSelectedSegments(e.target.checked ? [...selectedSegments, s.id] : selectedSegments.filter((id) => id !== s.id))} />{s.name}
          </label>)}
        </div>
      </>}
      <button className="btn small primary" type="submit">Save</button>
    </form>
  </SlideOver>;
}

const srOnly = {
  position: "absolute", width: 1, height: 1, padding: 0, margin: -1,
  overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap", border: 0,
};
const reconBar = {
  padding: "8px 12px", borderBottom: "1px solid var(--line-hairline)",
};
const cellBtn = {
  width: "100%", display: "flex", flexDirection: "column", gap: 2, alignItems: "flex-start",
  padding: "7px 8px", borderRadius: "var(--r-sm)", border: "1px solid",
  cursor: "pointer", textAlign: "left", color: "var(--ink-primary)",
};
const emptyCell = {
  width: "100%", padding: "7px 8px", borderRadius: "var(--r-sm)",
  border: "1px dashed var(--line-hairline)", background: "transparent",
  color: "var(--ink-tertiary)", cursor: "pointer",
};
const legendWrap = {
  display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center",
  padding: "10px 12px", borderTop: "1px solid var(--line-hairline)",
};
const legendItem = { display: "inline-flex", alignItems: "center", gap: 5 };
const sel = {
  padding: "6px 8px", borderRadius: "var(--r-sm)",
  border: "1px solid var(--line-hairline)", background: "var(--bg-surface)",
  color: "var(--ink-primary)",
};
const ta = {
  width: "100%", padding: "6px 8px", borderRadius: "var(--r-sm)",
  border: "1px solid var(--line-hairline)", background: "var(--bg-surface)",
  color: "var(--ink-primary)", fontFamily: "inherit", fontSize: 13,
};
const h4 = { margin: "0 0 6px", fontSize: 12, textTransform: "uppercase", letterSpacing: ".04em",
             color: "var(--ink-tertiary)" };
const field = { display: "flex", flexDirection: "column", gap: 4, marginBottom: 10, fontSize: 13 };
