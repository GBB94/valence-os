import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api } from "../api";
import { useToast, AgeChip, DueChip, Loading } from "../ui";
import PersonCard from "./PersonCard";

// §3.1 the five horizontal bands, top (most senior) to bottom.
const LAYER_ORDER = ["executive", "economic", "operational", "technical_gating", "user_advocate"];
const LAYER_LABEL = { executive: "Executive", economic: "Economic", operational: "Operational", technical_gating: "Technical & gating", user_advocate: "User & advocate" };

// The signature element (Section 6b / DESIGN-GUIDE §8): node size = influence, fill + shape =
// stance (categorical → the data family, paired with a shape so it reads without color; stance
// is a position, not account health), edge thickness = type, arrowheads = direction; anchored on
// the reporting hierarchy, no force-directed hairball. Toggle to a power-interest grid.
const STANCE_VAR = { supporter: "--data-1", skeptic: "--data-3", unconverted: "--data-muted", null: "--data-muted" };
const STANCE_SHAPE = { supporter: "ellipse", skeptic: "diamond", unconverted: "round-rectangle", null: "round-rectangle" };
// §3 placeholder: a position known to exist but not yet identified — rendered in the unknown
// treatment (status-unknown fill + hexagon), sized by EXPECTED influence.
const PLACEHOLDER_VAR = "--status-unknown";
const PLACEHOLDER_SHAPE = "hexagon";

