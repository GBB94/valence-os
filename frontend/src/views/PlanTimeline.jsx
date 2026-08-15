/**
 * The launch timeline: the merged standard drawn against one shared time axis.
 *
 * This is the primary element of the Plan tab. The stage cards below it answer "what is open right
 * now"; this answers the question that comes first — "we have had the call, where are we and what
 * is coming" — which is the shape Zach asked for. All geometry, ordering, status wording and
 * accessible naming come from `../planTimeline.js`; this file draws what that module returns and
 * decides nothing.
 *
 * Two things it is careful about, both of which a timeline makes easy to get wrong:
 *
 * - **Colour never carries the meaning alone.** The three kinds are told apart by *shape* (square,
 *   circle, diamond), which is also stated in the legend and in every marker's accessible name.
 *   Status hues appear only on markers that are overdue or flagged, and those markers also change
 *   form — they gain a ring — so the difference survives a greyscale print and a colour-vision
 *   difference. `markerLabel` guarantees the words are always there for a screen reader.
 * - **Density is stated, not hidden.** The axis is bounded, and everything the bounds leave out is
 *   counted in one sentence the module authors (D-160: a subtractive view says so).
 *
 * Selecting a marker fills the caption beneath the axis rather than opening anything — the timeline
 * is for orientation. A condition's caption offers the way through to its evidence panel, which is
 * the same panel the stage cards open, so there is one detail surface and not two.
 */
import { useMemo, useState } from "react";
import { Btn } from "../ui";
import {
  LANES, axisTicks, clusterLabel, planTimeline, pointStatus, timelineNotice,
} from "../planTimeline";

/** Month label for an axis tick. The year appears in January, where the reader needs it. */
function tickLabel(iso) {
  const [y, m] = iso.split("-");
  const d = new Date(Date.UTC(Number(y), Number(m) - 1, 1));
  const month = d.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return m === "01" ? `${month} ${y}` : month;
}

function longDate(iso) {
  const [y, m, d] = iso.split("-");
  return new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)))
    .toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

/**
 * Left offset for a point, inset from both edges so a marker at 0% or 100% is not half-clipped.
 * The inset lives in a token so the rules, the markers and the axis labels all use the same one.
 */
function at(percent) {
  return `calc(var(--ptl-inset) + (100% - 2 * var(--ptl-inset)) * ${percent / 100})`;
}

