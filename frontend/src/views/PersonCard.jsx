import { useEffect, useState } from "react";
import { api } from "../api";
import { SlideOver, useToast, AgeChip, fmtDate } from "../ui";

const CAD_LABEL = { manage_closely: "Manage closely", keep_satisfied: "Keep satisfied", keep_informed: "Keep informed", monitor: "Monitor" };

// §3.10 person profile card — the unit the pre-call brief assembles from. Professional
// observations only (trust boundary D-76): no sensitive personal data anywhere here.
export default function PersonCard({ personId, onClose, onChanged }) {
  const toast = useToast();
  const [card, setCard] = useState(null);
  const [tax, setTax] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { api.peopleTaxonomy().then(setTax).catch(() => {}); }, []);
  useEffect(() => {
    if (!personId) return;
    api.personCard(personId).then(setCard).catch((e) => toast(e.message, "err"));
  }, [personId, tick]);

  if (!card) return <SlideOver title="Person" onClose={onClose}><div className="subtle">Loading…</div></SlideOver>;

  const reload = () => { setTick((t) => t + 1); onChanged?.(); };
  const patchRole = async (roleId, body) => {
    try { await api.patchStakeholderRole(roleId, body); toast("Saved"); reload(); }
    catch (e) { toast(e.message, "err"); }
  };
  const savePerson = async (body) => {
    try { await api.patchPerson(personId, body); toast("Saved"); reload(); }
    catch (e) { toast(e.message, "err"); }
  };
  const addAdvocacy = async () => {
    try {
      await api.createAdvocacyEvent({ person_id: personId, kind: "advocacy_without_us",
        occurred_on: new Date().toISOString().slice(0, 10), note: "Advocated for us without us in the room" });
      toast("Advocacy logged"); reload();
    } catch (e) { toast(e.message, "err"); }
  };

  const layerLabel = (l) => tax?.layer_labels?.[l] || l;

  return (
    <SlideOver title={card.name || "Person"} onClose={onClose}>
      <div className="stack">
        <div>
          <div className="rowmeta">{card.title || "—"}{card.email ? ` · ${card.email}` : ""}</div>
          <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
            {card.layers.map((l) => <span key={l} className="badge">{layerLabel(l)}</span>)}
          </div>
        </div>

        {/* Roles by program (editable role + layer) */}
        <Section title="Roles by program">
          {card.roles.length === 0 ? <div className="rowmeta">No roles yet.</div> : card.roles.map((r) => (
            <div key={r.role_id} className="card" style={{ padding: 10, marginBottom: 6 }}>
              <div className="rowmeta" style={{ marginBottom: 4 }}>{r.program_name}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <select value={r.role} onChange={(e) => patchRole(r.role_id, { role: e.target.value })} style={sel}>
                  {tax?.roles?.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                </select>
                <select value={r.layer} onChange={(e) => patchRole(r.role_id, { layer: e.target.value })} style={sel}>
                  {tax?.layers?.map((o) => <option key={o} value={o}>{layerLabel(o)}</option>)}
                </select>
                {r.stance && <span className="badge">{r.stance}</span>}
              </div>
              {r.effective_role !== r.role && (
                <div className="rowmeta" style={{ marginTop: 6, color: "var(--status-warn)" }}>
                  Reads as <strong>{r.effective_role}</strong> — {r.coach_reason}
                </div>
              )}
              {r.cares_about && <div className="rowmeta" style={{ marginTop: 6 }}>Cares about: {r.cares_about}</div>}
            </div>
          ))}
        </Section>

        {/* §3.6 cadence + §3.7 health */}
        {card.cadence && (
          <Section title="Cadence & health">
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
              <span>{CAD_LABEL[card.cadence.quadrant] || card.cadence.quadrant} · every {card.cadence.target_days}d</span>
              {card.cadence.overdue
                ? <span style={{ color: "var(--status-warn)" }}>● overdue{card.cadence.overdue_by != null ? ` by ${card.cadence.overdue_by}d` : ""}</span>
                : <span style={{ color: "var(--status-ok)" }}>● in cadence</span>}
            </div>
            <div className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Last meaningful touch</span>
              <span>{card.cadence.last_touch ? <AgeChip date={card.cadence.last_touch} /> : "none logged"}</span>
            </div>
            {card.health && (
              <>
                <div className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Frequency (90d)</span><span>{card.health.frequency.count_90d} touches</span>
                </div>
                <div className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Reciprocity · attendance</span>
                  <span title={card.health.reciprocity.reason} style={{ fontStyle: "italic" }}>awaiting comms/calendar</span>
                </div>
              </>
            )}
          </Section>
        )}

        {/* Professional-observation fields */}
        <Section title="Working profile">
          <EditRow label="Metric judged on" value={card.metric_judged_on}
            onSave={(v) => savePerson({ metric_judged_on: v })} />
          <EditRow label="Comms preference" value={card.comms_preference}
            onSave={(v) => savePerson({ comms_preference: v })} />
        </Section>

        {card.stance_trajectory.length > 0 && (
          <Section title="Stance trajectory">
            {card.stance_trajectory.map((s, i) => (
              <div key={i} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{s.stance}{s.evidence ? ` — ${s.evidence}` : ""}</span>
                <span>{fmtDate(s.date)}</span>
              </div>
            ))}
          </Section>
        )}

        <Section title={`Advocacy log (${card.advocacy.length})`}>
          {card.advocacy.map((e) => (
            <div key={e.id} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{e.kind.replace(/_/g, " ")}{e.note ? ` — ${e.note}` : ""}</span>
              <span>{fmtDate(e.occurred_on)}</span>
            </div>
          ))}
          <button className="btn small" style={{ marginTop: 6 }} onClick={addAdvocacy}>+ Log advocacy without us</button>
        </Section>

        {card.open_commitments.length > 0 && (
          <Section title="Open commitments">
            {card.open_commitments.map((c) => (
              <div key={c.id} className="rowmeta" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{c.direction === "theirs" ? "→ " : "← "}{c.description}</span>
                <span>{fmtDate(c.due_date)}</span>
              </div>
            ))}
          </Section>
        )}

        <Section title={`Interaction history (${card.interaction_history.length})`}>
          {card.interaction_history.length === 0 ? <div className="rowmeta">No touches logged.</div> :
            card.interaction_history.map((h) => (
              <div key={h.id} className="rowmeta" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span>{h.type} · {h.summary || "—"}</span>
                <span><AgeChip date={h.occurred_on} /></span>
              </div>
            ))}
        </Section>
      </div>
    </SlideOver>
  );
}

const Section = ({ title, children }) => (
  <div>
    <div className="rowmeta" style={{ textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 6 }}>{title}</div>
    {children}
  </div>
);

function EditRow({ label, value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(value || "");
  useEffect(() => setV(value || ""), [value]);
  return (
    <div style={{ marginBottom: 6 }}>
      <div className="rowmeta">{label}</div>
      {editing ? (
        <div style={{ display: "flex", gap: 6 }}>
          <input value={v} onChange={(e) => setV(e.target.value)} autoFocus style={{ flex: 1, height: 28, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)" }} />
          <button className="btn small primary" onClick={() => { onSave(v); setEditing(false); }}>Save</button>
          <button className="btn small" onClick={() => setEditing(false)}>Cancel</button>
        </div>
      ) : (
        <div style={{ fontSize: 13 }}>{value || <span className="rowmeta">—</span>}
          <button className="btn small" style={{ marginLeft: 8 }} onClick={() => setEditing(true)}>Edit</button>
        </div>
      )}
    </div>
  );
}

const sel = { height: 28, borderRadius: 6, border: "1px solid var(--line-strong)", padding: "0 8px", background: "var(--bg-surface)", fontSize: 12 };
