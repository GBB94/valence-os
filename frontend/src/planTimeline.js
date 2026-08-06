/**
 * The Plan timeline: the merged launch standard laid out against a shared time axis.
 *
 * Zach asked for a paint-by-numbers view of an account — "we have had the onboarding call, what
 * next?" — and for the timeline that always exists behind that question to be the primary thing on
 * the Plan tab. This module computes the geometry and nothing else; `views/PlanTimeline.jsx` draws
 * what it returns.
 *
 * What the research settled, and why each rule survived contact with this codebase:
 *
 * - **Swim lanes against one axis, not one merged stream.** The launch is 23 dated things of three
 *   different kinds, and the whole point of migration 0051 was that those kinds answer different
 *   questions. Lanes keep them legible together without implying they share a vocabulary — the
 *   "hybrid" variant in the UX Patterns anatomy, chronology plus accountability.
 * - **Shape codes the kind, never colour.** Setup steps, conditions and deployment events get
 *   distinct marker shapes, and every marker also carries its kind in its accessible label. That is
 *   the CLAUDE.md rule ("no state is conveyed by colour alone") and the accessibility guidance
 *   arriving at the same place from different directions.
 * - **A today marker that is not merely a coloured line.** It is labelled, and its position is
 *   returned here so the view cannot place it by eye.
 * - **Density is a decision, not an accident.** The window is bounded and the rows outside it are
 *   *counted and reported* rather than silently dropped — the same rule the coverage notice follows
 *   (D-160): a subtractive view is always stated.
 *
 * What this module deliberately does not do:
 *
 * - It computes **no state**. A milestone's status and a gate item's tick are read verbatim; a
 *   requirement's four readiness axes are passed through untouched. A timeline that decided a
 *   requirement was "on track" would be the stored second source of truth by another route.
 * - It does **not re-rank**. Ordering within a lane is by date, which is arithmetic; where two
 *   items share a date the server's order is preserved.
 * - It does **not invent a duration**. Every one of the 23 things is a point in time, so this draws
 *   points. A bar spanning from "now" to a due date would assert a start nobody recorded.
 */

const MS_PER_DAY = 86400000;

