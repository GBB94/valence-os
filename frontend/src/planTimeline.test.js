import assert from "node:assert/strict";
import test from "node:test";
import {
  LANES, LANE_ORDER, axisTicks, axisWindow, clusterLabel, markerLabel, planTimeline, pointStatus,
  positionOf, timelineNotice, timelinePoints,
} from "./planTimeline.js";

const TODAY = "2026-08-05";

const setup = (o = {}) => ({
  gate_item_id: o.id || "gi-1", description: o.label || "Trace the IT / legal path",
  due_date: "due_date" in o ? o.due_date : "2026-08-02", complete: o.complete ?? false,
  gate_status: o.gate_status || "open", gate_name: "Foundation gate",
});
const condition = (o = {}) => ({
  instance_id: o.id || "ri-1", label: o.label || "Executive identified",
  requirement_key: "exec_identified",
  due_date: "due_date" in o ? o.due_date : "2026-08-16",
  state: o.state ?? "unknown", freshness: o.freshness ?? "not_applicable",
  pillar_label: "Executive sponsorship",
});
const milestone = (o = {}) => ({
  milestone_id: o.id || "ms-1", name: o.label || "Tech setup",
  target_date: "target_date" in o ? o.target_date : "2026-08-16",
  status: o.status || "upcoming", complete: o.status === "complete", at_risk: o.at_risk ?? false,
  program_name: "Manager Enablement Foundation",
});

const payload = (o = {}) => ({
  setup_items: o.setup_items || [setup()],
  requirements: o.requirements || [condition()],
  milestones: o.milestones || [milestone()],
});

// --- lanes -----------------------------------------------------------------

test("every lane is distinguished by a shape, and no lane owns a colour", () => {
  const markers = LANES.map((l) => l.marker);
  assert.equal(new Set(markers).size, LANES.length);
  for (const lane of LANES) {
    assert.ok(lane.title && lane.marker);
    assert.equal("color" in lane, false, "a lane that carried a colour would encode kind by hue");
  }
});

test("the three lanes are the three kinds the merged standard is made of", () => {
  assert.deepEqual(LANE_ORDER, ["setup", "condition", "milestone"]);
});

// --- points ----------------------------------------------------------------

test("each kind lands in its own lane", () => {
  const { points } = timelinePoints(payload());
  assert.deepEqual(points.map((p) => p.lane).sort(), ["condition", "milestone", "setup"]);
});

test("an undated row is counted, never placed", () => {
  const { points, undated } = timelinePoints(payload({
    setup_items: [setup({ due_date: null })],
    requirements: [condition({ due_date: null }), condition({ id: "ri-2" })],
    milestones: [milestone({ target_date: null })],
  }));
  assert.equal(points.length, 1);
  assert.deepEqual(undated, { setup: 1, condition: 1, milestone: 1 });
});

test("a setup step is settled by its own tick or a settled gate, and by nothing else", () => {
  const rows = [
    setup({ id: "a", complete: true }),
    setup({ id: "b", gate_status: "waived" }),
    setup({ id: "c" }),
  ];
  const { points } = timelinePoints({ setup_items: rows });
  assert.deepEqual(points.map((p) => [p.id, p.done]), [["a", true], ["b", true], ["c", false]]);
});

test("a condition's readiness axes are passed through, never recomputed", () => {
  const { points } = timelinePoints({
    requirements: [condition({ state: "thin", freshness: "stale" })],
  });
  assert.equal(points[0].state, "thin");
  assert.equal(points[0].freshness, "stale");
  // The timeline must not upgrade a thin reading to a done marker just because a date has passed.
  assert.equal(points[0].done, false);
});

test("a milestone's at-risk flag travels as the operator's flag and produces no state", () => {
  const { points } = timelinePoints({ milestones: [milestone({ at_risk: true })] });
  assert.equal(points[0].atRisk, true);
  assert.equal(points[0].state, undefined, "a milestone has no readiness state to report");
});

// --- axis ------------------------------------------------------------------