export default function StakeholderGraph({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [programId, setProgramId] = useState("");
  const [graph, setGraph] = useState(null);
  const [mode, setMode] = useState("network"); // 'network' | 'power_interest' | 'layers'
  const [selected, setSelected] = useState(null);
  const [cardPerson, setCardPerson] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const elRef = useRef(null);
  const cyRef = useRef(null);
  // Re-init the canvas graph when the light/dark theme changes (it reads colors from CSS vars).
  const [themeTick, setThemeTick] = useState(0);
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeTick((t) => t + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!accountId) return;
    api.account(accountId).then(setDetail).catch((e) => toast(e.message, "err"));
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    api.stakeholderGraph(accountId, programId || undefined).then(setGraph).catch((e) => toast(e.message, "err"));
  }, [accountId, programId, reloadKey]);

  useEffect(() => {
    if (!accountId) return;
    api.stakeholderCoverage(accountId).then(setCoverage).catch(() => setCoverage(null));
  }, [accountId, reloadKey]);

  useEffect(() => {
    if (mode !== "network" || !graph || !elRef.current) return;
    // Canvas can't use CSS var() — resolve the theme's colors from the computed root vars.
    // tokens.css loads before render, so the computed vars always resolve — no hex fallbacks.
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    const labelColor = v("--ink-primary");
    const nodeBorder = v("--bg-surface");
    const edgeColor = v("--line-strong");
    const edgeLabel = v("--ink-tertiary");
    const reportsColor = v("--line-strong");
    const relColor = v("--data-2");     // influence + sponsorship edges
    const stanceColor = (s) => v(STANCE_VAR[s] || "--data-muted");
    const cy = cytoscape({
      container: elRef.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: n.is_placeholder ? (n.title || n.name) : n.name, size: n.size,
          color: n.is_placeholder ? v(PLACEHOLDER_VAR) : stanceColor(n.stance),
          shape: n.is_placeholder ? PLACEHOLDER_SHAPE : (STANCE_SHAPE[n.stance] || "round-rectangle"),
          dashed: n.is_placeholder ? "dashed" : "solid", role: n.role } })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, type: e.type } })),
      ],
      style: [
        { selector: "node", style: {
          "background-color": "data(color)", shape: "data(shape)", width: "data(size)", height: "data(size)",
          label: "data(label)", "font-size": 12, "font-weight": 500, color: labelColor,
          "text-valign": "bottom", "text-margin-y": 4,
          "text-background-color": nodeBorder, "text-background-opacity": 0.9,
          "text-background-padding": 4, "text-background-shape": "roundrectangle",
          "border-width": 2, "border-color": nodeBorder } },
        // placeholders (§3): dashed border marks a position that isn't a confirmed person yet
        { selector: 'node[dashed="dashed"]', style: {
          "border-width": 2, "border-color": v("--status-unknown"), "border-style": "dashed" } },
        { selector: "edge", style: {
          "curve-style": "bezier", "target-arrow-shape": "triangle", width: 2,
          "line-color": edgeColor, "target-arrow-color": edgeColor, "font-size": 8,
          label: "data(type)", color: edgeLabel } },
        { selector: 'edge[type="reports_to"]', style: { "line-style": "solid", width: 3, "line-color": reportsColor, "target-arrow-color": reportsColor } },
        { selector: 'edge[type="influences"]', style: { "line-style": "dashed", "line-color": relColor, "target-arrow-color": relColor } },
        { selector: 'edge[type="sponsors"]', style: { "line-style": "dotted", "line-color": relColor, "target-arrow-color": relColor } },
      ],
      layout: graph.edges.length
        ? { name: "breadthfirst", directed: true, spacingFactor: 1.15, padding: 48 }
        : { name: "grid", avoidOverlap: true, padding: 72 },
    });
    cy.on("tap", "node", (evt) => {
      const n = graph.nodes.find((x) => x.id === evt.target.id());
      setSelected(n);
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [graph, mode, themeTick]);

  if (!accounts.length) return <div className="subtle">Create an account first.</div>;
  const programs = detail?.programs ?? [];

  return (
    <div className="stakeholder-workspace">
      <div className="actions stakeholder-toolbar">
        <div className="stakeholder-title"><div className="page-eyebrow">Relationship intelligence</div><h1>Stakeholder map</h1></div>
        <select value={accountId || ""} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); }} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={sel}>
          <option value="">all programs</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <div className="spacer" />
        <button className={"btn small" + (mode === "network" ? " selected" : "")} aria-pressed={mode === "network"} onClick={() => setMode("network")}>Network</button>
        <button className={"btn small" + (mode === "layers" ? " selected" : "")} aria-pressed={mode === "layers"} onClick={() => setMode("layers")}>Layers</button>
        <button className={"btn small" + (mode === "power_interest" ? " selected" : "")} aria-pressed={mode === "power_interest"} onClick={() => setMode("power_interest")}>Power–interest</button>
      </div>

      <div className="two-col">
        <div className="card stakeholder-canvas">
          {!graph ? <Loading what="stakeholder graph" /> :
            graph.nodes.length === 0 ? <div className="empty"><h3>No stakeholders</h3>Add people with roles and set their influence.</div> :
            mode === "network"
              ? <div ref={elRef} className="stakeholder-graph" />
              : mode === "layers"
                ? <LayerLanes nodes={graph.nodes} onSelect={setSelected} />
                : <PowerInterest nodes={graph.nodes} onSelect={setSelected} />}
          <div className="rowmeta stakeholder-legend">
            Size = influence · shape = stance (● supporter, ◆ skeptic, ▮ unconverted) · ⬡ dashed = unidentified position · solid = reports-to, dashed = influences, dotted = sponsors.
          </div>
        </div>
        <div>
        {coverage && (
          <div className="card stakeholder-coverage">
            <div className="page-eyebrow">Relationship coverage</div>
            <div className="coverage-primary">
              <strong>{coverage.vp_plus_active}/{coverage.vp_plus_total}</strong>
              <span>senior relationships active<small>touched within 21 days</small></span>
            </div>
            <div className={`coverage-callout ${coverage.multithreaded ? "is-healthy" : "is-warning"}`}>
              <span className={`state-mark ${coverage.multithreaded ? "ok" : "warn"}`} />
              <span>Business case is {coverage.multithreaded
                ? <span style={{ color: "var(--status-ok)" }}>multithreaded ({coverage.business_case_owner_count} owners)</span>
                : <span style={{ color: "var(--status-warn)" }}>single-threaded — add a second owner</span>}</span>
            </div>
            {coverage.placeholder_count > 0 && (
              <div style={{ fontSize: 13, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                <span className="unknown-hatch" style={{ width: 10, height: 10, display: "inline-block", flex: "none" }} />
                <strong>{coverage.placeholder_count}</strong>&nbsp;critical position{coverage.placeholder_count === 1 ? "" : "s"} unidentified
              </div>
            )}
            {coverage.cadence_compliance != null && (
              <div className="coverage-metric">
                <span>Cadence compliance</span><strong>{coverage.cadence_compliance}%</strong>
                <span className="rowmeta"> ({coverage.cadence_overdue_count} overdue)</span>
              </div>
            )}
            {coverage.layer_heat && (
              <div style={{ marginBottom: 8 }}>
                <div className="rowmeta" style={{ marginBottom: 4 }}>Layer heat (active · stale · placeholder)</div>
                {LAYER_ORDER.map((l) => {
                  const h = coverage.layer_heat[l] || {};
                  const a = h.active || 0, s = h.stale || 0, ph = h.placeholder || 0;
                  if (!a && !s && !ph) return null;
                  return (
                    <div key={l} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>{LAYER_LABEL[l]}</span>
                      <span>
                        <span style={{ color: "var(--status-ok)" }}>{a} active</span> ·{" "}
                        <span style={{ color: "var(--status-warn)" }}>{s} stale</span> ·{" "}
                        <span style={{ color: "var(--ink-secondary)" }}>{ph} placeholder</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            {coverage.detractors?.length > 0 && (
              <div style={{ marginBottom: 4 }}>
                <div className="rowmeta" style={{ marginBottom: 4 }}>Detractor watch</div>
                {coverage.detractors.map((d, i) => (
                  <div key={i} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>{d.name}{d.high_influence ? " (high influence)" : ""}</span>
                    {!d.has_plan && <span style={{ color: "var(--status-warn)" }}>no plan</span>}
                  </div>
                ))}
              </div>
            )}
            {coverage.senior_stakeholders.length > 0 && (
              <div className="rowmeta" style={{ marginBottom: 4, marginTop: 4 }}>Senior stakeholders · last touch</div>
            )}
            {coverage.senior_stakeholders.map((s, i) => (
              <div key={i} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{s.name} · {s.role.replace(/_/g, " ")}</span>
                {s.days_since_touch == null ? <span className="rowmeta">no touch</span> : <AgeChip days={s.days_since_touch} />}
              </div>
            ))}
          </div>
        )}
        <div className="card stakeholder-detail">
          {selected ? (
            selected.is_placeholder ? (
              <>
                <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="unknown-hatch" style={{ width: 12, height: 12, display: "inline-block", flex: "none" }} />
                  {selected.title || selected.name}
                </h3>
                <div className="rowmeta">Unidentified position</div>
                <div className="kv" style={{ marginTop: 10 }}>
                  <dt>Expected role</dt><dd>{(selected.role || "—").replace(/_/g, " ")}</dd>
                  <dt>Expected influence</dt><dd>{selected.expected_influence || "—"}</dd>
                  <dt>Find by</dt><dd>{selected.find_by_date ? <DueChip date={selected.find_by_date} /> : "—"}</dd>
                </div>
              </>
            ) : (
              <>
                <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
                <div className="rowmeta">{selected.title}</div>
                <div className="kv" style={{ marginTop: 10 }}>
                  <dt>Role</dt><dd>{(selected.effective_role || selected.role || "—").replace(/_/g, " ")}
                    {selected.effective_role && selected.effective_role !== selected.role
                      ? <span className="rowmeta"> (tagged {selected.role.replace(/_/g, " ")})</span> : null}</dd>
                  <dt>Layer</dt><dd>{LAYER_LABEL[selected.layer] || "—"}</dd>
                  <dt>Stance</dt><dd>{selected.stance || "—"}</dd>
                  <dt>Influence</dt><dd>{selected.influence || "—"}</dd>
                </div>
                <button className="btn small" style={{ marginTop: 12 }} onClick={() => setCardPerson(selected.id)}>Open full profile →</button>
              </>
            )
          ) : <div className="stakeholder-detail-empty"><span className="stakeholder-detail-mark" />
            <strong>Select a stakeholder</strong><span>Inspect role, stance, influence, and the full relationship record.</span></div>}
        </div>
        </div>
      </div>
      {cardPerson && <PersonCard personId={cardPerson} onClose={() => setCardPerson(null)} onChanged={() => setThemeTick((t) => t + 1)} />}
    </div>
  );
}

// §3.1 layer-lane view — horizontal bands by layer; placeholders in their expected band; an
// empty band is still drawn as a band so the gap is visible. Nodes carry a resolved `layer`.
function LayerLanes({ nodes, onSelect }) {
  const byLayer = Object.fromEntries(LAYER_ORDER.map((l) => [l, []]));
  nodes.forEach((n) => { (byLayer[n.layer] || byLayer.operational).push(n); });
  return (
    <div style={{ padding: 12 }}>
      {LAYER_ORDER.map((l) => (
        <div key={l} style={{ display: "flex", alignItems: "center", borderBottom: "1px solid var(--line-hairline)", minHeight: 76 }}>
          <div style={{ width: 120, flex: "none", fontSize: "var(--t-micro)", color: "var(--ink-tertiary)", textTransform: "uppercase", letterSpacing: ".04em" }}>{LAYER_LABEL[l]}</div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", padding: "12px 0" }}>
            {byLayer[l].length === 0
              ? <span className="rowmeta" style={{ fontStyle: "italic" }}>— empty band —</span>
              : byLayer[l].map((n) => (
                <div key={n.id} onClick={() => onSelect(n)} title={n.name} style={{ cursor: "pointer", textAlign: "center", width: 84 }}>
                  <div className={n.is_placeholder ? "unknown-hatch" : ""} style={{
                    width: Math.max(20, n.size * 0.7), height: Math.max(20, n.size * 0.7), margin: "0 auto",
                    borderRadius: n.is_placeholder ? 3 : "50%",
                    background: n.is_placeholder ? undefined : `var(${STANCE_VAR[n.stance] || "--data-muted"})`,
                    border: n.is_placeholder ? "1px dashed var(--status-unknown)" : "1px solid var(--bg-surface)" }} />
                  <div style={{ fontSize: "var(--t-micro)", color: "var(--ink-secondary)", marginTop: 2 }}>{(n.is_placeholder ? (n.title || n.name) : n.name).split(" ").slice(0, 2).join(" ")}</div>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// Power (influence) vs interest (stance) grid — classic 2x2 for prioritizing engagement.
function PowerInterest({ nodes, onSelect }) {
  return (
    <div style={{ position: "relative", height: 460, margin: 20 }}>
      <div style={{ position: "absolute", inset: 0, border: "1px solid var(--line-strong)" }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: "50%", width: 1, background: "var(--line-hairline)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: "var(--line-hairline)" }} />
      <Label t="Keep satisfied" x="2%" y="2%" /><Label t="Manage closely" x="70%" y="2%" />
      <Label t="Monitor" x="2%" y="94%" /><Label t="Keep informed" x="70%" y="94%" />
      <div style={{ position: "absolute", left: -4, top: "50%", transform: "rotate(-90deg)", transformOrigin: "left", fontSize: "var(--t-micro)", color: "var(--ink-tertiary)" }}>power (influence) →</div>
      <div style={{ position: "absolute", bottom: -16, left: "50%", fontSize: "var(--t-micro)", color: "var(--ink-tertiary)" }}>interest (stance) →</div>
      {nodes.map((n) => {
        const x = ((n.interest - 1) / 2) * 84 + 8;      // 1..3 -> 8..92%
        const y = 92 - ((n.power - 1) / 2) * 84;         // higher power = higher up
        return (
          <div key={n.id} onClick={() => onSelect(n)} title={n.name}
            style={{ position: "absolute", left: `${x}%`, top: `${y}%`, transform: "translate(-50%,-50%)", cursor: "pointer", textAlign: "center" }}>
            <div className={n.is_placeholder ? "unknown-hatch" : ""} style={{ width: n.size * 0.7, height: n.size * 0.7, borderRadius: n.is_placeholder ? 2 : "50%", background: n.is_placeholder ? undefined : `var(${STANCE_VAR[n.stance] || "--data-muted"})`, border: n.is_placeholder ? "1px dashed var(--status-unknown)" : "1px solid var(--bg-surface)" }} />
            <div style={{ fontSize: "var(--t-micro)", color: "var(--ink-secondary)" }}>{n.name.split(" ")[0]}</div>
          </div>
        );
      })}
    </div>
  );
}
const Label = ({ t, x, y }) => <div style={{ position: "absolute", left: x, top: y, fontSize: "var(--t-micro)", color: "var(--ink-tertiary)" }}>{t}</div>;
const sel = { height: 30, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" };