export default function PlanTimeline({ payload, today, onOpenCondition }) {
  // The selection is a *coordinate* — which lane, which date — and the cluster is looked up in the
  // current timeline on every render. Holding the cluster object instead would survive a reload:
  // tick a setup step in a stage card below, and this caption would go on reporting it open.
  const [pick, setPick] = useState(null);
  const timeline = useMemo(() => planTimeline(payload, today), [payload, today]);
  const ticks = useMemo(
    () => (timeline && !timeline.empty ? axisTicks(timeline.window) : []),
    [timeline],
  );

  const rows = (payload?.setup_items?.length || 0) + (payload?.requirements?.length || 0)
    + (payload?.milestones?.length || 0);
  if (!rows || !timeline) return null;

  // Nothing dated at all. An axis with no markers reads as a rendering failure, so say the reason
  // instead — and it is a different sentence from "no plan has been started here", which the head
  // card above already handles.
  if (timeline.empty) {
    return (
      <section className="card ptl ptl-empty">
        <h3>Launch timeline</h3>
        <p className="rowmeta">
          {timeline.undatedTotal} thing{timeline.undatedTotal === 1 ? "" : "s"} on this plan, none
          of them dated. A timeline can only place what states a date.
        </p>
      </section>
    );
  }

  // Authored whole by the module (D-153's rule applied here): a view that composed half of a
  // subtractive sentence is a view that can drop the other half.
  const notice = timelineNotice(timeline);

  // Resolved fresh. A selected date that no longer has anything on it simply falls back to the
  // prompt rather than showing a row the plan has moved on from.
  const picked = pick
    && timeline.lanes.find((l) => l.key === pick.lane)?.clusters.find((c) => c.date === pick.date);

  return (
    <section className="card ptl" aria-labelledby="ptl-title">
      <div className="actions">
        <h3 id="ptl-title">Launch timeline</h3>
        <div className="spacer" />
        <span className="rowmeta">
          {timeline.drawn} dated · {longDate(timeline.window.start)} to {longDate(timeline.window.end)}
        </span>
      </div>

      {/* The legend does the work the colours are not allowed to do. It names each shape and says
          what that kind of thing is, which is also why the lanes need no colour of their own. */}
      <ul className="ptl-legend">
        {LANES.map((lane) => (
          <li key={lane.key}>
            <span className={`ptl-mark ptl-mark-${lane.marker}`} aria-hidden="true" />
            <span><strong>{lane.title}</strong> — {lane.blurb}</span>
          </li>
        ))}
      </ul>

      <div className="ptl-chart">
        {/* Month rules and the today line, behind the markers and inert to the pointer. */}
        <div className="ptl-rules" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t.date} className="ptl-rule" style={{ left: at(t.percent) }} />
          ))}
          <span className="ptl-now" style={{ left: at(timeline.window.todayPercent) }}>
            <span className="ptl-now-flag">Today</span>
          </span>
        </div>

        {timeline.lanes.map((lane) => (
          <div className="ptl-lane" key={lane.key}>
            <div className="ptl-lane-head">
              <span className={`ptl-mark ptl-mark-${lane.marker}`} aria-hidden="true" />
              <span className="ptl-lane-title">{lane.title}</span>
              <span className="rowmeta">{lane.count}</span>
            </div>
            {/* An ordered list: the markers are in date order in the DOM as well as on the axis,
                so tabbing through a lane walks the launch forwards in time. */}
            <ol className="ptl-track" aria-label={`${lane.title}, ${lane.count} dated`}>
              {lane.clusters.map((c) => {
                const on = pick?.lane === c.lane && pick?.date === c.date;
                return (
                  <li key={`${c.lane}-${c.date}`} style={{ left: at(c.percent) }}>
                    <button
                      type="button"
                      className={[
                        "ptl-mark", `ptl-mark-${lane.marker}`,
                        c.done ? "is-done" : "is-open",
                        c.late ? "is-late" : "", c.atRisk ? "is-risk" : "",
                        on ? "is-picked" : "",
                      ].filter(Boolean).join(" ")}
                      aria-label={clusterLabel(c)}
                      aria-pressed={on}
                      onClick={() => setPick({ lane: c.lane, date: c.date })}
                    />
                    {/* The count, because a marker standing for four rows must say four. */}
                    {c.count > 1 && <span className="ptl-count" aria-hidden="true">{c.count}</span>}
                  </li>
                );
              })}
              {lane.count === 0 && (
                <li className="ptl-lane-none" style={{ left: at(0) }}>
                  <span className="rowmeta">None dated</span>
                </li>
              )}
            </ol>
          </div>
        ))}

        <div className="ptl-axis" aria-hidden="true">
          {ticks.map((t) => (
            <span key={t.date} className="ptl-tick" style={{ left: at(t.percent) }}>
              {tickLabel(t.date)}
            </span>
          ))}
        </div>
      </div>

      {/* One caption region, always present, so selecting a marker does not shift the axis under
          the pointer. Its live region announces the selection for a screen reader that activated a
          marker without following focus into it. */}
      <div className="ptl-caption" aria-live="polite">
        {picked ? (
          <>
            <div className="ptl-caption-head">
              <strong>{longDate(picked.date)}</strong>
              <span className="rowmeta">
                {picked.count} {LANES.find((l) => l.key === picked.lane)?.noun}
                {picked.count === 1 ? "" : "s"}
              </span>
            </div>
            {/* Every member, each in its own vocabulary. This is the disclosure that makes the
                count on the marker honest — a cluster is only allowed to stand for four rows if
                all four are readable from it. */}
            <ul className="ptl-caption-list">
              {picked.points.map((p) => (
                <li key={`${p.lane}-${p.id}`}>
                  <span className="ptl-caption-row">
                    <strong>{p.label}</strong>
                    <span className="rowmeta">{pointStatus(p)}</span>
                    {p.context && <span className="rowmeta">{p.context}</span>}
                  </span>
                  {p.lane === "condition" && onOpenCondition && (
                    <Btn size="small" onClick={() => onOpenCondition(p.row)}>Open condition</Btn>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="rowmeta">Select a marker to see what it stands for.</p>
        )}
      </div>

      {notice && <p className="rowmeta ptl-notice">{notice}</p>}
    </section>
  );
}