test("the window always contains today, even when every dated thing is in the past", () => {
  // Inside the past bound: the axis stretches back to reach it.
  const near = timelinePoints({ milestones: [milestone({ target_date: "2026-07-10" })] }).points;
  const w = axisWindow(near, TODAY);
  assert.ok(w.start <= "2026-07-10");
  assert.ok(w.end >= TODAY);
  assert.ok(w.todayPercent > 0 && w.todayPercent <= 100);

  // Outside it: the axis does *not* stretch — it stays bounded and reports what fell out. An
  // unbounded axis would let one abandoned 2024 milestone squeeze this quarter into a few pixels.
  const far = timelinePoints({ milestones: [milestone({ target_date: "2025-01-01" })] }).points;
  const bounded = axisWindow(far, TODAY);
  assert.ok(bounded.start > "2025-01-01");
  assert.equal(bounded.clipped.before, 1);
  assert.ok(bounded.todayPercent > 0 && bounded.todayPercent <= 100);
});

test("today's position is computed here, so no view can place the marker by eye", () => {
  const pts = timelinePoints({
    milestones: [milestone({ target_date: "2026-08-04" }), milestone({ id: "m2", target_date: "2026-08-06" })],
  }).points;
  const w = axisWindow(pts, TODAY);
  assert.ok(Math.abs(w.todayPercent - 50) < 1, `expected mid-axis, got ${w.todayPercent}`);
});

test("a row outside the bounded window is counted as clipped, not dropped quietly", () => {
  const pts = timelinePoints({
    milestones: [milestone({ target_date: "2027-06-01" }), milestone({ id: "m2", target_date: "2025-01-01" })],
  }).points;
  const w = axisWindow(pts, TODAY, { pastDays: 30, futureDays: 60 });
  assert.equal(w.clipped.total, 2);
  assert.equal(w.clipped.before, 1);
  assert.equal(w.clipped.after, 1);
});

test("a date outside the window has no position rather than a clamped one", () => {
  const w = { start: "2026-08-01", end: "2026-08-31" };
  assert.equal(positionOf("2026-07-01", w), null);
  assert.equal(positionOf("2026-10-01", w), null);
  assert.equal(positionOf("2026-08-16", w), 50);
  assert.equal(positionOf("2026-08-01", w), 0);
  assert.equal(positionOf("2026-08-31", w), 100);
});

test("ticks fall on month boundaries, and a short window still gets two labels", () => {
  const long = axisTicks({ start: "2026-07-15", end: "2026-11-20" });
  assert.deepEqual(long.map((t) => t.date), ["2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01"]);
  const short = axisTicks({ start: "2026-08-01", end: "2026-08-20" });
  assert.equal(short.length, 2);
});

// --- the whole timeline ----------------------------------------------------

test("points are ordered by date within a lane", () => {
  const t = planTimeline(payload({
    milestones: [
      milestone({ id: "late", target_date: "2026-10-01" }),
      milestone({ id: "early", target_date: "2026-08-10" }),
    ],
  }), TODAY);
  const lane = t.lanes.find((l) => l.key === "milestone");
  assert.deepEqual(lane.points.map((p) => p.id), ["early", "late"]);
});

test("nothing dated returns the empty shape rather than an axis with no markers", () => {
  const t = planTimeline({ setup_items: [setup({ due_date: null })] }, TODAY);
  assert.equal(t.empty, true);
  assert.equal(t.undatedTotal, 1);
  assert.equal(t.lanes, undefined);
});

test("an empty lane is still returned, so a missing kind reads as absent rather than unbuilt", () => {
  const t = planTimeline({ requirements: [condition()] }, TODAY);
  assert.equal(t.lanes.length, 3);
  assert.equal(t.lanes.find((l) => l.key === "setup").count, 0);
});

// --- status words ----------------------------------------------------------

const laneOf = (t, key) => t.lanes.find((l) => l.key === key).points;

test("a past date with nothing recorded is late; a past date already settled is not", () => {
  const t = planTimeline(payload({
    setup_items: [setup({ id: "a", due_date: "2026-07-01" }),
                  setup({ id: "b", due_date: "2026-07-01", complete: true })],
    requirements: [], milestones: [],
  }), TODAY);
  assert.deepEqual(laneOf(t, "setup").map((p) => [p.id, p.late]), [["a", true], ["b", false]]);
});

test("an overdue condition reports its own reading and says overdue beside it, never instead", () => {
  const t = planTimeline({
    requirements: [condition({ due_date: "2026-07-01", state: "thin", freshness: "stale" })],
  }, TODAY);
  const status = pointStatus(laneOf(t, "condition")[0]);
  assert.match(status, /thin/);
  assert.match(status, /stale/);
  assert.match(status, /overdue/);
});

test("a fresh reading spends no words on its freshness", () => {
  const { points } = timelinePoints({ requirements: [condition({ state: "met", freshness: "fresh" })] });
  assert.equal(pointStatus({ ...points[0], late: false }), "met");
});

