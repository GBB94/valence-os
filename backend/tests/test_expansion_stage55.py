"""Stage 5.5 — whitespace map, value ledger, funding intelligence
(EXPANSION-ENGINE-SPEC.md §§1, 2, 4, 10).

The tests that matter here are the ones guarding the three ways this module could lie:
the counting rule (§1.1), the derived-state precedence (§1.3), and the cohort privacy
floor (§1.2). Everything else is plumbing.
"""
import os
import tempfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


def _today():
    from app.db import now_utc
    return now_utc()[:10]


def _days(n):
    return (date.fromisoformat(_today()) + timedelta(days=n)).isoformat()


@pytest.fixture()
def account(client):
    """An account with a 20,000-FTE partition, two segments, and one global use case."""
    a = client.post("/api/accounts", json={"name": "Terravance"}).json()
    p = client.post("/api/population-partitions", json={
        "account_id": a["id"], "basis": "business unit x region",
        "total_fte": 20000, "fte_source": "client-stated, kickoff", "fte_as_of": _today()}).json()
    dach = client.post("/api/population-segments", json={
        "partition_id": p["id"], "name": "DACH", "region": "DACH", "headcount": 6000,
        "headcount_source": "client HR summary", "headcount_as_of": _today()}).json()
    nordics = client.post("/api/population-segments", json={
        "partition_id": p["id"], "name": "Nordics", "region": "Nordics", "headcount": 4000,
        "headcount_source": "client HR summary", "headcount_as_of": _today()}).json()
    uc = client.post("/api/use-cases", json={"name": "Performance reviews", "slug": "perf-reviews"}).json()
    uc2 = client.post("/api/use-cases", json={"name": "Change management", "slug": "change-mgmt"}).json()
    return {"account": a, "partition": p, "dach": dach, "nordics": nordics, "uc": uc, "uc2": uc2}


