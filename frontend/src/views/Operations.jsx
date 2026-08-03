import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useToast, fmtDate } from "../ui";

// Operations screen (Module P): say when the tool is broken without reading server logs.
export default function Operations({ reloadKey }) {
  const toast = useToast();
  const [ops, setOps] = useState(null);
  const [learning, setLearning] = useState(null);
  const [styles, setStyles] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [feedback, setFeedback] = useState([]);
  const [feedbackReview, setFeedbackReview] = useState({});
  const [styleName, setStyleName] = useState("Operator concise internal");
  const [maxChars, setMaxChars] = useState(6000);
  const loadStyles = useCallback(() => api.copilotStyles().then((result) => setStyles(result.profiles || [])).catch(() => {}), []);
  const loadCopilotOps = useCallback(() => Promise.all([
    api.copilotConfigurations().then((result) => setConfigs(result.configurations || [])),
    api.copilotFeedbackQueue(true).then((result) => setFeedback(result.feedback || [])),
  ]).catch(() => {}), []);
  useEffect(() => {
    api.operations().then(setOps).catch((e) => toast(e.message, "err"));
    api.campaignLearning().then(setLearning).catch((e) => toast(e.message, "err"));
    loadStyles();
    loadCopilotOps();
  }, [reloadKey, loadStyles, loadCopilotOps, toast]);
  if (!ops) return <div className="subtle">Loading…</div>;

  return (
    <div>
      <h1>Operations</h1>
      <div className="rowmeta" style={{ marginBottom: 14 }}>As of {ops.as_of}. Mock/local mode.</div>

      <div className="two-col" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div className="card" style={{ padding: 12 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase" }}>Job worker</div>
          <div>{ops.job_worker}</div>
          <div className="rowmeta" style={{ marginTop: 10, textTransform: "uppercase" }}>Audit events</div>
          <div style={{ fontSize: 20, fontWeight: 600 }}>{ops.audit_events.toLocaleString()}</div>
        </div>
        <div className="card" style={{ padding: 12 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase" }}>Backup</div>
          <div>RPO {ops.backup.rpo_hours}h · last restore test: {ops.backup.last_restore_test || "not run"}</div>
          <div className="rowmeta" style={{ marginTop: 6 }}>{ops.backup.note}</div>
        </div>
      </div>

      <h2>Company intelligence</h2>
      <div className="card" aria-label="Company intelligence operations">
        <div className="grid2" style={{ padding: 12 }}>
          <div><div className="rowmeta">Event review states</div><div className="chiprow">
            {Object.entries(ops.company_intelligence?.event_states || {}).map(([key, value]) => <span className="badge" key={key}>{key} · {value}</span>)}
          </div><div className="rowmeta" style={{ marginTop: 6 }}>Oldest proposal: {ops.company_intelligence?.proposed_oldest_age_days == null ? "none" : `${ops.company_intelligence.proposed_oldest_age_days}d`} · confirmation rate: {ops.company_intelligence?.confirmation_rate == null ? "insufficient data" : `${Math.round(ops.company_intelligence.confirmation_rate * 100)}%`} ({ops.company_intelligence?.reviewed_events} reviewed)</div></div>
          <div><div className="rowmeta">Ingestion outcomes</div><div className="chiprow">
            {Object.entries(ops.company_intelligence?.sync_totals || {}).map(([key, value]) => <span className="badge" key={key}>{key} · {value}</span>)}
          </div><div className="rowmeta" style={{ marginTop: 6 }}>Active convergence: {ops.company_intelligence?.active_convergences || 0}</div></div>
        </div>
        {!!ops.company_intelligence?.source_freshness?.length && <table><thead><tr><th>Source class</th><th>Latest retrieval</th><th>Documents</th><th>Retracted</th></tr></thead>
          <tbody>{ops.company_intelligence.source_freshness.map((row) => <tr key={row.source_class}><td>{row.source_class.replaceAll("_", " ")}</td><td>{fmtDate(row.latest_retrieval)}</td><td>{row.documents}</td><td>{row.retracted}</td></tr>)}</tbody></table>}
      </div>

      <h2>Campaign learning</h2>
      <div className="card" aria-label="Portfolio campaign learning">
        {!learning ? <div className="rowmeta" style={{ padding: 12 }}>Loading campaign learning…</div> : <>
          <div className="grid2" style={{ padding: 12 }}>
            <div><div className="rowmeta">Campaigns by state</div>
              <div className="chiprow">{Object.entries(learning.by_state || {}).map(([key, value]) =>
                <span className="badge" key={key}>{key.replaceAll("_", " ")} · {value}</span>)}</div></div>
            <div><div className="rowmeta">Completed outcomes</div>
              <div className="chiprow">{Object.entries(learning.outcomes || {}).map(([key, value]) =>
                <span className="badge" key={key}>{key.replaceAll("_", " ")} · {value}</span>)}</div></div>
          </div>
          <div style={{ padding: "0 12px 12px" }}>
            <strong>Time to first evidence:</strong> {learning.time_to_first_evidence?.insufficient_data
              ? " insufficient data" : ` median ${learning.time_to_first_evidence?.median_days} days`}
            <span className="rowmeta"> · n={learning.time_to_first_evidence?.n || 0}; count and denominator, never a percentage</span>
          </div>
          {!!learning.by_intervention_kind?.length && <table><thead><tr><th>Intervention</th><th>Observed</th><th>Appeared to help</th><th>Failed / did not help</th></tr></thead>
            <tbody>{learning.by_intervention_kind.map((row) => <tr key={row.intervention_kind}>
              <td>{row.intervention_kind.replaceAll("_", " ")}</td><td>{row.interventions_observed}</td>
              <td>{row.helped}</td><td>{row.failed}</td></tr>)}</tbody></table>}
          <div className="rowmeta" style={{ padding: 12 }}>
            Started without baseline: {learning.started_without_baseline?.length || 0} · without sponsor: {learning.started_without_sponsor?.length || 0} · evidence quiet: {learning.evidence_quiet_past_checkpoint?.length || 0} · repeated shapes: {learning.repeated_shapes?.length || 0}. No account or person ranking; no health score.
          </div>
        </>}
      </div>

      <h2>Account Copilot</h2>
      <div className="card" aria-label="Account Copilot operations">
        <div className="grid2" style={{ padding: 12 }}>
          <div><div className="rowmeta">Configuration</div>
            <div>{ops.copilot?.configuration?.mode || "unknown"} · network {ops.copilot?.configuration?.network ? "enabled" : "disabled"}</div>
            {ops.copilot?.configuration_error && <div style={{ color: "var(--status-risk)" }}>{ops.copilot.configuration_error}</div>}
          </div>
          <div><div className="rowmeta">Runs by state</div>
            <div className="chiprow">{Object.entries(ops.copilot?.counts || {}).map(([key, value]) =>
              <span className="badge" key={key}>{key} · {value}</span>)}</div>
          </div>
        </div>
        <details style={{ padding: "0 12px 12px" }}><summary>Release thresholds</summary>
          <div className="rowmeta" style={{ marginTop: 6 }}>{Object.entries(ops.copilot?.thresholds || {})
            .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`).join(" · ")}</div></details>
        {!!configs.length && <table><thead><tr><th>Version set</th><th>State</th><th>Evaluated</th><th>Release control</th></tr></thead>
          <tbody>{configs.map((config) => <tr key={config.id}>
            <td><div>{config.label}</div><div className="rowmeta">{config.model_version} · {config.prompt_version} · {config.retrieval_version} · {config.validator_version}</div></td>
            <td><span className="badge">{config.status}</span></td><td>{config.evaluated_at?.slice(0, 10) || "not evaluated"}</td>
            <td>{config.status === "passed" ? <button className="btn small" onClick={async () => {
              try { await api.activateCopilotConfiguration(config.id); await loadCopilotOps(); toast("Evaluated configuration activated."); }
              catch (error) { toast(error.message, "err"); }
            }}>Activate</button> : config.status === "active" && config.previous_config_id ? <button className="btn small ghost" onClick={async () => {
              try { await api.rollbackCopilotConfiguration(config.id); await loadCopilotOps(); toast("Previous evaluated configuration restored."); }
              catch (error) { toast(error.message, "err"); }
            }}>Rollback</button> : <span className="rowmeta">—</span>}</td>
          </tr>)}</tbody></table>}
      </div>

      <h2>Copilot correction queue</h2>
      <div className="card" aria-label="Copilot correction queue">
        {!feedback.length ? <div className="rowmeta" style={{ padding: 12 }}>No unreviewed feedback.</div> : feedback.map((item) => {
          const review = feedbackReview[item.id] || { disposition: "canonical_record_updated", resolution_note: "" };
          return <form key={item.id} style={{ padding: 12, borderBottom: "1px solid var(--line-hairline)" }} onSubmit={async (event) => {
            event.preventDefault();
            try {
              await api.reviewCopilotFeedback(item.id, { ...review, reviewed_by: "operator" });
              await loadCopilotOps(); toast("Feedback reviewed and retained in the correction ledger.");
            } catch (error) { toast(error.message, "err"); }
          }}>
            <div><strong>{item.issue_kind.replaceAll("_", " ")}</strong> · {item.query_text}</div>
            {item.claim_text && <div className="rowmeta">Claim: {item.claim_text}</div>}
            {item.source_record_id && <div className="rowmeta">Source: {item.source_packet_id} · {item.source_record_type?.replaceAll("_", " ")} · {item.source_record_id}</div>}
            <div className="actions" style={{ marginTop: 8, flexWrap: "wrap" }}>
              <select aria-label={`Disposition for ${item.id}`} value={review.disposition} onChange={(event) =>
                setFeedbackReview((current) => ({ ...current, [item.id]: { ...review, disposition: event.target.value } }))}>
                <option value="canonical_record_updated">Canonical record updated</option>
                <option value="evaluation_backlog">Add to evaluation backlog</option>
                <option value="confirmed">Confirmed</option><option value="dismissed">Dismissed</option>
              </select>
              <input required aria-label={`Resolution note for ${item.id}`} placeholder="Resolution or native record changed"
                value={review.resolution_note} onChange={(event) => setFeedbackReview((current) =>
                  ({ ...current, [item.id]: { ...review, resolution_note: event.target.value } }))} />
              <button className="btn small" type="submit">Record review</button>
            </div>
          </form>;
        })}
        <div className="rowmeta" style={{ padding: 12 }}>Feedback never edits frozen answers. Correct the native record, then record the disposition here.</div>
      </div>

      <h2>Writing style versions</h2>
      <div className="card">
        {styles.length > 0 && <table><thead><tr><th>Name</th><th>Audience</th><th>Version</th><th>State</th></tr></thead>
          <tbody>{styles.map((profile) => <tr key={profile.id}><td>{profile.name}</td><td>{profile.audience.replaceAll("_", " ")}</td>
            <td>{profile.version}</td><td>{profile.is_active ? "active" : "superseded"}</td></tr>)}</tbody></table>}
        <form className="actions" style={{ padding: 12, flexWrap: "wrap" }} onSubmit={async (event) => {
          event.preventDefault();
          try {
            const active = styles.find((profile) => profile.audience === "internal" && profile.is_active);
            await api.createCopilotStyle({ name: styleName, audience: "internal", effective_on: new Date().toISOString().slice(0, 10), author: "operator",
              supersedes_id: active?.id || null, rules: { max_characters: Number(maxChars), max_headings: 6, banned_phrases: ["model confidence"] } });
            await loadStyles(); toast(active ? "Style version superseded." : "Style profile created.");
          } catch (error) { toast(error.message, "err"); }
        }}>
          <input aria-label="Style profile name" value={styleName} onChange={(event) => setStyleName(event.target.value)} />
          <input aria-label="Maximum characters" type="number" min="500" value={maxChars} onChange={(event) => setMaxChars(event.target.value)} style={{ width: 150 }} />
          <button className="btn" type="submit">{styles.some((profile) => profile.audience === "internal" && profile.is_active) ? "Create next version" : "Create profile"}</button>
        </form>
        <div className="rowmeta" style={{ padding: "0 12px 12px" }}>Explicit rules only. Samples are never harvested automatically; changes create a new version.</div>
      </div>

      <h2>Source freshness</h2>
      <div className="card">
        {ops.source_freshness.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No metric sources.</div> : (
          <table><thead><tr><th>Metric</th><th style={{ width: 150 }}>Current through</th><th style={{ width: 100 }}>State</th></tr></thead>
            <tbody>{ops.source_freshness.map((f, i) => (
              <tr key={i}><td>{f.metric}</td><td className="rowmeta">{fmtDate(f.current_through)}</td>
                <td>{f.stale ? <span style={{ color: "var(--status-warn)" }}>⚠ stale</span> : <span style={{ color: "var(--status-ok)" }}>fresh</span>}</td></tr>
            ))}</tbody></table>
        )}
      </div>

      <h2>Import batches</h2>
      <div className="card">
        {ops.import_batches.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No imports yet.</div> : (
          <table><thead><tr><th>Adapter</th><th style={{ width: 70 }}>Rows</th><th style={{ width: 120 }}>Status</th><th style={{ width: 140 }}>Created</th></tr></thead>
            <tbody>{ops.import_batches.map((b) => (
              <tr key={b.id}><td>{b.adapter}</td><td className="rowmeta">{b.row_count}</td>
                <td><span className="badge" style={b.status === "rolled_back" ? { borderColor: "var(--status-risk)", color: "var(--status-risk)" } : {}}>{b.status}</span></td>
                <td className="rowmeta">{b.created_at?.slice(0, 10)}</td></tr>
            ))}</tbody></table>
        )}
        {ops.failed_or_rolled_back > 0 && <div className="rowmeta" style={{ padding: "8px 12px", color: "var(--status-risk)" }}>{ops.failed_or_rolled_back} rolled-back batch(es).</div>}
      </div>

      <h2>Internal operating records</h2>
      <div className="card">
        <table><thead><tr><th>Record type</th><th style={{ width: 120 }}>Rows</th></tr></thead>
          <tbody>{(ops.internal_record_counts || []).map((r) => <tr key={r.record_type}>
            <td>{r.record_type.replaceAll("_", " ")}</td><td>{r.count ?? "migration missing"}</td>
          </tr>)}</tbody></table>
      </div>

      <h2>Connection registry</h2>
      <div className="card">
        <table><thead><tr><th scope="col">Boundary</th><th scope="col">Current mode</th><th scope="col">Gate</th><th scope="col">Mock fixtures</th></tr></thead>
          <tbody>{(ops.connection_registry?.connections || []).map((a) => <tr key={a.id}>
            <td><div>{a.label}</div><div className="rowmeta">{a.config_switch}</div></td>
            <td><span className="badge">{a.current_mode.replaceAll("_", " ")}</span></td>
            <td><span className="badge" style={a.gate_status === "blocked" ? { borderColor: "var(--status-risk)", color: "var(--status-risk)" } : {}}>{a.gate_status}</span></td>
            <td className="rowmeta">{a.fixtures.length ? a.fixtures.join(", ") : "—"}</td>
          </tr>)}</tbody></table>
        <div className="rowmeta" style={{ padding: 12 }}>
          Policy: {ops.connection_registry?.policy}. Real modes require both explicit approval and a decision-log reference.
        </div>
      </div>
    </div>
  );
}
