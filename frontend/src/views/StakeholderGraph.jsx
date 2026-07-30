import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api } from "../api";
import { useToast } from "../ui";

// The signature element (Section 6b / DESIGN-GUIDE §8): node size = influence, fill = stance
// (from the status family), edge thickness = type, arrowheads = direction; anchored on the
// reporting hierarchy, no force-directed hairball. Toggle to a power-interest grid.
const STANCE_VAR = { supporter: "--status-ok", skeptic: "--status-risk", unconverted: "--status-unknown", null: "--status-unknown" };

export default function StakeholderGraph({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [programId, setProgramId] = useState("");
  const [graph, setGraph] = useState(null);
  const [mode, setMode] = useState("network"); // 'network' | 'power_interest'
  const [selected, setSelected] = useState(null);
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
    const css = getComputedStyle(document.documentElement);
    const v = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    const labelColor = v("--ink-primary", "#14161C");
    const nodeBorder = v("--bg-surface", "#fff");
    const edgeColor = v("--line-strong", "#CDD2DA");
    const edgeLabel = v("--ink-tertiary", "#868D9B");
    const reportsColor = v("--line-strong", "#CDD2DA");
    const relColor = v("--data-2", "#6A63D9");     // influence + sponsorship edges
    const stanceColor = (s) => v(STANCE_VAR[s] || "--status-unknown", "#868D9B");
    const cy = cytoscape({
      container: elRef.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: n.name, size: n.size, color: stanceColor(n.stance), role: n.role } })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, type: e.type } })),
      ],
      style: [
        { selector: "node", style: {
          "background-color": "data(color)", width: "data(size)", height: "data(size)",
          label: "data(label)", "font-size": 10, color: labelColor, "text-valign": "bottom",
          "text-margin-y": 3, "border-width": 1, "border-color": nodeBorder } },
        { selector: "edge", style: {
          "curve-style": "bezier", "target-arrow-shape": "triangle", width: 2,
          "line-color": edgeColor, "target-arrow-color": edgeColor, "font-size": 8,
          label: "data(type)", color: edgeLabel } },
        { selector: 'edge[type="reports_to"]', style: { "line-style": "solid", width: 3, "line-color": reportsColor, "target-arrow-color": reportsColor } },
        { selector: 'edge[type="influences"]', style: { "line-style": "dashed", "line-color": relColor, "target-arrow-color": relColor } },
        { selector: 'edge[type="sponsors"]', style: { "line-style": "dotted", "line-color": relColor, "target-arrow-color": relColor } },
      ],
      layout: { name: "breadthfirst", directed: true, spacingFactor: 1.3, padding: 20 },
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
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <h1>Stakeholder map</h1>
        <select value={accountId || ""} onChange={(e) => { setAccountId(e.target.value); setProgramId(""); }} style={sel}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={programId} onChange={(e) => setProgramId(e.target.value)} style={sel}>
          <option value="">all programs</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <div className="spacer" />
        <button className={"btn small" + (mode === "network" ? " primary" : "")} onClick={() => setMode("network")}>Network</button>
        <button className={"btn small" + (mode === "power_interest" ? " primary" : "")} onClick={() => setMode("power_interest")}>Power–interest</button>
      </div>

      <div className="two-col">
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          {!graph ? <div className="subtle" style={{ padding: 20 }}>Loading…</div> :
            graph.nodes.length === 0 ? <div className="empty"><h3>No stakeholders</h3>Add people with roles and set their influence.</div> :
            mode === "network"
              ? <div ref={elRef} style={{ height: 460 }} />
              : <PowerInterest nodes={graph.nodes} onSelect={setSelected} />}
          <div className="rowmeta" style={{ padding: "8px 12px", borderTop: "1px solid var(--border)" }}>
            Size = influence · color = stance (green supporter, red skeptic, grey unconverted) · solid = reports-to, blue dashed = influences, dotted = sponsors.
          </div>
        </div>
        <div>
        {coverage && (
          <div className="card" style={{ padding: 14, marginBottom: 10 }}>
            <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>Coverage</div>
            <div style={{ fontSize: 13, marginBottom: 4 }}>
              <strong>{coverage.vp_plus_active}/{coverage.vp_plus_total}</strong> senior relationships active
              <span className="rowmeta"> (touched ≤21d)</span>
            </div>
            <div style={{ fontSize: 13, marginBottom: 8 }}>
              Business case: {coverage.multithreaded
                ? <span style={{ color: "var(--ok)" }}>multithreaded ({coverage.business_case_owner_count} owners)</span>
                : <span style={{ color: "var(--warn)" }}>single-threaded — add a 2nd owner</span>}
            </div>
            {coverage.senior_stakeholders.map((s, i) => (
              <div key={i} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{s.name} · {s.role.replace(/_/g, " ")}</span>
                <span style={{ color: s.stale ? "var(--warn)" : "var(--text-3)" }}>
                  {s.days_since_touch == null ? "no touch" : `${s.days_since_touch}d`}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="card" style={{ padding: 14 }}>
          {selected ? (
            <>
              <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
              <div className="rowmeta">{selected.title}</div>
              <div className="kv" style={{ marginTop: 10 }}>
                <dt>Role</dt><dd>{selected.role}</dd>
                <dt>Stance</dt><dd>{selected.stance || "—"}</dd>
                <dt>Influence</dt><dd>{selected.influence || "—"}</dd>
                <dt>Relationship</dt><dd>{selected.relationship_strength || "—"}</dd>
              </div>
            </>
          ) : <div className="rowmeta">Click a node to inspect a stakeholder.</div>}
        </div>
        </div>
      </div>
    </div>
  );
}

// Power (influence) vs interest (stance) grid — classic 2x2 for prioritizing engagement.
function PowerInterest({ nodes, onSelect }) {
  return (
    <div style={{ position: "relative", height: 460, margin: 20 }}>
      <div style={{ position: "absolute", inset: 0, border: "1px solid var(--border-strong)" }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: "50%", width: 1, background: "var(--border)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: "var(--border)" }} />
      <Label t="Keep satisfied" x="2%" y="2%" /><Label t="Manage closely" x="70%" y="2%" />
      <Label t="Monitor" x="2%" y="94%" /><Label t="Keep informed" x="70%" y="94%" />
      <div style={{ position: "absolute", left: -4, top: "50%", transform: "rotate(-90deg)", transformOrigin: "left", fontSize: 10, color: "var(--text-3)" }}>power (influence) →</div>
      <div style={{ position: "absolute", bottom: -16, left: "50%", fontSize: 10, color: "var(--text-3)" }}>interest (stance) →</div>
      {nodes.map((n) => {
        const x = ((n.interest - 1) / 2) * 84 + 8;      // 1..3 -> 8..92%
        const y = 92 - ((n.power - 1) / 2) * 84;         // higher power = higher up
        return (
          <div key={n.id} onClick={() => onSelect(n)} title={n.name}
            style={{ position: "absolute", left: `${x}%`, top: `${y}%`, transform: "translate(-50%,-50%)", cursor: "pointer", textAlign: "center" }}>
            <div style={{ width: n.size * 0.7, height: n.size * 0.7, borderRadius: "50%", background: `var(${STANCE_VAR[n.stance] || "--status-unknown"})`, border: "1px solid var(--bg-surface)" }} />
            <div style={{ fontSize: 10, color: "var(--text-2)" }}>{n.name.split(" ")[0]}</div>
          </div>
        );
      })}
    </div>
  );
}
const Label = ({ t, x, y }) => <div style={{ position: "absolute", left: x, top: y, fontSize: 10, color: "var(--text-3)" }}>{t}</div>;
const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