def _cell(client, ctx, segment_id=None, view_id=None, use_case_id=None, **kw):
    body = {"account_id": ctx["account"]["id"], "use_case_id": use_case_id or ctx["uc"]["id"], **kw}
    if segment_id:
        body["segment_id"] = segment_id
    if view_id:
        body["view_id"] = view_id
    r = client.post("/api/whitespace-cells", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- §1.3 derived state ------------------------------------------------------------------------
def test_derived_state_covers_all_seven_states(client, account):
    """The single heatmap state is computed from four stored facts, never written."""
    from app.expansion import derive_state
    base = {"blocker_state": "clear", "pursuit_outcome": "none", "penetration": "none",
            "evidence_state": "none", "sponsor_person_id": None, "reopened_on": None}
    assert derive_state(base) == "white"
    assert derive_state({**base, "sponsor_person_id": "p1"}) == "target"
    assert derive_state({**base, "evidence_state": "anecdotal"}) == "proven"
    assert derive_state({**base, "penetration": "paid", "evidence_state": "measured"}) == "penetrated"
    # The state v1's six-state model could not express, and the reason the ledger exists.
    assert derive_state({**base, "penetration": "paid"}) == "penetrated_unevidenced"
    assert derive_state({**base, "pursuit_outcome": "declined"}) == "declined"
    assert derive_state({**base, "blocker_state": "gated"}) == "blocked"


def test_blocked_and_declined_take_precedence_over_paid(client, account):
    """A cell can be paid, evidenced AND gated. The heatmap shows Blocked, because the next
    action is the compliance lane — but the card still carries all four facts."""
    from app.expansion import derive_state
    paid_evidenced_gated = {"penetration": "paid", "evidence_state": "measured",
                            "blocker_state": "gated", "pursuit_outcome": "none",
                            "sponsor_person_id": None, "reopened_on": None}
    assert derive_state(paid_evidenced_gated) == "blocked"
    assert paid_evidenced_gated["penetration"] == "paid"        # fact not lost


def test_reopened_declined_cell_stops_reading_as_declined(client, account):
    from app.expansion import derive_state
    declined = {"penetration": "none", "evidence_state": "none", "blocker_state": "clear",
                "pursuit_outcome": "declined", "sponsor_person_id": "p1", "reopened_on": None}
    assert derive_state(declined) == "declined"
    assert derive_state({**declined, "reopened_on": _today()}) == "target"


# --- §1.1 the counting rule --------------------------------------------------------------------
def test_row_paid_seats_is_max_across_use_cases_not_sum(client, account):
    """Use cases are entitlements on a seat, not separate inventories. The same 900 managers
    lit for two use cases are 900 seats, not 1,800 — this is the whole counting rule."""
    _cell(client, account, segment_id=account["dach"]["id"], use_case_id=account["uc"]["id"], paid_seats=900)
    _cell(client, account, segment_id=account["dach"]["id"], use_case_id=account["uc2"]["id"], paid_seats=700)
    m = client.get(f"/api/accounts/{account['account']['id']}/whitespace").json()
    dach = next(r for r in m["segment_rows"] if r["name"] == "DACH")
    assert dach["paid_seats"] == 900                          # max, the honest figure
    assert dach["paid_seats_sum_across_use_cases"] == 1600     # exposed, and labeled as not the answer
    assert "not the sum" in dach["paid_seats_note"]


def test_composite_views_are_marked_non_additive_and_excluded_from_rollup(client, account):
    """A composite overlaps its constituent segments, so it can never be an addend."""
    tag = client.post("/api/audience-tags", json={"name": "Frontline managers", "slug": "frontline"}).json()
    view = client.post("/api/population-views", json={
        "account_id": account["account"]["id"], "name": "DACH frontline managers",
        "segment_ids": [account["dach"]["id"]], "tag_ids": [tag["id"]],
        "estimated_headcount": 1200, "headcount_source": "estimate", "headcount_as_of": _today()}).json()
    assert view["additive"] is False
    _cell(client, account, view_id=view["id"], paid_seats=300)
    _cell(client, account, segment_id=account["dach"]["id"], paid_seats=900)

    m = client.get(f"/api/accounts/{account['account']['id']}/whitespace").json()
    assert m["rollup"]["paid_seats"] == 900          # the view's 300 are inside the segment's 900
    assert m["rollup"]["excluded_view_cells"] == 1   # excluded out loud, not silently
    assert m["rollup"]["additive"] is True
    assert any("overlap" in n for n in m["counting_rule"]["non_additive"])


def test_segments_cannot_exceed_account_fte(client, account):
    """The map cannot quietly claim 30,000 addressable seats in a 20,000-person company."""
    r = client.post("/api/population-segments", json={
        "partition_id": account["partition"]["id"], "name": "APAC", "headcount": 12000})
    assert r.status_code == 422
    assert "exceeding" in r.json()["detail"] and "20000" in r.json()["detail"]


def test_unallocated_remainder_makes_the_partition_reconcile(client, account):
    client.post("/api/population-segments", json={
        "partition_id": account["partition"]["id"], "name": "Unallocated",
        "headcount": 10000, "is_unallocated": True})
    m = client.get(f"/api/accounts/{account['account']['id']}/whitespace").json()
    rec = m["reconciliation"]
    assert rec["allocated_headcount"] == 10000 and rec["unallocated_headcount"] == 10000
    assert rec["reconciles"] is True


def test_next_seats_answers_from_the_row_axis(client, account):
    """"Where do the next 2,000 seats live" is a row question; columns supply the motion."""
    _cell(client, account, segment_id=account["dach"]["id"], paid_seats=900,
          use_case_id=account["uc"]["id"])
    c2 = _cell(client, account, segment_id=account["nordics"]["id"], use_case_id=account["uc2"]["id"])
    client.post(f"/api/whitespace-cells/{c2['id']}/set-fact",
                json={"fact": "evidence_state", "value": "measured", "reason": "pilot readout"})
    r = client.get(f"/api/accounts/{account['account']['id']}/whitespace/next-seats").json()
    assert r["additive"] is True
    top = r["rows"][0]
    assert top["segment"] == "DACH" and top["unpenetrated_seats"] == 5100
    nordics = next(x for x in r["rows"] if x["segment"] == "Nordics")
    assert nordics["best_motion"]["state"] == "proven"       # cheapest next move surfaced


def test_a_cell_must_have_exactly_one_row_reference(client, account):
    r = client.post("/api/whitespace-cells", json={
        "account_id": account["account"]["id"], "use_case_id": account["uc"]["id"]})
    assert r.status_code == 422 and "exactly one" in r.json()["detail"]


# --- §1.2 the cohort privacy floor ---------------------------------------------------------------
def test_view_below_cohort_floor_is_refused(client, account):
    """Aggregate stops being non-identifying once a composite narrows far enough."""
    tag = client.post("/api/audience-tags", json={"name": "Exec", "slug": "exec"}).json()
    r = client.post("/api/population-views", json={
        "account_id": account["account"]["id"], "name": "DACH executives",
        "segment_ids": [account["dach"]["id"]], "tag_ids": [tag["id"]], "estimated_headcount": 8})
    assert r.status_code == 422 and "single out" in r.json()["detail"]


def test_paid_density_suppressed_below_floor_not_zeroed(client, account):
    client.put(f"/api/accounts/{account['account']['id']}/settings", json={"min_cohort_size": 25})
    p = client.get(f"/api/accounts/{account['account']['id']}/population-partition").json()
    tiny = client.post("/api/population-segments", json={
        "partition_id": p["id"], "name": "Pilot cell", "headcount": 10}).json()
    _cell(client, account, segment_id=tiny["id"], paid_seats=4)
    m = client.get(f"/api/accounts/{account['account']['id']}/whitespace").json()
    row = next(r for r in m["segment_rows"] if r["name"] == "Pilot cell")
    density = next(c["cell"] for c in row["cells"] if c["cell"])["paid_density"]
    assert density["suppressed"] is True and density["value"] is None   # not 0.0, not rounded
    assert "below 25" in density["reason"]


# --- §1.3 state changes carry reasons ------------------------------------------------------------
def test_setting_a_fact_requires_a_reason_and_writes_history(client, account):
    cell = _cell(client, account, segment_id=account["dach"]["id"])
    assert client.post(f"/api/whitespace-cells/{cell['id']}/set-fact",
                       json={"fact": "penetration", "value": "paid"}).status_code == 422

    r = client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "penetration", "value": "paid", "reason": "3-year deal signed for DACH"}).json()
    assert r["state"] == "penetrated_unevidenced" and r["previous_state"] == "white"

    hist = client.get(f"/api/whitespace-cells/{cell['id']}").json()["history"]
    assert hist[0]["fact"] == "penetration" and hist[0]["before_value"] == "none"
    assert hist[0]["after_value"] == "paid" and "3-year deal" in hist[0]["reason"]