/** Parse an ISO date as UTC midnight, so a local timezone cannot shift a due date by a day. */
function utcDay(iso) {
  if (typeof iso !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function isoOf(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * The three lanes, in the order they read down the page.
 *
 * Setup steps first because they are the ones an operator can act on with a tick today; conditions
 * next because they are what the setup is for; deployment events last because they are the outcome
 * the other two lanes are working towards. `marker` is the shape, and it is the only thing that
 * distinguishes a lane visually apart from its label — no lane has a colour of its own.
 */
export const LANES = [
  {
    key: "setup",
    title: "Setup steps",
    noun: "setup step",
    marker: "square",
    blurb: "Operational work somebody does, ticked when done.",
  },
  {
    key: "condition",
    title: "Conditions",
    noun: "condition",
    marker: "circle",
    blurb: "Relationship conditions readiness assesses from evidence. No tick can satisfy one.",
  },
  {
    key: "milestone",
    title: "Deployment events",
    noun: "deployment event",
    marker: "diamond",
    blurb: "Dated events in the rollout itself.",
  },
];

const LANE_KEYS = LANES.map((l) => l.key);

/**
 * Flatten the plan payload into dated points, one per thing, tagged with its lane.
 *
 * Undated rows are dropped *here* and counted by the caller. A timeline cannot place a row with no
 * date, and putting it at an arbitrary position would be the timeline asserting a date the plan
 * explicitly does not state (`planSetup.js` has a whole stage for that case).
 */
export function timelinePoints(payload) {
  const points = [];
  const undated = { setup: 0, condition: 0, milestone: 0 };

  for (const r of payload?.setup_items || []) {
    if (!r.due_date) { undated.setup += 1; continue; }
    points.push({
      lane: "setup", id: r.gate_item_id, date: r.due_date, label: r.description,
      // A gate item's only settled signal is its own tick or a settled gate — it has no state.
      done: !!r.complete || r.gate_status === "passed" || r.gate_status === "waived",
      context: r.gate_name, row: r,
    });
  }
  for (const r of payload?.requirements || []) {
    if (!r.due_date) { undated.condition += 1; continue; }
    points.push({
      lane: "condition", id: r.instance_id, date: r.due_date, label: r.label || r.requirement_key,
      done: r.state === "met" || !!r.recorded_complete || !!r.waiver || !!r.applicability_override,
      // Passed through, never recomputed. The view renders readiness' own words.
      state: r.state ?? null, freshness: r.freshness ?? null, context: r.pillar_label || null,
      row: r,
    });
  }
  for (const r of payload?.milestones || []) {
    if (!r.target_date) { undated.milestone += 1; continue; }
    points.push({
      lane: "milestone", id: r.milestone_id, date: r.target_date, label: r.name,
      done: !!r.complete, atRisk: !!r.at_risk, context: r.program_name, row: r,
    });
  }
  return { points, undated };
}

/**
 * The axis window, and what it leaves out.
 *
 * The window is the span the dated points actually occupy, padded to today so an account whose work
 * is all in the past or all in the future still shows where it stands. `pastDays`/`futureDays` bound
 * it; anything outside is reported in `clipped` rather than dropped quietly, because a view that
 * silently narrows reads as a complete picture (D-160).
 */
export function axisWindow(points, today, { pastDays = 45, futureDays = 120 } = {}) {
  const now = utcDay(today);
  if (now === null) return null;
  const dates = points.map((p) => utcDay(p.date)).filter((d) => d !== null);

  const earliest = Math.max(now - pastDays * MS_PER_DAY, Math.min(now, ...dates));
  const latest = Math.min(now + futureDays * MS_PER_DAY, Math.max(now, ...dates));
  // A single-day span would divide by zero below; one day either side gives the marker room.
  const start = Math.min(earliest, now - MS_PER_DAY);
  const end = Math.max(latest, now + MS_PER_DAY);

  const before = points.filter((p) => { const d = utcDay(p.date); return d !== null && d < start; });
  const after = points.filter((p) => { const d = utcDay(p.date); return d !== null && d > end; });

  return {
    start: isoOf(start), end: isoOf(end),
    days: Math.round((end - start) / MS_PER_DAY),
    todayPercent: ((now - start) / (end - start)) * 100,
    clipped: { before: before.length, after: after.length, total: before.length + after.length },
  };
}

/** Where a date sits on the axis, 0–100. Returns null for a date outside the window. */
export function positionOf(date, window) {
  const d = utcDay(date), start = utcDay(window?.start), end = utcDay(window?.end);
  if (d === null || start === null || end === null || end === start) return null;
  if (d < start || d > end) return null;
  return ((d - start) / (end - start)) * 100;
}

/**
 * Month ticks across the window, for the time labels the anatomy requires.
 *
 * Months rather than a fixed number of divisions: a launch is discussed in months, and evenly
 * spaced ticks would put labels on dates nobody refers to. A window under two months gets its
 * endpoints instead, because one tick is not an axis.
 */
export function axisTicks(window) {
  const start = utcDay(window?.start), end = utcDay(window?.end);
  if (start === null || end === null || end <= start) return [];
  const ticks = [];
  const d = new Date(start);
  let cursor = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
  while (cursor <= end) {
    ticks.push({ date: isoOf(cursor), percent: ((cursor - start) / (end - start)) * 100 });
    const c = new Date(cursor);
    cursor = Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + 1, 1);
  }
  if (ticks.length < 2) {
    return [{ date: isoOf(start), percent: 0 }, { date: isoOf(end), percent: 100 }];
  }
  return ticks;
}

/**
 * The whole timeline: lanes, their placed points, the axis, and what was left out.
 *
 * Returns `null` when there is nothing dated to draw. The caller shows the reason rather than an
 * empty axis — an axis with no markers looks like a rendering failure, and "no plan has been
 * started here" is a different sentence from "this plan has no dates".
 */
export function planTimeline(payload, today, options) {
  const { points, undated } = timelinePoints(payload);
  if (!points.length) {
    return { empty: true, undated, undatedTotal: Object.values(undated).reduce((a, b) => a + b, 0) };
  }
  const window = axisWindow(points, today, options);
  if (!window) return null;

  // Arithmetic on a date the plan already states, which is the one thing a timeline may work out
  // for itself. It is not a readiness state and never becomes one: an overdue condition whose
  // reading is `thin` still reports `thin`, with "overdue" said alongside it rather than instead.
  const todayIso = isoOf(utcDay(today));

  const lanes = LANES.map((lane) => {
    const placed = points
      .filter((p) => p.lane === lane.key)
      .map((p, index) => ({
        ...p, percent: positionOf(p.date, window), index,
        late: !p.done && p.date < todayIso,
      }))
      .filter((p) => p.percent !== null)
      // By date only. Two items on one date keep the server's order, which `filter` preserves.
      .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.index - b.index));
    return { ...lane, points: placed, count: placed.length, clusters: clusterPoints(placed) };
  });

  const drawn = lanes.reduce((n, l) => n + l.count, 0);
  return {
    empty: false, lanes, window, undated,
    undatedTotal: Object.values(undated).reduce((a, b) => a + b, 0),
    drawn, total: points.length,
  };
}

const LANE_BY_KEY = Object.fromEntries(LANES.map((l) => [l.key, l]));

const words = (v) => String(v).replace(/_/g, " ");

