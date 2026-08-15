/**
 * Stage 17 Slice 3 — recording a cause and applying a reviewed set (`SURFACE-USAGE-SPEC.md` §7.8).
 *
 * The whole screen is built around one shape: **stage, preview, apply, undo.** Nothing is applied
 * from a row. A simplification pass is a sitting — you look at the whole screen, decide what goes,
 * and see what the screen looks like afterwards before committing — and per-row apply buttons turn
 * that into twenty independent decisions each made without the others in view. That matters because
 * §7.7's safety check is a property of the *set*: two retirements that are individually safe can
 * between them empty a route to a record type.
 *
 * Three things this view deliberately does not do.
 *
 * - **It does not decide whether an action is allowed.** The available actions per kind, the field
 *   group refusal, and the safety check all arrive from the server. A client that knew the rules
 *   would be a second place a retirement could be judged safe, and the client registry does not
 *   even mirror the fields the check reads.
 * - **It does not compose a refusal.** Every refusal is rendered verbatim (D-151…D-155).
 * - **It does not rank.** The list is in the report's own order, and the cause dropdown lists
 *   §7.1's seven in the spec's order with `narrow_but_needed` among them, not hidden behind a
 *   "keep" affordance — a form that can only agree with itself is not a review.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { useSurfaceRetirement } from "../measure";

const CAUSE_PLACEHOLDER = "Record a cause…";

export default function SurfaceRetirement() {
  const [state, setState] = useState(null);
  const [report, setReport] = useState(null);
  const [staged, setStaged] = useState({});
  const [preview, setPreview] = useState(null);
  const [failed, setFailed] = useState(null);
  const [lastBatch, setLastBatch] = useState(null);
  const [undone, setUndone] = useState(null);

  // The wrapper's copy of the same map, refetched whenever a decision here lands. Without it the
  // running app went on rendering against the map it fetched at start-up, so a surface retired on
  // this screen stayed visible everywhere else until a reload — and a retirement that appears to
  // have done nothing is one somebody applies a second time. Called from the three mutations
  // rather than from `load`, which also runs on mount: this screen opening is not a decision.
  const { refresh: refreshWrappers } = useSurfaceRetirement();

  const load = useCallback(() => {
    Promise.all([api.surfaceRetirement(), api.surfaceUsage({})])
      .then(([retirement, usage]) => { setState(retirement); setReport(usage); })
      .catch(() => setFailed("Retirement state could not be read."));
  }, []);

  useEffect(() => { load(); }, [load]);

  const entries = useMemo(() => Object.entries(staged)
    .filter(([, entry]) => entry && entry.cause_code)
    .map(([surface, entry]) => ({ surface, ...entry })), [staged]);

  useEffect(() => {
    if (!entries.length) { setPreview(null); return undefined; }
    let live = true;
    api.surfaceRetirementPreview(entries)
      .then((result) => { if (live) setPreview(result); })
      .catch(() => { if (live) setPreview(null); });
    return () => { live = false; };
  }, [entries]);

  if (failed) {
    return <div className="card"><div className="rowmeta" style={{ padding: 12 }}>{failed}</div></div>;
  }
  if (!state || !report) {
    return <div className="card"><div className="rowmeta" style={{ padding: 12 }}>Reading…</div></div>;
  }

  const vocabulary = state.vocabulary;
  const stage = (surface, patch) => setStaged((current) => ({
    ...current, [surface]: { ...(current[surface] || { action: "none" }), ...patch },
  }));

  const apply = () => {
    setFailed(null);
    api.surfaceRetirementApply(entries)
      .then((result) => { setLastBatch(result); setStaged({}); load(); refreshWrappers(); })
      .catch((error) => setFailed(String(error && error.message ? error.message : error)));
  };

  const undo = () => {
    api.surfaceRetirementUndo(lastBatch.batch_id)
      .then((result) => { setUndone(result); setLastBatch(null); load(); refreshWrappers(); })
      .catch((error) => setFailed(String(error && error.message ? error.message : error)));
  };

  const restore = (surface) => {
    api.surfaceRetirementRestore(surface)
      .then(() => { load(); refreshWrappers(); })
      .catch((error) => setFailed(String(error && error.message ? error.message : error)));
  };

  const currentlyChanged = Object.values(state.surfaces)
    .filter((row) => row.action !== "none" && row.action !== "restore");

  return (
    <div className="card" aria-label="Record a cause">
      <div className="rowmeta" style={{ padding: 12 }}>
        {/* §7.9, from the server, so a view cannot present a retirement as a deletion. */}
        {preview ? preview.code_deletion : vocabulary.actions.find((a) => a.action === "retire").meaning}
      </div>

      <div className="surface-usage-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Surface</th>
              <th scope="col">Observation</th>
              <th scope="col">Cause</th>
              <th scope="col">Action</th>
              <th scope="col">Now</th>
            </tr>
          </thead>
          <tbody>
            {report.surfaces.map((row) => {
              const current = state.surfaces[row.surface] || {};
              const entry = staged[row.surface] || {};
              const available = current.available_actions || [];
              return (
                <tr key={row.surface}>
                  <th scope="row" style={{ fontWeight: 400 }}>{row.label}</th>
                  <td>
                    {row.observation_label}
                    {!row.instrumented && row.instrumentation_note
                      ? <div className="rowmeta">{row.instrumentation_note}</div>
                      : null}
                  </td>
                  <td>
                    <select
                      aria-label={`Cause for ${row.label}`}
                      value={entry.cause_code || ""}
                      onChange={(event) => stage(row.surface, { cause_code: event.target.value })}
                    >
                      <option value="">{CAUSE_PLACEHOLDER}</option>
                      {vocabulary.cause_codes.map((cause) => (
                        <option key={cause.code} value={cause.code} title={cause.meaning}>
                          {cause.code.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select
                      aria-label={`Action for ${row.label}`}
                      value={entry.action || "none"}
                      disabled={!entry.cause_code}
                      onChange={(event) => stage(row.surface, { action: event.target.value })}
                    >
                      {/* `none` is always offered: recording a cause without moving anything is a
                          first-class outcome, and it is what `narrow_but_needed` pairs with. */}
                      <option value="none">leave in place</option>
                      {available.map((action) => (
                        <option key={action} value={action}>{action}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    {current.action && current.action !== "none" && current.action !== "restore"
                      ? <span className="badge">{current.action}</span>
                      : <span className="rowmeta">as normal</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {preview && (
        <div style={{ padding: 12, borderTop: "1px solid var(--line-hairline)" }}>
          <div className="rowmeta">What this sitting would do</div>
          {preview.refusals.length > 0 && (
            <ul className="chiprow" style={{ display: "block", margin: "8px 0" }}>
              {preview.refusals.map((refusal, index) => (
                // Verbatim. A view that composes part of a refusal can soften one.
                <li key={`${refusal.surface}-${refusal.rule}-${index}`} className="rowmeta">
                  {refusal.message}
                </li>
              ))}
            </ul>
          )}
          {preview.routes.map((route) => (
            <div key={route.route} style={{ marginTop: 8 }}>
              <div style={{ fontWeight: 500 }}>{route.route}</div>
              <div className="rowmeta">
                Still offered: {route.still_offered.join(", ") || "nothing"}
              </div>
            </div>
          ))}
          <div className="rowmeta" style={{ marginTop: 8 }}>{preview.caveat}</div>
          <div className="actions" style={{ marginTop: 8 }}>
            <button
              className="btn small primary"
              disabled={preview.refusals.length > 0 || preview.items.length === 0}
              onClick={apply}
            >
              Apply {preview.items.length} change{preview.items.length === 1 ? "" : "s"}
            </button>
            <button className="btn small" onClick={() => setStaged({})}>Clear</button>
          </div>
          {preview.refusals.length > 0 && (
            <div className="rowmeta" style={{ marginTop: 4 }}>
              Nothing is applied while a refusal stands. A batch is all-or-nothing.
            </div>
          )}
        </div>
      )}

      {/* An undo that reversed fewer surfaces than the sitting held is a subtractive answer, and
          D-160's rule applies here as much as to a snoozed row: it is stated, quietly and without
          a status hue, because a withheld row is not a failure. The sentence is the server's. */}
      {undone && (
        <div style={{ padding: 12, borderTop: "1px solid var(--line-hairline)" }}>
          <div>
            Restored {undone.restored.length} surface{undone.restored.length === 1 ? "" : "s"}.
          </div>
          {undone.note && (
            <div className="rowmeta" style={{ marginTop: 4 }}>{undone.note}</div>
          )}
        </div>
      )}

      {lastBatch && (
        <div style={{ padding: 12, borderTop: "1px solid var(--line-hairline)" }}>
          <div>Applied {lastBatch.applied} change{lastBatch.applied === 1 ? "" : "s"}.</div>
          <div className="actions" style={{ marginTop: 4 }}>
            <button className="btn small" onClick={undo}>
              Undo this sitting
            </button>
          </div>
          <div className="rowmeta" style={{ marginTop: 4 }}>
            A whole sitting can be undone for {vocabulary.undo_window_days} days. Restoring one
            surface never expires.
          </div>
        </div>
      )}

      <div style={{ padding: 12, borderTop: "1px solid var(--line-hairline)" }}>
        <div className="rowmeta">Currently collapsed, moved, or retired</div>
        {currentlyChanged.length === 0
          ? <div className="rowmeta" style={{ marginTop: 4 }}>Nothing has been changed.</div>
          : (
            <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
              {currentlyChanged.map((row) => (
                <li key={row.surface} className="chiprow" style={{ marginBottom: 4 }}>
                  <span className="badge">{row.action}</span>
                  <span>{row.surface}</span>
                  <span className="rowmeta">
                    {row.cause_code ? row.cause_code.replaceAll("_", " ") : "no cause"} ·{" "}
                    {row.recorded_on ? row.recorded_on.slice(0, 10) : ""}
                  </span>
                  <button className="btn small" onClick={() => restore(row.surface)}>Restore</button>
                </li>
              ))}
            </ul>
          )}
      </div>
    </div>
  );
}
