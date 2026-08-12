/**
 * Stage 17 Slice 2 — the Surface usage report (`SURFACE-USAGE-SPEC.md` §8).
 *
 * The design problem here is not the table, it is what the table invites. A grid of low numbers
 * beside a list of screen names reads as a kill list unless the page works against it, so three
 * things are deliberate:
 *
 * **Default order is navigation order.** The server decides this and the client does not re-sort.
 * Least-used-first is one control click away and is never where you land, because the top row of a
 * disuse leaderboard is whichever surface has the least honest window rather than the least useful
 * one.
 *
 * **`insufficient_window` rows are cross-hatched, not greyed to zero.** That is the same treatment
 * the design guide already uses for stale data, and it is exactly what these rows are: not-yet-
 * knowable, not zero. The row also carries the server's sentence saying how long it observed and
 * how long it would need, so the claim is checkable rather than atmospheric.
 *
 * **Nothing on this page combines the four axes.** There is no total, no rate, no percentage, and
 * no colour that means "bad" — the observation is a word and a shape, never a hue, because a single
 * number here would be read as a kill order and the data cannot support that reading.
 *
 * Every sentence in the report — the caveat, the window refusal, what each observation suggests —
 * is authored on the server and rendered verbatim. A view that composes part of a caution can
 * soften one (D-151…D-155).
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";

/** The observation cell: a word and a shape, never a colour on its own. */
function Observation({ row }) {
  if (row.observation === "insufficient_window") {
    return (
      <span className="unknown-chip">
        <span className="unknown-hatch" aria-hidden="true" />
        {row.observation_label}
      </span>
    );
  }
  return <span className="badge">{row.observation_label}</span>;
}

/**
 * A count that has no basis yet renders as the unknown treatment rather than as its digit.
 *
 * Showing "0 rendered" beside "not yet knowable" would put the two readings on screen at once and
 * let the eye take the number. The number is still in the payload; it is just not a claim yet.
 */
function Count({ value, covered }) {
  if (!covered) return <span className="unknown-hatch" aria-hidden="true" title="not yet knowable" />;
  return <>{value}</>;
}

/**
 * §8's screen-weight view: what each screen costs and what it returns.
 *
 * Four independent counters per screen and one list. There is deliberately no "2 of 11" here and no
 * bar: a proportion would be the composite §12 forbids, and it would rank screens against each
 * other when the useful reading is *within* one screen. `sections_not_yet_knowable` is its own
 * column for the same reason it is its own counter on the server — a section whose window cannot
 * cover it has not been shown to be unwanted.
 */