/**
 * The words describing where a point stands, in the vocabulary its own kind uses.
 *
 * Three vocabularies, deliberately not reconciled. A setup step is done or it is not; a condition
 * reports the state and freshness readiness gave it; a milestone reports the status an operator
 * recorded. Flattening these to one scale is the merge that migration 0051 was careful *not* to
 * make, and a timeline is exactly where it would be tempting — the axis is shared, so the status
 * looks like it should be too.
 *
 * Nothing is derived here beyond `late`, which is a date comparison. A condition reading `thin` and
 * overdue says both; it never rounds to "behind".
 */
export function pointStatus(point) {
  const parts = [];
  if (point.lane === "condition") {
    parts.push(point.state ? words(point.state) : "no reading");
    // Freshness is a separate axis, so it is a separate word — but only when it says something.
    // "fresh" and "not applicable" describe an absence of concern and would be noise on a marker.
    if (point.freshness && !["fresh", "not_applicable"].includes(point.freshness)) {
      parts.push(words(point.freshness));
    }
  } else if (point.lane === "milestone") {
    parts.push(words(point.row?.status || (point.done ? "complete" : "upcoming")));
  } else {
    parts.push(point.done ? "done" : "open");
  }
  if (point.atRisk) parts.push("flagged at risk");
  if (point.late) parts.push("overdue");
  return parts.join(", ");
}

/**
 * Group a lane's placed points into one marker per date.
 *
 * Rendering revealed why this is not optional. A launch anchored to a kickoff puts several setup
 * steps on day zero, and drawn one marker per row they land on the same pixel: the lane said seven
 * and showed three. A timeline that hides rows under each other is the same failure as a timeline
 * that drops them silently, and this module's whole density rule is that what is not shown is
 * *stated*. So coincident rows become one marker carrying a count, and the caption discloses the
 * members.
 *
 * Consecutive grouping is exact because the caller has already sorted the lane by date.
 */
export function clusterPoints(points) {
  const out = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (last && last.date === p.date) { last.points.push(p); continue; }
    out.push({ lane: p.lane, date: p.date, percent: p.percent, points: [p] });
  }
  return out.map((c) => ({
    ...c,
    count: c.points.length,
    // Every member settled, or the cluster is not: one open row in a group of four is the reason
    // to look at it, and `some` would let three settled rows hide it.
    done: c.points.every((p) => p.done),
    late: c.points.some((p) => p.late),
    atRisk: c.points.some((p) => p.atRisk),
  }));
}

/**
 * A cluster marker's accessible name.
 *
 * A cluster deliberately does not summarise the states of its members — three readings in three
 * vocabularies do not add up to a fourth, and the caption shows each one in its own words. It does
 * name the counts behind the two hues a cluster can take, because those are the flags that must
 * never be carried by colour alone.
 */
export function clusterLabel(cluster) {
  if (cluster.count === 1) return markerLabel(cluster.points[0]);
  const noun = `${LANE_BY_KEY[cluster.lane]?.noun || "item"}s`;
  const flags = [];
  const late = cluster.points.filter((p) => p.late).length;
  const risk = cluster.points.filter((p) => p.atRisk).length;
  if (late) flags.push(`${late} overdue`);
  if (risk) flags.push(`${risk} flagged at risk`);
  return `${cluster.count} ${noun}, ${cluster.date}${flags.length ? `: ${flags.join(", ")}` : ""}`;
}

/**
 * A marker's accessible name.
 *
 * Built here rather than in the view because it is what keeps the timeline off the wrong side of
 * the colour rule: a marker is a shape and a hue on screen, and this is the text that carries the
 * same information in words. A view that composed its own label could omit the status half.
 */
export function markerLabel(point) {
  const noun = LANE_BY_KEY[point.lane]?.noun || "item";
  return `${point.label} — ${noun}, ${point.date}: ${pointStatus(point)}`;
}

/**
 * The sentence stating what the timeline is not showing, or null when it shows everything.
 *
 * Authored here rather than composed in the view for the same reason a refusal's wording is
 * authored on the server (D-153): a caller that assembles half of a subtractive notice is a caller
 * that can drop the other half. Returns plain prose with no status tone — a withheld row is not a
 * failure, it is a row the axis cannot place.
 */
export function timelineNotice(timeline) {
  if (!timeline || timeline.empty) return null;
  const parts = [];
  const clipped = timeline.window?.clipped?.total || 0;
  if (clipped) {
    parts.push(`${clipped} outside the window shown`);
  }
  if (timeline.undatedTotal) {
    parts.push(`${timeline.undatedTotal} with no date on this plan`);
  }
  if (!parts.length) return null;
  return `Not on the timeline: ${parts.join(", ")}.`;
}

/** Lane keys, exported so a caller can assert it handles every one. */
export const LANE_ORDER = LANE_KEYS;