test("each kind reports in its own vocabulary, not one shared scale", () => {
  const s = pointStatus({ lane: "setup", done: true });
  const c = pointStatus({ lane: "condition", state: "insufficient_data" });
  const m = pointStatus({ lane: "milestone", row: { status: "in_progress" }, atRisk: true });
  assert.equal(s, "done");
  assert.equal(c, "insufficient data");
  assert.equal(m, "in progress, flagged at risk");
});

test("every marker's accessible name carries its status in words, so no marker is colour alone", () => {
  const t = planTimeline(payload({
    setup_items: [setup({ due_date: "2026-07-01" })],
    milestones: [milestone({ at_risk: true })],
  }), TODAY);
  for (const lane of t.lanes) {
    for (const p of lane.points) {
      const label = markerLabel(p);
      assert.ok(label.includes(p.label), "the name should identify the row");
      assert.ok(label.includes(p.date), "the name should state the date the marker encodes");
      assert.ok(label.endsWith(pointStatus(p)), `status missing from "${label}"`);
    }
  }
  const late = markerLabel(laneOf(t, "setup")[0]);
  assert.match(late, /overdue/);
  assert.match(markerLabel(laneOf(t, "milestone")[0]), /at risk/);
});

// --- clustering ------------------------------------------------------------

test("rows sharing a date become one marker carrying a count, never markers on top of each other", () => {
  const t = planTimeline({
    setup_items: [
      setup({ id: "a", due_date: "2026-08-02" }),
      setup({ id: "b", due_date: "2026-08-02" }),
      setup({ id: "c", due_date: "2026-09-10" }),
    ],
  }, TODAY);
  const lane = t.lanes.find((l) => l.key === "setup");
  assert.equal(lane.count, 3, "every row is still placed");
  assert.deepEqual(lane.clusters.map((c) => c.count), [2, 1]);
  // Nothing is lost: the members are reachable from the cluster.
  assert.deepEqual(lane.clusters.flatMap((c) => c.points.map((p) => p.id)), ["a", "b", "c"]);
});

test("one unsettled row keeps its cluster unsettled, so three ticks cannot hide it", () => {
  const t = planTimeline({
    setup_items: [
      setup({ id: "a", complete: true }), setup({ id: "b", complete: true }), setup({ id: "c" }),
    ],
  }, TODAY);
  const [cluster] = t.lanes.find((l) => l.key === "setup").clusters;
  assert.equal(cluster.count, 3);
  assert.equal(cluster.done, false);
});

test("a cluster names the counts behind its hues and summarises no state", () => {
  const t = planTimeline({
    setup_items: [setup({ id: "a", due_date: "2026-07-01" }),
                  setup({ id: "b", due_date: "2026-07-01", complete: true })],
  }, TODAY);
  const [cluster] = t.lanes.find((l) => l.key === "setup").clusters;
  const label = clusterLabel(cluster);
  assert.match(label, /2 setup steps/);
  assert.match(label, /1 overdue/);
  assert.equal(cluster.late, true);
});

test("a cluster of one is labelled as the row it contains, not as a group", () => {
  const t = planTimeline({ milestones: [milestone({ at_risk: true })] }, TODAY);
  const [cluster] = t.lanes.find((l) => l.key === "milestone").clusters;
  assert.equal(clusterLabel(cluster), markerLabel(cluster.points[0]));
});

// --- the subtractive notice ------------------------------------------------

test("a timeline showing everything says nothing", () => {
  assert.equal(timelineNotice(planTimeline(payload(), TODAY)), null);
});

test("undated and clipped rows are both stated, in one sentence the view cannot half-render", () => {
  const t = planTimeline(payload({
    setup_items: [setup({ due_date: null })],
    milestones: [milestone({ target_date: "2028-01-01" })],
  }), TODAY);
  const notice = timelineNotice(t);
  assert.match(notice, /Not on the timeline:/);
  assert.match(notice, /1 outside the window shown/);
  assert.match(notice, /1 with no date on this plan/);
});

test("the notice is prose with no status word, because a row the axis cannot place is not a failure", () => {
  const t = planTimeline(payload({ setup_items: [setup({ due_date: null })] }), TODAY);
  const notice = timelineNotice(t);
  for (const word of ["error", "failed", "warning", "missing", "incomplete"]) {
    assert.equal(notice.toLowerCase().includes(word), false, `notice should not say "${word}"`);
  }
});
