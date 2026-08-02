"""Stage 11.0 — adoption campaigns (ADOPTION-CAMPAIGN-SPEC.md §13 adversarial cases).

The tests that matter guard the §5 measurement contract, because that is the only place a
campaign can render a number that looks like evidence and is not: the baseline series, comparator
disjointness, the regression-to-the-mean caution, retracted baselines, and staleness.
"""
import json
import os
import tempfile
from datetime import date, timedelta

import pytest
from conftest import utc_day
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


# One clock for fixture and code — see tests/conftest.py for why this matters.
def _today():
    return utc_day()


def _d(n):
    return utc_day(n)


@pytest.fixture()
def ctx(client):
    """An account with a cohort, a use case, a metric, and a Valence owner."""
    a = client.post("/api/accounts", json={"name": "Terravance"}).json()
    prog = client.post("/api/programs", json={"account_id": a["id"], "name": "Global"}).json()
    part = client.post("/api/population-partitions", json={
        "account_id": a["id"], "total_fte": 20000}).json()
    dach = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "DACH", "headcount": 6000}).json()
    nordics = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "Nordics", "headcount": 4000}).json()
    uc = client.post("/api/use-cases", json={"name": "Change management", "slug": "cm"}).json()
    owner = client.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()
    sponsor = client.post("/api/persons", json={
        "name": "Dana", "affiliation": "client", "account_id": a["id"]}).json()
    d = client.post("/api/metric-definitions", json={
        "name": "Activation", "stale_after_days": 30}).json()
    src = client.post("/api/source-references", json={"label": "Q2 cohort readout"}).json()
    return {"a": a, "prog": prog, "part": part, "dach": dach, "nordics": nordics,
            "uc": uc, "owner": owner, "sponsor": sponsor, "d": d, "src": src}