function ScreenWeight({ screens, caveat }) {
  return (
    <div className="card" aria-label="Screen weight" style={{ marginTop: 12 }}>
      <div style={{ padding: 12 }}>
        <div style={{ fontWeight: 500 }}>What each screen costs</div>
        <div className="rowmeta" style={{ marginTop: 4 }}>
          Sections registered on each screen, in navigation order.
        </div>
      </div>
      <div className="surface-usage-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Screen</th>
              <th scope="col" className="num">Sections</th>
              <th scope="col" className="num">Shown</th>
              <th scope="col" className="num">Operated</th>
              <th scope="col" className="num">Not yet knowable</th>
              <th scope="col">Never operated</th>
            </tr>
          </thead>
          <tbody>
            {screens.map((screen) => (
              <tr key={screen.route}>
                <th scope="row" style={{ fontWeight: 400 }}>{screen.route}</th>
                <td className="num">{screen.sections}</td>
                <td className="num">{screen.sections_rendered}</td>
                <td className="num">{screen.sections_engaged}</td>
                <td className="num">
                  {screen.sections_not_yet_knowable > 0
                    ? (
                      <span className="unknown-chip">
                        <span className="unknown-hatch" aria-hidden="true" />
                        {screen.sections_not_yet_knowable}
                      </span>
                    )
                    : 0}
                </td>
                <td>
                  {screen.never_engaged.length === 0
                    ? <span className="rowmeta">—</span>
                    : (
                      <div className="chiprow">
                        {screen.never_engaged.map((entry) => (
                          <span key={entry.surface} className="badge">{entry.label}</span>
                        ))}
                      </div>
                    )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Server-authored, and it is the sentence that keeps this table from reading as a verdict. */}
      <div className="rowmeta" style={{ padding: 12 }}>{caveat}</div>
    </div>
  );
}

/**
 * §7.0's redundancy checklist — the twenty-minute manual pass the counts cannot do.
 *
 * This is a question list. Nothing here is a defect, nothing is staged, and there is no action: the
 * whole point is that two surfaces both operated weekly can be answering the same question in two
 * places, and the usage table calls both of them healthy. Rendering it as a to-do would be claiming
 * the app had found something, which it has not — it has only counted routes.
 */
function RedundancyChecklist() {
  const [checklist, setChecklist] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.surfaceRedundancy()
      .then((result) => { setChecklist(result); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  if (failed || !checklist) {
    return (
      <div className="card" aria-label="Redundancy checklist" style={{ marginTop: 12 }}>
        <div className="rowmeta" style={{ padding: 12 }}>
          {failed
            ? "The redundancy checklist could not be read. It is a read over the registry; nothing was changed."
            : "Reading the registry…"}
        </div>
      </div>
    );
  }

  return (
    <div className="card" aria-label="Redundancy checklist" style={{ marginTop: 12 }}>
      <div style={{ padding: 12 }}>
        <div style={{ fontWeight: 500 }}>What telemetry cannot see</div>
        {/* The honest limit goes above the list, not below it: it is the reason the list exists. */}
        <div className="rowmeta" style={{ marginTop: 4 }}>{checklist.honest_limit}</div>
        <div className="rowmeta" style={{ marginTop: 8 }}>{checklist.cadence}</div>
      </div>
      <div className="surface-usage-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Record type</th>
              <th scope="col" className="num">Surfaces reaching it</th>
              <th scope="col">Where</th>
            </tr>
          </thead>
          <tbody>
            {checklist.record_types.map((item) => (
              <tr key={item.record_type}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  {item.record_type.replaceAll("_", " ")}
                  {/* A question, phrased as one. Not a warning hue, not a severity, not a count of
                      problems — three routes to one record type is worth twenty minutes and may
                      well be correct. */}
                  {item.ask_why && (
                    <div className="rowmeta">
                      {item.count} surfaces answer questions about this record. Ask why.
                    </div>
                  )}
                </th>
                <td className="num">{item.count}</td>
                <td>
                  <div className="chiprow">
                    {item.surfaces.map((entry) => (
                      <span key={entry.surface} className="badge" title={entry.route}>
                        {entry.label}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="rowmeta" style={{ padding: 12 }}>
        {checklist.ask_why} of {checklist.record_types.length} record types are reached by{" "}
        {checklist.threshold} surfaces or more. Retired surfaces are not counted.
      </div>
    </div>
  );
}

export default function SurfaceUsage() {
  const [report, setReport] = useState(null);
  const [failed, setFailed] = useState(false);
  const [sort, setSort] = useState("navigation");

  const load = useCallback((nextSort) => {
    api.surfaceUsage({ sort: nextSort === "least_used" ? "least_used" : null })
      .then((result) => { setReport(result); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => { load(sort); }, [load, sort]);

  if (failed) {
    return (
      <div className="card" aria-label="Surface usage">
        <div className="rowmeta" style={{ padding: 12 }}>
          Surface usage could not be read. Treat the absence as unknown, not as zero use.
        </div>
      </div>
    );
  }
  if (!report) {
    return (
      <div className="card" aria-label="Surface usage">
        <div className="rowmeta" style={{ padding: 12 }}>Reading surface usage…</div>
      </div>
    );
  }

  const { window: observed, totals } = report;

  return (
    <>
    <div className="card" aria-label="Surface usage">
      <div className="grid2" style={{ padding: 12 }}>
        <div>
          <div className="rowmeta">Observation window</div>
          {/* §9.1: the window's start date, stated prominently rather than buried, so a period
              known to have been a build week can be discounted by the person reading. */}
          <div>
            {observed.measuring_since
              ? <>Observing since {observed.measuring_since} · {observed.observed_days} days</>
              : <>Not currently observing. Measurement is off, and turning it off discarded what
                  had been collected.</>}
          </div>
          {observed.requested_window_days
            && observed.requested_window_days > observed.observed_days && (
            <div className="rowmeta" style={{ marginTop: 4 }}>
              A {observed.requested_window_days}-day window was requested; only{" "}
              {observed.observed_days} days have been observed, so that is the window used.
            </div>
          )}
          {/* The counts are summed over whole months, so they reach outside the dates above. The
              sentence is the server's whole — a view that composed part of it could drop the part
              that makes the numbers wider than they look. */}
          {report.partial_months && report.partial_months.notice && (
            <div className="rowmeta" style={{ marginTop: 4 }}>
              {report.partial_months.notice}
            </div>
          )}
        </div>
        <div>
          <div className="rowmeta">Surfaces</div>
          {/* Four independent counters. They are never divided, totalled into a rate, or coloured:
              the same rule VISIBILITY's four absence counters follow. */}
          <div className="chiprow" style={{ marginTop: 4 }}>
            <span className="badge">registered · {totals.surfaces}</span>
            <span className="badge">engaged · {totals.engaged}</span>
            <span className="badge">shown, never operated · {totals.rendered_not_engaged}</span>
            <span className="badge">never displayed · {totals.not_rendered}</span>
            <span className="unknown-chip">
              <span className="unknown-hatch" aria-hidden="true" />
              not yet knowable · {totals.insufficient_window}
            </span>
            {totals.uninstrumented > 0 && (
              <span className="badge">not instrumented · {totals.uninstrumented}</span>
            )}
          </div>
        </div>
      </div>

      <div className="actions" style={{ padding: "0 12px 12px", flexWrap: "wrap" }}>
        {/* Sorting by disuse is an explicit choice, and the button says what it does rather than
            being labelled "sort". Landing on it by default is what would make this a kill list. */}
        <button
          className="btn small"
          aria-pressed={sort === "least_used"}
          onClick={() => setSort(sort === "least_used" ? "navigation" : "least_used")}
        >
          {sort === "least_used" ? "Back to navigation order" : "Order by least used"}
        </button>
      </div>

      <div className="surface-usage-table">
        <table>
          <thead>
            <tr>
              <th scope="col">Surface</th>
              <th scope="col">Screen</th>
              <th scope="col">Cadence</th>
              <th scope="col" className="num">Shown</th>
              <th scope="col" className="num">Operated</th>
              <th scope="col">Last operated</th>
              <th scope="col">Observation</th>
              <th scope="col">Recorded cause</th>
            </tr>
          </thead>
          <tbody>
            {report.surfaces.map((row) => (
              <tr key={row.surface} className={row.window_covered ? undefined : "row-unknowable"}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  {row.label}
                  {!row.instrumented && (
                    <div className="rowmeta">Not instrumented — {row.instrumentation_note}</div>
                  )}
                  {row.notice && <div className="rowmeta">{row.notice}</div>}
                  {/* §6.4. Stated beside the surface it covers and never in the Shown/Operated
                      columns, because it is a coverage fact rather than a third count of use — the
                      three numbers are read side by side and none of them is divided by another. */}
                  {row.window_covered && row.trigger_available && row.trigger_condition && (
                    <div className="rowmeta">
                      Covered by its trigger: {row.trigger_condition}, {row.trigger_count} times in
                      this window.
                    </div>
                  )}
                </th>
                <td>{row.route}</td>
                <td>{row.cadence.replaceAll("_", " ")}</td>
                <td className="num"><Count value={row.rendered} covered={row.window_covered} /></td>
                <td className="num"><Count value={row.engaged} covered={row.window_covered} /></td>
                <td>
                  {row.window_covered && row.last_engaged_on
                    ? row.last_engaged_on
                    : <span className="rowmeta">—</span>}
                </td>
                <td><Observation row={row} /></td>
                {/* §6.1's fourth axis is never inferred. Until Slice 3 lets an operator record one,
                    this column is honestly empty rather than filled with a guess. */}
                <td>{row.recorded_cause
                  ? row.recorded_cause.replaceAll("_", " ")
                  : <span className="rowmeta">none recorded</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* §8: beside the numbers, not in a tooltip. This is the sentence most likely to be needed by
          whoever quotes a row out of this table. */}
      <div className="rowmeta" style={{ padding: 12 }}>{report.caveat}</div>

      <details style={{ padding: "0 12px 12px" }}>
        <summary className="rowmeta">What each observation means</summary>
        <dl style={{ margin: "8px 0 0" }}>
          {Object.entries(report.observations).map(([key, copy]) => (
            <div key={key} style={{ marginBottom: 8 }}>
              <dt style={{ fontWeight: 500 }}>{copy.label}</dt>
              <dd className="rowmeta" style={{ margin: 0 }}>{copy.meaning} {copy.suggests}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>

    {/* Below the per-surface table, because the screen-level reading is only meaningful once you
        have seen which rows were not yet knowable. */}
    <ScreenWeight screens={report.screens} caveat={report.screen_weight_caveat} />
    <RedundancyChecklist />
    </>
  );
}
