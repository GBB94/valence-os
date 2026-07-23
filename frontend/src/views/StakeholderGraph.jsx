import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api } from "../api";
import { useToast } from "../ui";

// The signature element (Section 6b): node size = influence, color = stance,
// edge thickness = type, arrowheads = direction; anchored on reporting hierarchy,
// no force-directed hairball. Toggle to a power-interest grid.
const STANCE_COLOR = { supporter: "#2b8a3e", skeptic: "#c92a2a", unconverted: "#8a909c", null: "#8a909c" };

export default function StakeholderGraph({ accounts, accountId, setAccountId, reloadKey }) {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [programId, setProgramId] = useState("");
  const [graph, setGraph] = useState(null);
  const [mode, setMode] = useState("network"); // 'network' | 'power_interest'
  const [selected, setSelected] = useState(null);
  const elRef = useRef(null);
  const cyRef = useRef(null);

  useEffect(() => {
    if (!accountId) return;
    api.account(accountId).then(setDetail).catch((e) => toast(e.message, "err"));
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    api.stakeholderGraph(accountId, programId || undefined).then(setGraph).catch((e) => toast(e.message, "err"));
  }, [accountId, programId, reloadKey]);

  useEffect(() => {
    if (mode !== "network" || !graph || !elRef.current) return;
    const cy = cytoscape({
      container: elRef.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: n.name, size: n.size, color: STANCE_COLOR[n.stance], role: n.role } })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, type: e.type } })),
      ],
      style: [
        { selector: "node", style: {
          "background-color": "data(color)", width: "data(size)", height: "data(size)",
          label: "data(label)", "font-size": 10, color: "#1a1d23", "text-valign": "bottom",
          "text-margin-y": 3, "border-width": 1, "border-color": "#fff" } },
        { selector: "edge", style: {
          "curve-style": "bezier", "target-arrow-shape": "triangle", width: 2,
          "line-color": "#ccd1d9", "target-arrow-color": "#ccd1d9", "font-size": 8,
          label: "data(type)", color: "#8a909c" } },
        { selector: 'edge[type="reports_to"]', style: { "line-style": "solid", width: 3, "line-color": "#5b616e", "target-arrow-color": "#5b616e" } },
        { selector: 'edge[type="influences"]', style: { "line-style": "dashed", "line-color": "#3b5bdb", "target-arrow-color": "#3b5bdb" } },
        { selector: 'edge[type="sponsors"]', style: { "line-style": "dotted" } },
      ],
      layout: { name: "breadthfirst", directed: true, spacingFactor: 1.3, padding: 20 },
    });
    cy.on("tap", "node", (evt) => {
      const n = graph.nodes.find((x) => x.id === evt.target.id());
      setSelected(n);
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [graph, mode]);

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
            <div style={{ width: n.size * 0.7, height: n.size * 0.7, borderRadius: "50%", background: STANCE_COLOR[n.stance], border: "1px solid #fff" }} />
            <div style={{ fontSize: 10, color: "var(--text-2)" }}>{n.name.split(" ")[0]}</div>
          </div>
        );
      })}
    </div>
  );
}
const Label = ({ t, x, y }) => <div style={{ position: "absolute", left: x, top: y, fontSize: 10, color: "var(--text-3)" }}>{t}</div>;
const sel = { height: 30, borderRadius: 6, border: "1px solid var(--border-strong)", padding: "0 8px", background: "var(--surface)" };