def _campaign(client, ctx, **kw):
    body = {"account_id": ctx["a"]["id"], "program_id": ctx["prog"]["id"],
            "use_case_id": ctx["uc"]["id"], "segment_id": ctx["dach"]["id"],
            "name": "DACH change adoption", "target_behavior": "Managers run change conversations",
            "hypothesis": "If we embed the prompt in the review workflow, managers will use it",
            "planned_start_on": _d(-30), "planned_end_on": _d(30), "evaluation_on": _d(45),
            "internal_owner_person_id": ctx["owner"]["id"], **kw}
    r = client.post("/api/campaigns", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _obs(client, ctx, value, days_ago, segment_id=None):
    return client.post("/api/metric-observations", json={
        "definition_id": ctx["d"]["id"], "program_id": ctx["prog"]["id"],
        "population_segment_id": segment_id or ctx["dach"]["id"],
        "value": value, "current_through": _d(-days_ago)}).json()


def _target(client, ctx, campaign, **kw):
    vt = client.post("/api/value-targets", json={
        "account_id": ctx["a"]["id"], "definition_id": ctx["d"]["id"],
        "segment_id": kw.pop("segment_id", ctx["dach"]["id"]),
        "target_value": kw.pop("target_value", 0.70), "timeframe_end": _d(60)}).json()
    body = {"value_target_id": vt["id"], "role": "primary", **kw}
    return client.post(f"/api/campaigns/{campaign['id']}/targets", json=body), vt


# --- cross-account scope ------------------------------------------------------------------------
def test_campaign_population_must_belong_to_the_account(client, ctx):
    other = client.post("/api/accounts", json={"name": "Globex"}).json()
    op = client.post("/api/population-partitions", json={
        "account_id": other["id"], "total_fte": 5000}).json()
    oseg = client.post("/api/population-segments", json={
        "partition_id": op["id"], "name": "Theirs", "headcount": 900}).json()
    r = client.post("/api/campaigns", json={
        "account_id": ctx["a"]["id"], "program_id": ctx["prog"]["id"],
        "use_case_id": ctx["uc"]["id"], "segment_id": oseg["id"], "name": "x",
        "target_behavior": "b", "hypothesis": "h", "planned_start_on": _d(0),
        "planned_end_on": _d(30), "internal_owner_person_id": ctx["owner"]["id"]})
    assert r.status_code >= 400


def test_internal_owner_must_be_valence(client, ctx):
    r = client.post("/api/campaigns", json={
        "account_id": ctx["a"]["id"], "program_id": ctx["prog"]["id"],
        "use_case_id": ctx["uc"]["id"], "segment_id": ctx["dach"]["id"], "name": "x",
        "target_behavior": "b", "hypothesis": "h", "planned_start_on": _d(0),
        "planned_end_on": _d(30), "internal_owner_person_id": ctx["sponsor"]["id"]})
    assert r.status_code >= 400


def test_target_population_must_match_the_campaign(client, ctx):
    """A target on a different cohort would measure people the campaign never touched."""
    c = _campaign(client, ctx)
    r, _ = _target(client, ctx, c, segment_id=ctx["nordics"]["id"])
    assert r.status_code == 422 and "different population" in r.json()["detail"]


def test_exactly_one_cohort(client, ctx):
    r = client.post("/api/campaigns", json={
        "account_id": ctx["a"]["id"], "program_id": ctx["prog"]["id"],
        "use_case_id": ctx["uc"]["id"], "name": "x", "target_behavior": "b", "hypothesis": "h",
        "planned_start_on": _d(0), "planned_end_on": _d(30),
        "internal_owner_person_id": ctx["owner"]["id"]})
    assert r.status_code == 422           # neither segment nor view


# --- §5.2 comparator disjointness -----------------------------------------------------------------
def test_comparator_cannot_be_the_treated_segment(client, ctx):
    c = _campaign(client, ctx, evaluation_design="comparator")
    r, _ = _target(client, ctx, c, comparator_segment_id=ctx["dach"]["id"])
    assert r.status_code == 422 and "overlaps the treated cohort" in r.json()["detail"]


def test_comparator_view_containing_the_treated_segment_is_rejected(client, ctx):
    """Views overlap segments by construction here, so a 'control' can contain the treated."""
    tag = client.post("/api/audience-tags", json={"name": "Frontline", "slug": "fl"}).json()
    view = client.post("/api/population-views", json={
        "account_id": ctx["a"]["id"], "name": "DACH frontline",
        "segment_ids": [ctx["dach"]["id"]], "tag_ids": [tag["id"]],
        "estimated_headcount": 1200}).json()
    c = _campaign(client, ctx, evaluation_design="comparator")
    r, _ = _target(client, ctx, c, comparator_view_id=view["id"])
    assert r.status_code == 422 and "overlaps the treated cohort" in r.json()["detail"]


def test_a_genuinely_disjoint_comparator_is_accepted(client, ctx):
    c = _campaign(client, ctx, evaluation_design="comparator")
    r, _ = _target(client, ctx, c, comparator_segment_id=ctx["nordics"]["id"])
    assert r.status_code == 201


# --- §5.1 baseline series ---------------------------------------------------------------------------
def _make_ready(client, ctx, campaign, barrier_src=None):
    client.post(f"/api/campaigns/{campaign['id']}/barriers", json={
        "category": "opportunity", "description": "Prompt is not in the review workflow",
        "observed_on": _today(), "confidence": "observed",
        "source_reference_id": barrier_src or ctx["src"]["id"], "is_primary": True})
    task = client.post("/api/tasks", json={
        "program_id": ctx["prog"]["id"], "description": "Embed prompt in review flow"}).json()
    client.post(f"/api/campaigns/{campaign['id']}/plan", json={
        "intervention_kind": "workflow_embed", "task_id": task["id"], "sequence": 1})
    followup = client.post("/api/tasks", json={
        "program_id": ctx["prog"]["id"], "description": "Manager reinforcement note"}).json()
    client.post(f"/api/campaigns/{campaign['id']}/plan", json={
        "intervention_kind": "reinforcement", "task_id": followup["id"],
        "sequence": 2, "is_reinforcement": True})
    client.post(f"/api/campaigns/{campaign['id']}/checkpoints", json={"scheduled_on": _d(15)})
    return task


def test_readiness_locks_the_baseline_series_not_just_a_point(client, ctx):
    """A lone baseline cannot tell "we moved it" from "it was already moving"."""
    for value, ago in ((0.40, 90), (0.45, 60), (0.50, 30), (0.52, 1)):
        _obs(client, ctx, value, ago)
    c = _campaign(client, ctx)
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "not yet secured"})

    r = client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "plan agreed"})
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/campaigns/{c['id']}").json()
    t = detail["targets"][0]
    assert t["baseline_observation_id"] and t["baseline_locked_on"]
    trajectory = t["baseline_trajectory"]
    assert [p["value"] for p in trajectory] == [0.40, 0.45, 0.50]   # the prior series, oldest first