def test_gating_a_cell_requires_a_lane(client, account):
    cell = _cell(client, account, segment_id=account["dach"]["id"])
    r = client.post(f"/api/whitespace-cells/{cell['id']}/set-fact",
                    json={"fact": "blocker_state", "value": "gated", "reason": "blocked"})
    assert r.status_code == 422 and "requires a lane" in r.json()["detail"]

    ok = client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "blocker_state", "value": "gated", "blocker_lane": "works_council",
        "reason": "works council consultation not started"}).json()
    assert ok["state"] == "blocked" and ok["blocker_lane"] == "works_council"


def test_declining_then_reopening_keeps_both_in_history(client, account):
    """The demo's "Declined cell whose reason later changes" is a transition, not an edit."""
    cell = _cell(client, account, segment_id=account["nordics"]["id"])
    client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "pursuit_outcome", "value": "declined", "reason": "no budget this fiscal year"})
    assert client.get(f"/api/whitespace-cells/{cell['id']}").json()["state"] == "declined"

    r = client.post(f"/api/whitespace-cells/{cell['id']}/reopen",
                    json={"reason": "new CHRO reopened the L&D budget"}).json()
    assert r["state"] != "declined"

    hist = client.get(f"/api/whitespace-cells/{cell['id']}").json()["history"]
    reasons = [h["reason"] for h in hist]
    assert any("no budget" in x for x in reasons)          # the original decline survives
    assert any("new CHRO" in x for x in reasons)


def test_only_a_declined_cell_can_be_reopened(client, account):
    cell = _cell(client, account, segment_id=account["dach"]["id"])
    r = client.post(f"/api/whitespace-cells/{cell['id']}/reopen", json={"reason": "x"})
    assert r.status_code == 422


def test_repartitioning_requires_a_reason(client, account):
    """Re-cutting the base re-bases every historical number, so it is an event, not an edit."""
    r = client.post("/api/population-partitions", json={
        "account_id": account["account"]["id"], "basis": "function only", "total_fte": 20000})
    assert r.status_code == 422 and "reason" in r.json()["detail"]

    ok = client.post("/api/population-partitions", json={
        "account_id": account["account"]["id"], "basis": "function only", "total_fte": 20000,
        "reason": "client reorganised into functions"}).json()
    assert ok["version"] == 2 and ok["supersedes_id"] == account["partition"]["id"]


# --- §2 the value ledger ---------------------------------------------------------------------------
def _target(client, account, definition_id, **kw):
    body = {"account_id": account["account"]["id"], "definition_id": definition_id,
            "segment_id": account["dach"]["id"], "target_value": 0.70,
            "timeframe_end": _days(30), **kw}
    return client.post("/api/value-targets", json=body)


