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
  const [openCell, setOpenCell] = useState(null);
  const [tick, setTick] = useState(0);
  const gridRef = useRef(null);

  async function load() {
    if (!accountId) return;
    try {
      const [m, n] = await Promise.all([api.whitespace(accountId), api.nextSeats(accountId)]);
      setMap(m); setNext(n);
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
    return (
      <div className="card">
        <div className="card-h"><h3>Whitespace map</h3></div>
        <Empty title="No base partition yet">
          The map needs a base population partition first — a set of mutually exclusive segments
          covering the account's total FTE. It is the only additive dimension, so nothing can be
          counted until it exists.
        </Empty>
      </div>
    );
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
        <CellPanel cellId={openCell} onClose={() => setOpenCell(null)}
                   onChanged={() => { setTick((t) => t + 1); }} />
      )}
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

/* The cell card. Shows ALL FOUR stored facts even though the heatmap shows one derived state,
   so nothing is hidden by the display precedence. Facts change only with a reason (§1.3). */
function CellPanel({ cellId, onClose, onChanged }) {
  const toast = useToast();
  const [cell, setCell] = useState(null);
  const [fact, setFact] = useState("penetration");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [lane, setLane] = useState("works_council");

  async function load() {
    try { setCell(await api.cell(cellId)); } catch (e) { toast(e.message, "err"); }
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
    </SlideOver>
  );
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
  padding: "7px 8px", borderRadius: "var(--radius-sm, 4px)", border: "1px solid",
  cursor: "pointer", textAlign: "left", color: "var(--ink-primary)",
};
const emptyCell = {
  width: "100%", padding: "7px 8px", borderRadius: "var(--radius-sm, 4px)",
  border: "1px dashed var(--line-hairline)", background: "transparent",
  color: "var(--ink-tertiary)", cursor: "pointer",
};
const legendWrap = {
  display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center",
  padding: "10px 12px", borderTop: "1px solid var(--line-hairline)",
};
const legendItem = { display: "inline-flex", alignItems: "center", gap: 5 };
const sel = {
  padding: "6px 8px", borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--line-hairline)", background: "var(--surface-1, transparent)",
  color: "var(--ink-primary)",
};
const ta = {
  width: "100%", padding: "6px 8px", borderRadius: "var(--radius-sm, 4px)",
  border: "1px solid var(--line-hairline)", background: "var(--surface-1, transparent)",
  color: "var(--ink-primary)", fontFamily: "inherit", fontSize: 13,
};
const h4 = { margin: "0 0 6px", fontSize: 12, textTransform: "uppercase", letterSpacing: ".04em",
             color: "var(--ink-tertiary)" };