def test_signal_triggered_pre_post_carries_the_regression_caution(client, ctx):
    """Stalled-cohort signals select on a declining reading, so some rebound is expected with no
    intervention at all. The delta must never render alone."""
    from app.db import new_id, now_utc
    conn = client.app.state.conn
    ts = now_utc()
    episode_id = new_id()
    conn.execute(
        "INSERT INTO signal_episodes (id,account_id,kind,condition_key,source_kind,explanation,"
        "opened_at,last_evaluated_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (episode_id, ctx["a"]["id"], "stalled_cohort", "stalled:x", "usage",
         "Cohort stalled 0.55 -> 0.50", ts, ts, ts, ts))
    conn.commit()

    _obs(client, ctx, 0.55, 60)
    _obs(client, ctx, 0.50, 1)
    c = _campaign(client, ctx, evaluation_design="pre_post",
                  created_from_signal_episode_id=episode_id)
    _target(client, ctx, c)
    detail = client.get(f"/api/campaigns/{c['id']}").json()
    kinds = {x["kind"] for x in detail["targets"][0]["evaluation"]["cautions"]}
    assert "regression_to_the_mean" in kinds


def test_a_retracted_baseline_invalidates_the_comparison(client, ctx):
    """Import rollback archives observations; a delta from a withdrawn number is not evidence."""
    baseline = _obs(client, ctx, 0.40, 60)
    c = _campaign(client, ctx, evaluation_design="pre_post")
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    _obs(client, ctx, 0.50, 1)

    conn = client.app.state.conn
    conn.execute("UPDATE metric_observations SET archived=1 WHERE id=?", (baseline["id"],))
    conn.commit()

    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["status"] == "invalidated" and ev["delta"] is None
    assert ev["cautions"][0]["kind"] == "baseline_retracted"


def test_stale_evidence_cannot_read_as_met(client, ctx):
    _obs(client, ctx, 0.95, 400)                       # well past stale_after_days
    c = _campaign(client, ctx)
    _target(client, ctx, c)
    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["status"] == "unknown" and ev["value"] is None


def test_sub_floor_cohort_is_suppressed_not_zeroed(client, ctx):
    tiny = client.post("/api/population-segments", json={
        "partition_id": ctx["part"]["id"], "name": "Lab", "headcount": 8}).json()
    _obs(client, ctx, 0.80, 1, segment_id=tiny["id"])
    c = _campaign(client, ctx, segment_id=tiny["id"])
    _target(client, ctx, c, segment_id=tiny["id"])
    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["status"] == "suppressed" and ev["value"] is None


def test_evaluation_never_claims_causation(client, ctx):
    _obs(client, ctx, 0.40, 60)
    c = _campaign(client, ctx, evaluation_design="pre_post")
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    _obs(client, ctx, 0.80, 1)          # post observation arrives after the baseline is locked
    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["delta"] == pytest.approx(0.40)
    assert "does not assert" in ev["interpretation_note"]


# --- §2.3 readiness and lifecycle -----------------------------------------------------------------
def test_a_messaging_reference_alone_is_not_an_intervention(client, ctx):
    """Otherwise an activity list masquerades as a campaign."""
    c = _campaign(client, ctx)
    _target(client, ctx, c)
    entry = client.post("/api/messaging-library", json={
        "layer": "operational", "value_prop": "Managers save time"}).json()
    client.post(f"/api/campaigns/{c['id']}/barriers", json={
        "category": "motivation", "description": "No perceived relevance",
        "observed_on": _today(), "source_reference_id": ctx["src"]["id"]})
    client.post(f"/api/campaigns/{c['id']}/plan", json={
        "intervention_kind": "communication", "messaging_entry_id": entry["id"]})
    blocking = client.get(f"/api/campaigns/{c['id']}/readiness").json()["blocking"]
    assert any("actionable linked intervention" in b for b in blocking)