def test_accepted_target_requires_who_and_when(client, account):
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    r = _target(client, account, d["id"], client_accepted=True)
    assert r.status_code == 422 and "aspiration" in r.json()["detail"]


def test_realization_uses_population_scoped_observations(client, account):
    """cohort_label is free text and cannot be joined; population_segment_id is what makes the
    ledger computable. An observation for a DIFFERENT segment must not satisfy the target."""
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    prog = client.post("/api/programs", json={"account_id": account["account"]["id"], "name": "P"}).json()
    t = _target(client, account, d["id"]).json()

    client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": prog["id"], "value": 0.95,
        "current_through": _days(-1), "population_segment_id": account["nordics"]["id"]})
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    row = next(r for r in led["targets"] if r["id"] == t["id"])
    assert row["realization"]["status"] == "not_demonstrated"   # Nordics' 0.95 is not DACH's

    client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": prog["id"], "value": 0.82,
        "current_through": _days(-1), "population_segment_id": account["dach"]["id"]})
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    row = next(r for r in led["targets"] if r["id"] == t["id"])
    assert row["realization"]["status"] == "realized" and row["realization"]["value"] == 0.82


def test_stale_observation_renders_unknown_not_realized(client, account):
    """Freshness governs the ledger like everything else: never a carried-forward good state."""
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    prog = client.post("/api/programs", json={"account_id": account["account"]["id"], "name": "P"}).json()
    t = _target(client, account, d["id"]).json()
    client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": prog["id"], "value": 0.99,
        "current_through": _days(-200), "population_segment_id": account["dach"]["id"]})
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    row = next(r for r in led["targets"] if r["id"] == t["id"])
    assert row["realization"]["status"] == "unknown" and row["realization"]["value"] is None


def test_at_most_targets_are_not_compared_backwards(client, account):
    """"Response time under 24h" and "activation above 70%" are both targets."""
    d = client.post("/api/metric-definitions", json={"name": "Response hours", "stale_after_days": 30}).json()
    prog = client.post("/api/programs", json={"account_id": account["account"]["id"], "name": "P"}).json()
    t = _target(client, account, d["id"], target_value=24, direction="at_most").json()
    client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": prog["id"], "value": 12,
        "current_through": _days(-1), "population_segment_id": account["dach"]["id"]})
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    row = next(r for r in led["targets"] if r["id"] == t["id"])
    assert row["realization"]["status"] == "realized"      # 12 <= 24


def test_superseded_target_stays_readable_and_drops_out_of_the_active_ledger(client, account):
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    t = _target(client, account, d["id"]).json()
    v2 = client.post(f"/api/value-targets/{t['id']}/supersede", json={
        "target_value": 0.60, "timeframe_end": _days(90),
        "reason": "renegotiated at the March review"}).json()
    assert v2["version"] == 2 and v2["supersedes_id"] == t["id"]
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    ids = [r["id"] for r in led["targets"]]
    assert v2["id"] in ids and t["id"] not in ids


def test_value_gap_is_the_paid_but_unevidenced_cell(client, account):
    """§2's dangerous state and §1.3's display state 4 are the same condition, computed once."""
    cell = _cell(client, account, segment_id=account["dach"]["id"], paid_seats=900)
    client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "penetration", "value": "paid", "reason": "signed"})
    gaps = client.get(f"/api/accounts/{account['account']['id']}/value-gaps").json()["gaps"]
    assert len(gaps) == 1 and gaps[0]["population"] == "DACH"
    assert "no measured evidence" in gaps[0]["because"]

    client.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
        "fact": "evidence_state", "value": "measured", "reason": "Q2 readout"})
    assert client.get(f"/api/accounts/{account['account']['id']}/value-gaps").json()["gaps"] == []


def test_ledger_reports_counts_not_rates(client, account):
    """At n=5 accounts a percentage implies precision the sample cannot support (§10)."""
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    _target(client, account, d["id"])
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    assert isinstance(led["counts"], dict) and led["total"] == 1
    assert "rate" not in led and "percentage" not in led


# --- §4 funding intelligence -------------------------------------------------------------------------
def test_ask_calendar_back_schedules_the_whole_chain(client, account):
    """An ask that misses the planning window slips a cycle; the dates exist before anyone asks."""
    cal = client.post("/api/ask-calendars", json={
        "account_id": account["account"]["id"], "name": "DACH expansion",
        "target_close_date": _days(180)}).json()
    kinds = [s["kind"] for s in cal["steps"]]
    assert kinds == ["business_case_delivered", "budget_owner_sponsorship", "budget_window",
                     "procurement", "works_council", "signature"]
    assert cal["steps"][0]["due_date"] < cal["steps"][-1]["due_date"]
    assert cal["steps"][-1]["due_date"] == _days(180)


