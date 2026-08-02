/* Adoption campaigns (ADOPTION-CAMPAIGN-SPEC.md, Stage 11.0).

   The screen exists to make one thing legible: what we are deliberately doing to change adoption
   in a cohort, and whether the behaviour moved. Two display rules carry most of the weight:

   * **Cautions render beside the number, never below the fold.** The backend returns structured
     `cautions` precisely so this component cannot show a delta while dropping the reason it might
     be an artifact. A signal-triggered pre/post delta without its regression-to-the-mean warning
     is the failure mode the whole §5 contract exists to prevent.
   * **The plan mirrors the Ledger.** Linked status is read from the linked record, so a task
     closing elsewhere changes this readout without anything writing to the campaign. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Empty, SlideOver, Unknown, useToast } from "../ui";

const STATUS = {
  draft:     { glyph: "○", hue: "--ink-secondary",   label: "Draft" },
  ready:     { glyph: "◐", hue: "--status-warn",     label: "Ready" },
  active:    { glyph: "●", hue: "--status-ok",       label: "Active" },
  paused:    { glyph: "‖", hue: "--status-warn",     label: "Paused" },
  completed: { glyph: "✓", hue: "--ink-secondary",   label: "Completed" },
  cancelled: { glyph: "✕", hue: "--status-risk",     label: "Cancelled" },
};

// Evaluation status -> how it reads. Never colour alone.
const EVAL = {
  met:              { glyph: "●", hue: "--status-ok",      label: "Meets the bar" },
  not_met:          { glyph: "◑", hue: "--status-warn",    label: "Below the bar" },
  unknown:          { glyph: "?", hue: "--status-unknown", label: "Unknown" },
  suppressed:       { glyph: "▨", hue: "--status-unknown", label: "Suppressed" },
  invalidated:      { glyph: "✕", hue: "--status-risk",    label: "Invalidated" },
  no_evidence:      { glyph: "○", hue: "--status-unknown", label: "No evidence" },
};
const EVAL_FALLBACK = { glyph: "?", hue: "--status-unknown", label: "Unknown" };

const BARRIER = {
  capability: "Capability", opportunity: "Opportunity",
  motivation: "Motivation", unknown: "Not yet diagnosed",
};

export default function Campaigns({ accountId, reloadKey }) {
  const toast = useToast();
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);

  async function load() {
    if (!accountId) return;
    try { setRows(await api.campaigns(accountId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [accountId, reloadKey, tick]);

  if (!accountId) return null;

  return (
    <div className="card">
      <div className="card-h">
        <h3>Adoption campaigns</h3>
        <div className="spacer" />
        <span className="rowmeta">
          {rows ? `${rows.filter((r) => r.status === "active").length} active` : ""}
        </span>
      </div>
      <div className="rowmeta" style={{ padding: "0 12px 8px" }}>
        A time-boxed intervention against one cohort. The app reports what the numbers did; it
        never claims the campaign caused it.
      </div>

      {!rows ? <div className="subtle" style={{ padding: 12 }}>Loading…</div> :
        rows.length === 0 ? (
          <Empty title="No campaigns yet">
            A campaign names the cohort, the behaviour to change, the barrier in the way, and the
            bar it is measured against.
          </Empty>
        ) : (
          <table>
            <thead><tr>
              <th scope="col">Campaign</th>
              <th scope="col" style={{ width: 150 }}>Cohort</th>
              <th scope="col" style={{ width: 130 }}>Status</th>
              <th scope="col" style={{ width: 120 }}>Window</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => {
                const st = STATUS[r.status] || STATUS.draft;
                return (
                  <tr key={r.id}>
                    <th scope="row" style={{ textAlign: "left", fontWeight: 500 }}>
                      <button className="btn ghost" style={{ padding: 0, textAlign: "left" }}
                              onClick={() => setOpen(r.id)}>{r.name}</button>
                      <div className="rowmeta">{r.target_behavior}</div>
                    </th>
                    <td className="rowmeta">
                      {r.population}
                      <div>{r.use_case}</div>
                    </td>
                    <td>
                      <span aria-hidden="true" style={{ color: `var(${st.hue})`, marginRight: 5 }}>
                        {st.glyph}
                      </span>
                      {st.label}
                    </td>
                    <td className="rowmeta">
                      {r.planned_start_on} → {r.planned_end_on}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

      {open && <CampaignPanel campaignId={open} onClose={() => setOpen(null)}
                              onChanged={() => setTick((t) => t + 1)} />}
    </div>
  );
}

function CampaignPanel({ campaignId, onClose, onChanged }) {
  const toast = useToast();
  const [c, setC] = useState(null);

  async function load() {
    try { setC(await api.campaign(campaignId)); } catch (e) { toast(e.message, "err"); }
  }
  useEffect(() => { load(); }, [campaignId]);

  if (!c) return <SlideOver title="Campaign" onClose={onClose}>
    <div className="subtle">Loading…</div></SlideOver>;

  const st = STATUS[c.status] || STATUS.draft;

  return (
    <SlideOver title={c.name} onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span aria-hidden="true" style={{ color: `var(${st.hue})`, fontSize: 15 }}>{st.glyph}</span>
        <strong>{st.label}</strong>
        <span className="rowmeta">· {c.population} · {c.use_case}</span>
      </div>
      <div className="rowmeta" style={{ marginBottom: 14 }}>
        {c.planned_start_on} → {c.planned_end_on}
        {c.evaluation_on ? ` · evaluated ${c.evaluation_on}` : ""}
        {c.internal_owner_name ? ` · ${c.internal_owner_name}` : ""}
      </div>

      <h4 style={h4}>The behaviour and the bet</h4>
      <p style={p}>{c.target_behavior}</p>
      <p style={{ ...p, color: "var(--ink-secondary)" }}>{c.hypothesis}</p>

      {c.readiness && !c.readiness.ready && c.status === "draft" && (
        <div style={gapBar}>
          <span aria-hidden="true" style={{ color: "var(--status-warn)" }}>▲</span>{" "}
          <span className="rowmeta">Not ready: {c.readiness.blocking.join("; ")}</span>
        </div>
      )}

      <h4 style={h4}>Measurement</h4>
      {c.targets.length === 0 ? <div className="rowmeta">No target yet.</div> :
        c.targets.map((t) => {
          const ev = t.evaluation;
          const e = EVAL[ev.status] || EVAL_FALLBACK;
          return (
            <div key={t.id} style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                <span aria-hidden="true" style={{ color: `var(${e.hue})` }}>{e.glyph}</span>
                <strong>{t.metric}</strong>
                <span className="rowmeta">
                  {t.role} · {t.direction === "at_most" ? "≤" : "≥"} {t.target_value}
                </span>
              </div>
              <div style={{ fontVariantNumeric: "tabular-nums", margin: "4px 0" }}>
                {ev.value == null ? <Unknown since={ev.current_through} /> : (
                  <>
                    {ev.value}
                    {ev.baseline_value != null && (
                      <span className="rowmeta">
                        {"  from "}{ev.baseline_value}
                        {ev.delta != null && ` (${ev.delta > 0 ? "+" : ""}${ev.delta})`}
                      </span>
                    )}
                    {ev.current_through && <AgeChip date={ev.current_through} />}
                  </>
                )}
              </div>

              {/* §5.1 — the series the baseline sits in. Without it, a delta cannot show whether
                  the cohort was already moving. */}
              {t.baseline_trajectory?.length > 0 && (
                <div className="rowmeta">
                  Before the campaign:{" "}
                  {t.baseline_trajectory.map((pt) => pt.value).join(" → ")}
                  {ev.baseline_value != null && ` → ${ev.baseline_value} (baseline)`}
                </div>
              )}

              {ev.comparator && (
                <div className="rowmeta" style={{ marginTop: 3 }}>
                  {ev.comparator.delta != null
                    ? <>Comparator cohort moved {ev.comparator.delta > 0 ? "+" : ""}
                        {ev.comparator.delta} over the same window ({ev.comparator.from_value} →
                        {" "}{ev.comparator.to_value}).</>
                    : <>Comparator: {ev.comparator.reason}</>}
                </div>
              )}

              {/* Cautions sit WITH the number, by design. */}
              {ev.cautions?.map((w) => (
                <div key={w.kind} style={caution}>
                  <span aria-hidden="true" style={{ color: "var(--status-warn)" }}>▲</span>{" "}
                  {w.detail}
                </div>
              ))}
              {ev.interpretation_note && (
                <div className="rowmeta" style={{ marginTop: 3, fontStyle: "italic" }}>
                  {ev.interpretation_note}
                </div>
              )}
            </div>
          );
        })}

      <h4 style={h4}>Barriers</h4>
      {c.barriers.length === 0 ? <div className="rowmeta">None diagnosed.</div> : (
        <table style={{ marginBottom: 14 }}>
          <tbody>
            {c.barriers.map((b) => (
              <tr key={b.id}>
                <th scope="row" style={{ textAlign: "left", fontWeight: b.is_primary ? 600 : 400 }}>
                  {BARRIER[b.category]}
                  {b.is_primary ? <span className="rowmeta"> · primary</span> : null}
                  <div className="rowmeta">{b.description}</div>
                </th>
                <td className="rowmeta" style={{ width: 110 }}>
                  {b.confidence}
                  <div>{b.observed_on}</div>
                </td>
                <td className="rowmeta" style={{ width: 90 }}>{b.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 style={h4}>The intervention</h4>
      {c.plan.length === 0 ? <div className="rowmeta">No linked interventions yet.</div> : (
        <table style={{ marginBottom: 14 }}>
          <thead><tr>
            <th scope="col">Step</th>
            <th scope="col" style={{ width: 110 }}>Kind</th>
            <th scope="col" style={{ width: 90 }}>State</th>
          </tr></thead>
          <tbody>
            {c.plan.map((l) => (
              <tr key={l.id}>
                <th scope="row" style={{ textAlign: "left", fontWeight: 400 }}>
                  {l.linked_label || <span className="rowmeta">missing record</span>}
                  {l.cue && <div className="rowmeta">cue: {l.cue}</div>}
                  {l.purpose && <div className="rowmeta">{l.purpose}</div>}
                </th>
                <td className="rowmeta">
                  {l.intervention_kind.replace(/_/g, " ")}
                  {l.is_reinforcement ? <div>reinforcement</div> : null}
                </td>
                {/* Derived from the linked record, so this can never disagree with the Ledger. */}
                <td className="rowmeta">{l.linked_status || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 style={h4}>Checkpoints</h4>
      {c.checkpoints.length === 0 ? <div className="rowmeta">None scheduled.</div> : (
        <table style={{ marginBottom: 14 }}>
          <tbody>
            {c.checkpoints.map((cp) => (
              <tr key={cp.id}>
                <th scope="row" style={{ textAlign: "left", fontWeight: 400 }}>
                  {cp.held_on ? `Held ${cp.held_on}` : `Scheduled ${cp.scheduled_on}`}
                  {cp.reason && <div className="rowmeta">{cp.reason}</div>}
                </th>
                <td className="rowmeta" style={{ width: 110 }}>
                  {cp.assessment || "—"}
                  {cp.decision ? <div>{cp.decision}</div> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {c.completion_outcome && (
        <>
          <h4 style={h4}>Outcome</h4>
          <p style={p}>
            <strong>{c.completion_outcome.replace(/_/g, " ")}</strong>
            <span className="rowmeta"> · reviewed {c.completion_reviewed_on}</span>
          </p>
          {c.completion_note && <p style={{ ...p, color: "var(--ink-secondary)" }}>{c.completion_note}</p>}
        </>
      )}

      <h4 style={{ ...h4, marginTop: 18 }}>History</h4>
      <table>
        <tbody>
          {c.history.map((h) => (
            <tr key={h.id}>
              <th scope="row" style={{ textAlign: "left", fontWeight: 400 }} className="rowmeta">
                {h.from_status ? `${h.from_status} → ${h.to_status}` : h.to_status}
              </th>
              <td>{h.reason}</td>
              <td className="rowmeta" style={{ width: 92 }}>{h.changed_on}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </SlideOver>
  );
}

const h4 = { margin: "16px 0 6px", fontSize: 12, textTransform: "uppercase",
             letterSpacing: ".04em", color: "var(--ink-tertiary)" };
const p = { margin: "0 0 6px", fontSize: 13, lineHeight: 1.5 };
const gapBar = { padding: "8px 10px", marginBottom: 8,
                 borderLeft: "3px solid var(--status-warn)", background: "var(--bg-sunken)" };
const caution = { marginTop: 4, fontSize: 12, lineHeight: 1.45,
                  color: "var(--ink-secondary)" };