def test_status_moves_only_through_reason_logged_transitions(client, ctx):
    _obs(client, ctx, 0.50, 1)
    c = _campaign(client, ctx)
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})

    # No generic status patch exists — the field is simply not in the patch model.
    client.patch(f"/api/campaigns/{c['id']}", json={"status": "active"})
    assert client.get(f"/api/campaigns/{c['id']}").json()["status"] == "draft"

    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "plan agreed"})
    client.post(f"/api/campaigns/{c['id']}/activate", json={"reason": "kickoff held"})
    assert client.post(f"/api/campaigns/{c['id']}/pause",
                       json={"reason": "x"}).status_code == 422      # needs pause detail
    ok = client.post(f"/api/campaigns/{c['id']}/pause", json={
        "reason": "sponsor on leave", "pause_reason": "sponsor on leave",
        "resume_condition": "sponsor returns 15th"})
    assert ok.status_code == 200 and ok.json()["status"] == "paused"

    history = client.get(f"/api/campaigns/{c['id']}").json()["history"]
    assert [h["to_status"] for h in history][:3] == ["paused", "active", "ready"]
    assert all(h["reason"] for h in history)


def test_state_history_is_append_only(client, ctx):
    c = _campaign(client, ctx)
    conn = client.app.state.conn
    conn.execute(
        "INSERT INTO adoption_campaign_state_history "
        "(id,campaign_id,from_status,to_status,reason,changed_on,created_at) "
        "VALUES ('h1',?,'draft','ready','x',?,?)", (c["id"], _today(), _today()))
    conn.commit()
    import sqlite3
    for stmt in ("UPDATE adoption_campaign_state_history SET reason='y' WHERE id='h1'",
                 "DELETE FROM adoption_campaign_state_history WHERE id='h1'"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(stmt)


def test_concurrent_campaigns_on_one_cohort_need_a_stated_reason(client, ctx):
    _obs(client, ctx, 0.50, 1)
    first = _campaign(client, ctx, name="First")
    _target(client, ctx, first)
    _make_ready(client, ctx, first)
    client.patch(f"/api/campaigns/{first['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{first['id']}/ready", json={"reason": "go"})

    second = _campaign(client, ctx, name="Second")
    _target(client, ctx, second)
    _make_ready(client, ctx, second)
    client.patch(f"/api/campaigns/{second['id']}", json={"sponsor_gap_reason": "n/a"})
    blocked = client.post(f"/api/campaigns/{second['id']}/ready", json={"reason": "go"})
    assert blocked.status_code == 422 and "another active campaign" in blocked.json()["detail"]

    client.patch(f"/api/campaigns/{second['id']}", json={
        "concurrent_intervention_reason": "different barrier; evaluations are confounded"})
    assert client.post(f"/api/campaigns/{second['id']}/ready",
                       json={"reason": "go"}).status_code == 200


def test_a_cohort_already_at_target_must_say_which_campaign_this_is(client, ctx):
    """The app does not manufacture lift from a cohort that began above its goal."""
    _obs(client, ctx, 0.90, 1)
    c = _campaign(client, ctx)
    _target(client, ctx, c, target_value=0.70)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    r = client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    assert r.status_code == 422 and "already meets this target" in r.json()["detail"]

    client.patch(f"/api/campaigns/{c['id']}", json={
        "already_met_reason": "sustain campaign; the bar is maintenance not increase"})
    assert client.post(f"/api/campaigns/{c['id']}/ready",
                       json={"reason": "go"}).status_code == 200


# --- §4.1 the plan mirrors the ledger, never duplicates it -------------------------------------
def test_plan_readout_follows_the_linked_record(client, ctx):
    """Completion derives from the linked task, so the campaign cannot disagree with the Plan."""
    c = _campaign(client, ctx)
    task = _make_ready(client, ctx, c)
    before = client.get(f"/api/campaigns/{c['id']}").json()["plan"]
    embed = next(p for p in before if p["linked_id"] == task["id"])
    assert embed["linked_status"] == "open" and embed["linked_label"]

    campaign_before = client.get(f"/api/campaigns/{c['id']}").json()["updated_at"]
    client.post(f"/api/tasks/{task['id']}/close", json={"close_note": "shipped"})
    after = client.get(f"/api/campaigns/{c['id']}").json()
    assert next(p for p in after["plan"] if p["linked_id"] == task["id"])["linked_status"] == "done"
    # The campaign row itself was never written — the plan readout is derived, so the campaign
    # cannot drift out of agreement with the Ledger.
    assert after["updated_at"] == campaign_before


def test_a_plan_item_links_exactly_one_record(client, ctx):
    c = _campaign(client, ctx)
    task = client.post("/api/tasks", json={
        "program_id": ctx["prog"]["id"], "description": "t"}).json()
    ms = client.post("/api/milestones", json={
        "program_id": ctx["prog"]["id"], "name": "m"}).json()
    assert client.post(f"/api/campaigns/{c['id']}/plan", json={
        "intervention_kind": "enablement"}).status_code == 422
    assert client.post(f"/api/campaigns/{c['id']}/plan", json={
        "intervention_kind": "enablement", "task_id": task["id"],
        "milestone_id": ms["id"]}).status_code == 422


def test_plan_link_cannot_reference_another_accounts_record(client, ctx):
    other = client.post("/api/accounts", json={"name": "Globex"}).json()
    oprog = client.post("/api/programs", json={
        "account_id": other["id"], "name": "P"}).json()
    otask = client.post("/api/tasks", json={
        "program_id": oprog["id"], "description": "theirs"}).json()
    c = _campaign(client, ctx)
    r = client.post(f"/api/campaigns/{c['id']}/plan", json={
        "intervention_kind": "enablement", "task_id": otask["id"]})
    assert r.status_code == 422 and "different account" in r.json()["detail"]


def test_barrier_requires_a_dated_source(client, ctx):
    c = _campaign(client, ctx)
    r = client.post(f"/api/campaigns/{c['id']}/barriers", json={
        "category": "unknown", "description": "not sure yet", "observed_on": _today()})
    assert r.status_code == 422        # even uncertainty carries a source


def test_completed_campaign_is_immutable(client, ctx):
    _obs(client, ctx, 0.50, 1)
    c = _campaign(client, ctx)
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    client.post(f"/api/campaigns/{c['id']}/activate", json={"reason": "started"})
    done = client.post(f"/api/campaigns/{c['id']}/complete", json={
        "reason": "window closed", "completion_outcome": "improved_not_met",
        "completion_reviewed_on": _today()})
    assert done.status_code == 200
    assert client.patch(f"/api/campaigns/{c['id']}",
                        json={"name": "renamed"}).status_code == 422


# --- §11.3 integration is first-slice work, not cleanup ------------------------------------------
def test_campaign_is_findable_and_survives_export_restore(client, ctx):
    c = _campaign(client, ctx, name="Zephyr manager adoption")
    client.post(f"/api/campaigns/{c['id']}/barriers", json={
        "category": "capability", "description": "Managers never saw a worked example",
        "observed_on": _today(), "source_reference_id": ctx["src"]["id"]})
    client.post("/api/search/reindex")

    hits = client.get("/api/search?q=Zephyr").json()["results"]
    assert any(h["object_type"] == "adoption_campaign" for h in hits)
    hits = client.get("/api/search?q=worked example").json()["results"]
    assert any(h["object_type"] == "adoption_campaign_barrier" for h in hits)

    bundle = client.get(f"/api/accounts/{ctx['a']['id']}/export").json()
    for tbl in ("adoption_campaigns", "adoption_campaign_barriers"):
        assert bundle["counts"].get(tbl), f"{tbl} missing from the export bundle"


def test_trigger_violations_surface_as_client_errors_not_500s(client, ctx):
    """A trigger already wrote a readable sentence; a bare 500 throws it away."""
    other = client.post("/api/accounts", json={"name": "Globex"}).json()
    op = client.post("/api/population-partitions", json={
        "account_id": other["id"], "total_fte": 900}).json()
    oseg = client.post("/api/population-segments", json={
        "partition_id": op["id"], "name": "Theirs", "headcount": 500}).json()
    r = client.post("/api/campaigns", json={
        "account_id": ctx["a"]["id"], "program_id": ctx["prog"]["id"],
        "use_case_id": ctx["uc"]["id"], "segment_id": oseg["id"], "name": "x",
        "target_behavior": "b", "hypothesis": "h", "planned_start_on": _d(0),
        "planned_end_on": _d(30), "internal_owner_person_id": ctx["owner"]["id"]})
    assert r.status_code == 422
    assert "different account" in r.json()["detail"]


# --- measurement window: a finished campaign is judged at its window, not at "now" ---------------
def test_completed_campaign_ignores_observations_after_its_window(client, ctx):
    """Taking the newest observation forever would let movement months after the campaign ended
    flow into its delta, silently re-attributing later change to an intervention that stopped."""
    _obs(client, ctx, 0.30, 120)
    c = _campaign(client, ctx, evaluation_design="pre_post")
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    client.post(f"/api/campaigns/{c['id']}/activate", json={"reason": "started"})
    _obs(client, ctx, 0.45, 40)                       # inside the window
    client.post(f"/api/campaigns/{c['id']}/complete", json={
        "reason": "window closed", "completion_outcome": "improved_not_met",
        "completion_reviewed_on": _d(-35)})

    # Unrelated later movement, well after the campaign ended.
    client.post("/api/metric-observations", json={
        "definition_id": ctx["d"]["id"], "program_id": ctx["prog"]["id"],
        "population_segment_id": ctx["dach"]["id"], "value": 0.95,
        "current_through": _today()})

    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["value"] == 0.45          # not 0.95
    assert ev["delta"] == pytest.approx(0.15)


def test_a_finished_campaign_does_not_decay_into_unknown(client, ctx):
    """Freshness answers "is this on track *now*". A closed campaign's evidence was fresh when the
    outcome was recorded; judging it against today would turn every historical result into
    unknown as it aged, which is decay rather than honesty."""
    _obs(client, ctx, 0.30, 300)
    c = _campaign(client, ctx, planned_start_on=_d(-300), planned_end_on=_d(-200),
                  evaluation_on=_d(-190), evaluation_design="pre_post")
    _target(client, ctx, c)
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    client.post(f"/api/campaigns/{c['id']}/activate", json={"reason": "started"})
    _obs(client, ctx, 0.50, 210)                      # fresh at the time, ancient today
    client.post(f"/api/campaigns/{c['id']}/complete", json={
        "reason": "closed", "completion_outcome": "improved_not_met",
        "completion_reviewed_on": _d(-190)})

    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["status"] != "unknown" and ev["value"] == 0.50


def test_comparator_window_starts_at_the_treated_baseline(client, ctx):
    """A baseline is routinely locked just before the campaign opens; anchoring the comparator on
    planned_start_on silently drops its matching pre-reading and reports no evidence."""
    _obs(client, ctx, 0.30, 40)                                    # treated baseline, pre-start
    _obs(client, ctx, 0.55, 5, segment_id=ctx["nordics"]["id"])    # comparator post
    client.post("/api/metric-observations", json={                 # comparator pre, pre-start
        "definition_id": ctx["d"]["id"], "program_id": ctx["prog"]["id"],
        "population_segment_id": ctx["nordics"]["id"], "value": 0.50,
        "current_through": _d(-40)})
    c = _campaign(client, ctx, planned_start_on=_d(-30), evaluation_design="comparator")
    _target(client, ctx, c, comparator_segment_id=ctx["nordics"]["id"])
    _make_ready(client, ctx, c)
    client.patch(f"/api/campaigns/{c['id']}", json={"sponsor_gap_reason": "n/a"})
    client.post(f"/api/campaigns/{c['id']}/ready", json={"reason": "go"})
    _obs(client, ctx, 0.60, 2)

    ev = client.get(f"/api/campaigns/{c['id']}").json()["targets"][0]["evaluation"]
    assert ev["comparator"]["delta"] == pytest.approx(0.05)    # 0.50 -> 0.55, not "no evidence"
    assert "not causation" in ev["comparator"]["note"]