def test_ask_calendar_uses_the_accounts_own_lead_times(client, account):
    """Lead times come from the contract and fiscal map, not a generic default."""
    cv = client.post("/api/contracts", json={
        "account_id": account["account"]["id"], "version_label": "v1",
        "procurement_lead_days": 90}).json()
    client.put(f"/api/accounts/{account['account']['id']}/fiscal-map", json={
        "procurement_lead_contract_id": cv["id"], "works_council_lead_days": 60,
        "confirmed_on": _today()})
    cal = client.post("/api/ask-calendars", json={
        "account_id": account["account"]["id"], "name": "X", "target_close_date": _days(200)}).json()
    proc = next(s for s in cal["steps"] if s["kind"] == "procurement")
    wc = next(s for s in cal["steps"] if s["kind"] == "works_council")
    assert proc["due_date"] == _days(200 - 90)
    assert wc["due_date"] == _days(200 - 60)


def test_late_ask_steps_are_derived_against_today(client, account):
    cal = client.post("/api/ask-calendars", json={
        "account_id": account["account"]["id"], "name": "Late one",
        "target_close_date": _days(10)}).json()
    assert cal["late_steps"] > 0
    funding = client.get(f"/api/accounts/{account['account']['id']}/funding").json()
    assert funding["late_steps_total"] == cal["late_steps"]


def test_works_council_step_can_be_omitted(client, account):
    cal = client.post("/api/ask-calendars", json={
        "account_id": account["account"]["id"], "name": "US only",
        "target_close_date": _days(180), "include_works_council": False}).json()
    assert "works_council" not in [s["kind"] for s in cal["steps"]]


def test_invalid_ask_reference_does_not_leave_a_partial_calendar(client, account):
    aid = account["account"]["id"]
    before = len(client.get(f"/api/accounts/{aid}/funding").json()["ask_calendars"])
    r = client.post("/api/ask-calendars", json={
        "account_id": aid, "name": "Must not persist", "target_close_date": _days(180),
        "opportunity_id": "does-not-exist"})
    assert r.status_code == 404
    after = len(client.get(f"/api/accounts/{aid}/funding").json()["ask_calendars"])
    assert after == before


def test_funding_pool_links_to_the_stakeholder_who_controls_it(client, account):
    person = client.post("/api/persons", json={
        "name": "CHRO", "affiliation": "client", "account_id": account["account"]["id"]}).json()
    client.post("/api/funding-pools", json={
        "account_id": account["account"]["id"], "name": "CHRO discretionary",
        "kind": "chro_discretionary", "owner_person_id": person["id"],
        "status": "confirmed", "amount": 250000, "currency": "EUR"})
    f = client.get(f"/api/accounts/{account['account']['id']}/funding").json()
    assert f["funding_pools"][0]["owner_name"] == "CHRO"


# --- §10 revenue semantics ------------------------------------------------------------------------
def test_arr_is_derived_once_from_the_stated_basis(client, account):
    """Deriving ARR at each call site is how two screens quietly disagree about revenue."""
    cv = client.post("/api/contracts", json={
        "account_id": account["account"]["id"], "version_label": "v1", "price": 1200000}).json()
    r = client.patch(f"/api/contracts/{cv['id']}/revenue", json={
        "currency": "EUR", "price_basis": "tcv", "term_months": 36}).json()
    assert r["derived_arr"] == 400000.0 and r["currency"] == "EUR"

    cv2 = client.post("/api/contracts", json={
        "account_id": account["account"]["id"], "version_label": "v2", "price": 30000}).json()
    r2 = client.patch(f"/api/contracts/{cv2['id']}/revenue", json={
        "currency": "EUR", "price_basis": "monthly"}).json()
    assert r2["derived_arr"] == 360000.0


def test_one_time_price_contributes_no_recurring_revenue(client, account):
    cv = client.post("/api/contracts", json={
        "account_id": account["account"]["id"], "version_label": "v1", "price": 50000}).json()
    r = client.patch(f"/api/contracts/{cv['id']}/revenue", json={
        "currency": "EUR", "price_basis": "one_time"}).json()
    assert r["derived_arr"] is None      # guessing otherwise would inflate NRR


