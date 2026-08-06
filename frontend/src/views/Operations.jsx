import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { AgeChip, Loading, useToast, fmtDate } from "../ui";

/**
 * One funnel's counts. Rendered from a `totals` block rather than from the response, so the
 * aggregate and each per-ruleset block are drawn by the same code and cannot describe themselves
 * differently. "left the list" is the event's own name: Account Path never closes anything, so a
 * row's absence is all that was observed — a cancellation looks identical to a completion here.
 */
function FunnelChips({ totals }) {
  return (
    <div className="chiprow">
      <span className="badge">views · {totals.views}</span>
      <span className="badge">with a move · {totals.views_with_next_move}</span>
      <span className="badge">opened · {totals.next_move_opened}</span>
      <span className="badge">left the list · {totals.next_move_left_list}</span>
      <span className="badge">snoozed · {totals.next_move_snoozed}</span>
      <span className="badge">successors · {totals.successor_actions_created}</span>
      <span className="badge">incomplete coverage · {totals.views_with_incomplete_coverage}</span>
    </div>
  );
}

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
  // Product measurement (ACCOUNT-PATH-SPEC.md §17). Loaded and failed independently of everything
  // else on this screen: the diagnostics sink must never be able to blank Operations.
  const [measurement, setMeasurement] = useState(null);
  const [rules, setRules] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [comparing, setComparing] = useState(false);
  const loadMeasurement = useCallback(() => Promise.all([
    api.telemetryFunnel().then((result) => setMeasurement(result)),
    api.rankingRules().then((result) => setRules(result)),
  ]).catch(() => {}), []);
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
    loadMeasurement();
  }, [reloadKey, loadStyles, loadCopilotOps, loadMeasurement, toast]);
  if (!ops) return <Loading what="operations" />;

  return (
    <div className="card-stack">
      <h1>Operations</h1>
      <div className="rowmeta" style={{ marginBottom: 14 }}>As of {ops.as_of}. Mock/local mode.</div>

      <div className="two-col" style={{ gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div className="card" style={{ padding: 12 }}>
          <div className="rowmeta" style={{ textTransform: "uppercase" }}>Job worker</div>
          <div>{ops.job_worker}</div>
          <div className="rowmeta" style={{ marginTop: 12, textTransform: "uppercase" }}>Audit events</div>
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
        {!!ops.company_intelligence?.source_freshness?.length && <table><thead><tr><th scope="col">Source class</th><th scope="col" className="num">Latest retrieval</th><th scope="col" className="num">Documents</th><th scope="col" className="num">Retracted</th></tr></thead>
          <tbody>{ops.company_intelligence.source_freshness.map((row) => <tr key={row.source_class}><td>{row.source_class.replaceAll("_", " ")}</td><td className="num">{fmtDate(row.latest_retrieval)} <AgeChip date={row.latest_retrieval} /></td><td className="num">{row.documents}</td><td className="num">{row.retracted}</td></tr>)}</tbody></table>}
      </div>

      <h2>Campaign learning</h2>
      <div className="card" aria-label="Portfolio campaign learning">
        {!learning ? <Loading what="campaign learning" /> : <>
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
          {!!learning.by_intervention_kind?.length && <table><thead><tr><th scope="col">Intervention</th><th scope="col" className="num">Observed</th><th scope="col" className="num">Appeared to help</th><th scope="col" className="num">Failed / did not help</th></tr></thead>
            <tbody>{learning.by_intervention_kind.map((row) => <tr key={row.intervention_kind}>
              <td>{row.intervention_kind.replaceAll("_", " ")}</td><td className="num">{row.interventions_observed}</td>
              <td className="num">{row.helped}</td><td className="num">{row.failed}</td></tr>)}</tbody></table>}
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
        {!!configs.length && <table><thead><tr><th scope="col">Version set</th><th scope="col">State</th><th scope="col" className="num">Evaluated</th><th scope="col">Release control</th></tr></thead>
          <tbody>{configs.map((config) => <tr key={config.id}>
            <td><div>{config.label}</div><div className="rowmeta">{config.model_version} · {config.prompt_version} · {config.retrieval_version} · {config.validator_version}</div></td>
            <td><span className="badge">{config.status}</span></td><td className="num">{config.evaluated_at?.slice(0, 10) || "not evaluated"}</td>
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
        {styles.length > 0 && <table><thead><tr><th scope="col">Name</th><th scope="col">Audience</th><th scope="col" className="num">Version</th><th scope="col">State</th></tr></thead>
          <tbody>{styles.map((profile) => <tr key={profile.id}><td>{profile.name}</td><td>{profile.audience.replaceAll("_", " ")}</td>
            <td className="num">{profile.version}</td><td>{profile.is_active ? "active" : "superseded"}</td></tr>)}</tbody></table>}
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
          <table><thead><tr><th scope="col">Metric</th><th scope="col" className="num" style={{ width: 150 }}>Current through</th><th scope="col" style={{ width: 100 }}>State</th></tr></thead>
            <tbody>{ops.source_freshness.map((f, i) => (
              <tr key={i}><td>{f.metric}</td><td className="rowmeta num">{fmtDate(f.current_through)} <AgeChip date={f.current_through} /></td>
                <td>{f.stale ? <span style={{ color: "var(--status-warn)" }}>⚠ stale</span> : <span style={{ color: "var(--status-ok)" }}>fresh</span>}</td></tr>
            ))}</tbody></table>
        )}
      </div>

      <h2>Import batches</h2>
      <div className="card">
        {ops.import_batches.length === 0 ? <div className="rowmeta" style={{ padding: 12 }}>No imports yet.</div> : (
          <table><thead><tr><th scope="col">Adapter</th><th scope="col" className="num" style={{ width: 70 }}>Rows</th><th scope="col" style={{ width: 120 }}>Status</th><th scope="col" className="num" style={{ width: 140 }}>Created</th></tr></thead>
            <tbody>{ops.import_batches.map((b) => (
              <tr key={b.id}><td>{b.adapter}</td><td className="rowmeta num">{b.row_count}</td>
                <td><span className="badge" style={b.status === "rolled_back" ? { borderColor: "var(--status-risk)", color: "var(--status-risk)" } : {}}>{b.status}</span></td>
                <td className="rowmeta num">{b.created_at?.slice(0, 10)}</td></tr>
            ))}</tbody></table>
        )}
        {ops.failed_or_rolled_back > 0 && <div className="rowmeta" style={{ padding: "8px 12px", color: "var(--status-risk)" }}>{ops.failed_or_rolled_back} rolled-back batch(es).</div>}
      </div>

      <h2>Internal operating records</h2>
      <div className="card">
        <table><thead><tr><th scope="col">Record type</th><th scope="col" className="num" style={{ width: 120 }}>Rows</th></tr></thead>
          <tbody>{(ops.internal_record_counts || []).map((r) => <tr key={r.record_type}>
            <td>{r.record_type.replaceAll("_", " ")}</td><td className="num">{r.count ?? "migration missing"}</td>
          </tr>)}</tbody></table>
      </div>

      <h2>Product measurement</h2>
      <div className="card" aria-label="Product measurement">
        {!measurement ? <div className="rowmeta" style={{ padding: 12 }}>
          Measurement could not be read. Treat the absence as unknown, not as zero use.
        </div> : <>
          <div className="grid2" style={{ padding: 12 }}>
            <div>
              <div className="rowmeta">Local diagnostics</div>
              <div>
                {measurement.settings.enabled ? "Recording" : "Disabled"} · retention{" "}
                {measurement.settings.retention_days} days · nothing leaves this installation
              </div>
              <div className="actions" style={{ marginTop: 8, flexWrap: "wrap" }}>
                {/* §17.4: a local setting can disable measurement. Turning it off also discards
                    what was collected, which the button says rather than leaving to be found. */}
                <button className="btn small" onClick={async () => {
                  try {
                    await api.patchTelemetrySettings({ enabled: !measurement.settings.enabled });
                    await loadMeasurement();
                    toast(measurement.settings.enabled
                      ? "Measurement disabled and existing events discarded."
                      : "Measurement recording.");
                  } catch (error) { toast(error.message, "err"); }
                }}>
                  {measurement.settings.enabled
                    ? "Disable and delete collected events" : "Enable measurement"}
                </button>
              </div>
            </div>
            <div>
              <div className="rowmeta">
                Funnel{measurement.rule_versions.length > 0 && <>
                  {" · "}{measurement.rule_versions.map((v) => v.ranking_rule_version).join(", ")}
                </>}
              </div>
              <FunnelChips totals={measurement.totals} />
            </div>
          </div>
          {/* Which ordering produced these numbers is part of the numbers. When the data spans
              more than one ruleset the aggregate above describes no single ordering, so the
              separable ones render underneath rather than being left in the payload. */}
          {measurement.spans_multiple_rule_versions && <div style={{ padding: "0 12px 12px" }}>
            {measurement.by_rule_version.map((block) => (
              <div key={block.ranking_rule_version} style={{ marginTop: 8 }}>
                <div className="rowmeta">Ranked by {block.ranking_rule_version}</div>
                <FunnelChips totals={block.totals} />
              </div>
            ))}
          </div>}
          {measurement.by_reason_code.length > 0 && <table>
            <thead><tr>
              <th scope="col">Ranking reason</th><th scope="col" className="num">Opened</th>
              <th scope="col" className="num">Left the list</th>
              <th scope="col" className="num">Snoozed</th>
            </tr></thead>
            <tbody>{measurement.by_reason_code.map((row) => <tr key={row.reason_code}>
              <td>{row.reason_code.replaceAll("_", " ")}</td>
              <td className="num">{row.opened}</td><td className="num">{row.left_list}</td>
              <td className="num">{row.snoozed}</td>
            </tr>)}</tbody>
          </table>}
          {/* The §17.5 caveat, on screen rather than only in the payload: this is the number most
              likely to be quoted on its own. */}
          <div className="rowmeta" style={{ padding: 12 }}>{measurement.caveat}</div>
        </>}
      </div>

      <h2>Ranking rule versions</h2>
      <div className="card" aria-label="Ranking rule versions">
        {!rules ? <div className="rowmeta" style={{ padding: 12 }}>Rule versions unavailable.</div> : <>
          <table><thead><tr>
            <th scope="col">Version</th><th scope="col">State</th><th scope="col">What it changes</th>
          </tr></thead>
            <tbody>{rules.versions.map((version) => <tr key={version.version}>
              <td>{version.version}</td>
              <td><span className="badge">
                {version.version === rules.active_version ? "live" : version.status}
              </span></td>
              <td className="rowmeta">{version.summary}</td>
            </tr>)}</tbody>
          </table>
          <div className="actions" style={{ padding: 12, flexWrap: "wrap" }}>
            {/* §17.6 step 4. Comparing is a read: it builds each account's path twice and diffs the
                ordering. It never selects a ruleset — that is the `VALENCE_OS_RANKING_RULES` flag,
                deliberately outside the app so an ordering change is a deployment decision. */}
            <button className="btn small" disabled={comparing} onClick={async () => {
              setComparing(true);
              try { setComparison(await api.compareRankingRules({})); }
              catch (error) { toast(error.message, "err"); }
              finally { setComparing(false); }
            }}>Compare orderings across seeded accounts</button>
            <span className="rowmeta">
              Selected by {rules.flag} at deployment, never from this screen.
            </span>
          </div>
          {comparison && <>
            <table><thead><tr>
              <th scope="col">Account</th><th scope="col">Next move changes</th>
              <th scope="col" className="num">Rows that move</th>
            </tr></thead>
              <tbody>{comparison.accounts.map((row) => <tr key={row.account_id}>
                <td>{row.account_name}</td>
                <td>{row.next_move_changed
                  ? <span className="badge" style={{ borderColor: "var(--status-warn)" }}>
                    changes
                  </span>
                  : <span className="rowmeta">unchanged</span>}</td>
                <td className="num">{row.moved_rows.length}</td>
              </tr>)}</tbody>
            </table>
            <div className="rowmeta" style={{ padding: 12 }}>
              {comparison.version_a} → {comparison.version_b} · {comparison.accounts_with_changes} of{" "}
              {comparison.accounts.length} accounts reorder. §17.6 asks for the surprising ones to be
              reviewed by a person before a version ships; this table is the input to that review,
              not the decision.
            </div>
          </>}
        </>}
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