def test_revenue_movement_reports_absolutes_with_its_base(client, account):
    """Not a blended rate: one account is not a population (§10)."""
    cv = client.post("/api/contracts", json={
        "account_id": account["account"]["id"], "version_label": "v1", "price": 500000}).json()
    client.patch(f"/api/contracts/{cv['id']}/revenue", json={"currency": "EUR", "price_basis": "arr"})
    client.post("/api/revenue-events", json={
        "account_id": account["account"]["id"], "kind": "expansion", "amount": 120000,
        "currency": "EUR", "effective_on": _days(-30)})
    client.post("/api/revenue-events", json={
        "account_id": account["account"]["id"], "kind": "contraction", "amount": -20000,
        "currency": "EUR", "effective_on": _days(-10)})
    m = client.get(f"/api/accounts/{account['account']['id']}/revenue-movement").json()
    assert m["base_arr"] == 500000 and m["net_movement"] == 100000
    assert m["ending_arr"] == 600000 and m["insufficient_data"] is False
    assert "nrr" not in m and "rate" not in m


def test_revenue_movement_says_so_when_there_is_not_enough_data(client, account):
    m = client.get(f"/api/accounts/{account['account']['id']}/revenue-movement").json()
    assert m["insufficient_data"] is True and m["ending_arr"] is None


def test_revenue_events_enforce_sign_and_contract_currency(client, account):
    aid = account["account"]["id"]
    cv = client.post("/api/contracts", json={
        "account_id": aid, "version_label": "v1", "price": 500000}).json()
    client.patch(f"/api/contracts/{cv['id']}/revenue", json={"currency": "EUR", "price_basis": "arr"})
    assert client.post("/api/revenue-events", json={
        "account_id": aid, "contract_version_id": cv["id"], "kind": "contraction",
        "amount": 1, "currency": "EUR", "effective_on": _today()}).status_code == 422
    assert client.post("/api/revenue-events", json={
        "account_id": aid, "contract_version_id": cv["id"], "kind": "expansion",
        "amount": 1, "currency": "USD", "effective_on": _today()}).status_code == 422
    ok = client.post("/api/revenue-events", json={
        "account_id": aid, "contract_version_id": cv["id"], "kind": "contraction",
        "amount": -1000, "currency": "eur", "effective_on": _today()})
    assert ok.status_code == 201 and ok.json()["currency"] == "EUR"


# --- §3.2 the headcount series the detector will need -------------------------------------------------
def test_headcount_series_reports_when_the_detector_can_switch_on(client, account):
    """The land-and-leave detector needs two comparable periods; the table ships now so the
    clock starts, and the API says plainly whether it is ready rather than guessing."""
    seg = account["dach"]["id"]
    h = client.get(f"/api/population-segments/{seg}/headcount-history").json()
    assert h["detector_ready"] is False

    client.post("/api/population-headcount-observations", json={
        "segment_id": seg, "period_label": "2026-Q1", "headcount": 6000,
        "source_kind": "hris_adapter", "observed_on": _days(-90)})
    client.post("/api/population-headcount-observations", json={
        "segment_id": seg, "period_label": "2026-Q2", "headcount": 6800,
        "source_kind": "hris_adapter", "observed_on": _today()})
    h = client.get(f"/api/population-segments/{seg}/headcount-history").json()
    assert h["comparable_periods"] == 2 and h["detector_ready"] is True


# --- defects found by adversarial review of this slice (D-86) -------------------------------
# Theme the reviewer named, correctly: the module's comments promised guarantees the code did
# not deliver. Each of these reproduced against the first implementation.

def test_cell_row_must_belong_to_the_cell_account(client, account):
    """A cell claiming account A with account B's segment aggregated another customer's
    population into A's rollup — the same look-up-by-id-and-trust-the-caller defect as D-82."""
    other = client.post("/api/accounts", json={"name": "Globex"}).json()
    op = client.post("/api/population-partitions", json={
        "account_id": other["id"], "total_fte": 5000}).json()
    oseg = client.post("/api/population-segments", json={
        "partition_id": op["id"], "name": "Their BU", "headcount": 900}).json()

    r = client.post("/api/whitespace-cells", json={
        "account_id": account["account"]["id"], "segment_id": oseg["id"],
        "use_case_id": account["uc"]["id"], "paid_seats": 400})
    assert r.status_code == 422 and "different account" in r.json()["detail"]


def test_composite_view_cannot_import_another_accounts_segment(client, account):
    other = client.post("/api/accounts", json={"name": "Globex"}).json()
    op = client.post("/api/population-partitions", json={
        "account_id": other["id"], "total_fte": 1000}).json()
    oseg = client.post("/api/population-segments", json={
        "partition_id": op["id"], "name": "Other population", "headcount": 500}).json()
    r = client.post("/api/population-views", json={
        "account_id": account["account"]["id"], "name": "Mixed customer cohort",
        "segment_ids": [oseg["id"]], "estimated_headcount": 500})
    assert r.status_code == 422 and "active partition" in r.json()["detail"]


def test_superseded_partition_segments_leave_the_live_map(client, account):
    """Versioning the partition is what makes re-basing clean; querying segments by account
    instead of by active partition returned every generation at once, so a re-based account
    reported more addressable seats than the company has people."""
    _cell(client, account, segment_id=account["dach"]["id"], paid_seats=900)
    p2 = client.post("/api/population-partitions", json={
        "account_id": account["account"]["id"], "total_fte": 20000,
        "reason": "client reorganised into functions"}).json()
    client.post("/api/population-segments", json={
        "partition_id": p2["id"], "name": "Functions", "headcount": 12000})

    m = client.get(f"/api/accounts/{account['account']['id']}/whitespace").json()
    assert [r["name"] for r in m["segment_rows"]] == ["Functions"]
    assert m["rollup"]["addressable_seats"] == 12000        # not 12000 + the old generation
    assert m["rollup"]["paid_seats"] == 0                   # the old cell is history, not inventory


def test_unallocated_remainder_is_capped_like_every_other_segment(client, account):
    """Exempting the remainder from the FTE cap let it exceed the company, which breaks the
    reconciliation the remainder exists to make honest."""
    r = client.post("/api/population-segments", json={
        "partition_id": account["partition"]["id"], "name": "Unallocated",
        "headcount": 50000, "is_unallocated": True})
    assert r.status_code == 422 and "exceeding" in r.json()["detail"]


def test_account_wide_target_cannot_read_another_accounts_observation(client, account):
    """A target with no segment and no view is account-wide, not portfolio-wide."""
    other = client.post("/api/accounts", json={"name": "Globex"}).json()
    oprog = client.post("/api/programs", json={"account_id": other["id"], "name": "P"}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": oprog["id"], "value": 0.95,
        "current_through": _days(-1)})

    t = client.post("/api/value-targets", json={
        "account_id": account["account"]["id"], "definition_id": d["id"],
        "target_value": 0.70, "timeframe_end": _days(30)}).json()
    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    row = next(r for r in led["targets"] if r["id"] == t["id"])
    assert row["realization"]["status"] != "realized"
    assert row["realization"]["value"] is None


def test_metric_values_for_sub_floor_cohorts_are_suppressed(client, account):
    """The actual privacy control. A metric over a ten-person cohort is behavioural data about
    identifiable people; suppressing the penetration rate while shipping the metric was not
    protection, it was decoration."""
    p = client.get(f"/api/accounts/{account['account']['id']}/population-partition").json()
    tiny = client.post("/api/population-segments", json={
        "partition_id": p["id"], "name": "Innovation lab", "headcount": 10}).json()
    d = client.post("/api/metric-definitions", json={"name": "Activation", "stale_after_days": 30}).json()
    prog = client.post("/api/programs", json={"account_id": account["account"]["id"], "name": "P"}).json()
    client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": prog["id"], "value": 0.8,
        "current_through": _days(-1), "population_segment_id": tiny["id"]})
    t = client.post("/api/value-targets", json={
        "account_id": account["account"]["id"], "definition_id": d["id"],
        "segment_id": tiny["id"], "target_value": 0.7, "timeframe_end": _days(30)}).json()

    led = client.get(f"/api/accounts/{account['account']['id']}/ledger").json()
    r = next(x for x in led["targets"] if x["id"] == t["id"])["realization"]
    assert r["status"] == "suppressed" and r["value"] is None


def test_sub_floor_metrics_are_refused_at_ingest_and_redacted_on_every_legacy_read(client, account):
    """The ledger alone is not the privacy boundary: evidence pickers, scoreboards, trend APIs,
    and the legacy QBR must not provide alternate routes to the same behavioural value."""
    p = client.get(f"/api/accounts/{account['account']['id']}/population-partition").json()
    tiny = client.post("/api/population-segments", json={
        "partition_id": p["id"], "name": "Small strategy team", "headcount": 8}).json()
    d = client.post("/api/metric-definitions", json={"name": "Weekly return", "stale_after_days": 30}).json()
    prog = client.post("/api/programs", json={"account_id": account["account"]["id"], "name": "P"}).json()
    refused = client.post("/api/metric-observations", json={
        "definition_id": d["id"], "program_id": prog["id"], "value": 0.88,
        "target": 0.75, "current_through": _days(-1), "population_segment_id": tiny["id"]})
    assert refused.status_code == 422 and "sufficiently aggregated" in refused.json()["detail"]

    csv = ("definition_id,period_label,value,program_id,population_segment_id\n"
           f"{d['id']},2026-Q3,0.88,{prog['id']},{tiny['id']}\n")
    preview = client.post("/api/imports/metric-observations/preview", json={
        "csv_text": csv, "current_through": _days(-1)}).json()
    assert preview["valid"] == 0 and "below the account minimum" in preview["rows"][0]["errors"][0]
    assert client.post("/api/imports/metric-observations/commit", json={
        "csv_text": csv, "current_through": _days(-1)}).status_code == 422

    # Simulate a legacy row created before this guard. Every generic read still redacts it.
    from app import repo
    source = client.post("/api/source-references", json={
        "label": "Legacy aggregate report", "type": "data_report"}).json()["id"]
    legacy = repo.insert(client.app.state.conn, "metric_observations", {
        "definition_id": d["id"], "definition_version": "1", "program_id": prog["id"],
        "population_segment_id": tiny["id"], "period_label": "legacy", "value": 0.88,
        "target": 0.75, "current_through": _days(-1), "source_reference_id": source},
        object_type="metric_observation")
    picker = client.get(f"/api/accounts/{account['account']['id']}/metric-observations").json()
    row = next(r for r in picker if r["id"] == legacy["id"])
    assert row["suppressed"] is True and row["value"] is None and row["target"] is None
    scoreboard = client.get("/api/scoreboard").json()
    card = next(c for c in scoreboard["cards"] if c["definition"]["id"] == d["id"])
    assert card["suppressed"] is True and card["display_value"] == "suppressed"
    history = client.get(f"/api/metric-definitions/{d['id']}/observations").json()["series"]
    assert history[-1]["suppressed"] is True and history[-1]["value"] is None
    qbr = client.get(f"/api/accounts/{account['account']['id']}/qbr").json()
    metric = next(m for m in qbr["metrics"] if m["name"] == "Weekly return")
    assert metric["value"] == "suppressed" and metric["target"] is None


def test_a_failed_supersede_leaves_the_original_bar_active(client, account):
    """The status flip and the replacement insert were separate transactions, so a replacement
    that failed its CHECK left the account with a superseded target and nothing superseding it."""
    d = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    t = _target(client, account, d["id"]).json()
    r = client.post(f"/api/value-targets/{t['id']}/supersede", json={
        "target_value": 0.9, "timeframe_end": _days(90), "reason": "new bar",
        "client_accepted": True})            # accepted with no accepter and no date
    assert r.status_code == 422
    assert client.get(f"/api/accounts/{account['account']['id']}/ledger").json()["total"] == 1


def test_typed_links_reject_objects_that_do_not_exist(client, account):
    """"Typed link" has to mean the object exists, or the UI renders evidence that was never there."""
    cell = _cell(client, account, segment_id=account["dach"]["id"])
    r = client.post(f"/api/whitespace-cells/{cell['id']}/evidence", json={
        "object_type": "metric_observation", "object_id": "does-not-exist"})
    assert r.status_code == 422

    cal = client.post("/api/ask-calendars", json={
        "account_id": account["account"]["id"], "name": "Ask",
        "target_close_date": _days(180)}).json()
    r2 = client.patch(f"/api/ask-calendar-steps/{cal['steps'][0]['id']}", json={
        "linked_type": "task", "linked_id": "does-not-exist"})
    assert r2.status_code == 422


def test_budget_step_lands_on_the_clients_actual_deadline(client, account):
    """The budget request is a date the client's finance calendar fixes, not a lead time.
    Back-scheduling off a generic offset ignored the deadline already recorded, which is the
    "discover it late" failure the ask calendar exists to prevent."""
    client.put(f"/api/accounts/{account['account']['id']}/fiscal-map", json={
        "planning_window_start": "01-01", "planning_window_end": "01-31",
        "budget_request_deadline": "01-15", "confirmed_on": _today()})
    close = _days(180)
    cal = client.post("/api/ask-calendars", json={
        "account_id": account["account"]["id"], "name": "Ask",
        "target_close_date": close}).json()
    step = next(s for s in cal["steps"] if s["kind"] == "budget_window")
    assert step["due_date"].endswith("-01-15") and step["due_date"] <= close
    # and the generic 80-day offset would NOT have landed there
    assert step["due_date"] != _days(180 - 80)
