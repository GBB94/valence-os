"""Acceptance tests for ACCOUNT-PATH-SPEC.md Slice 7 — measurement and refinement.

These are written to try to get something into the measurement sink that does not belong there —
a person's name, an email address, a description, a title under a key nobody screened, a payload
past its bound — and to try to make measurement matter to the product: to a status, to a ranking,
to an export, to whether a page loads at all. Each test asserts the honest answer, which is that
the event is dropped with a stated reason and the product does not notice either way.
"""
import json
import os
import pathlib
import re
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    os.environ.pop("VALENCE_OS_RANKING_RULES", None)
    os.environ.pop("VALENCE_OS_TELEMETRY_STRICT", None)
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _sql(c, statement, params=()):
    conn = sqlite3.connect(c.db_path)
    try:
        conn.row_factory = sqlite3.Row
        with conn:
            return [dict(r) for r in conn.execute(statement, params).fetchall()]
    finally:
        conn.close()


def _post(c, event_name, **payload):
    return c.post("/api/telemetry/events", json={"event_name": event_name, **payload})


def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name="Europe Deployment", phase="launch"):
    return c.post("/api/programs", json={"account_id": account_id, "name": name,
                                         "phase": phase}).json()


# --- §17.2 / §17.3 the event contract -------------------------------------------------------

def test_the_twenty_two_named_events_are_exactly_the_allowlist():
    """§17.3's sixteen, plus the six `ACCOUNT-INTAKE-SPEC.md` §17 amends in (D-246).

    Asserted literally, in one set, because the amendment is the whole point: the drop zone's
    events live under the same contract as the rest rather than in a store of their own.
    """
    from app import telemetry
    assert set(telemetry.EVENTS) == {
        "account_path_viewed", "next_move_opened", "next_move_snoozed", "next_move_left_list",
        "successor_action_created", "execution_group_opened", "program_path_filtered",
        "requirement_opened", "requirement_action_created", "proposal_review_opened",
        "proposal_accepted", "proposal_rejected", "phase_readiness_opened",
        "phase_transition_completed", "execution_native_target_opened", "execution_path_retry",
        "drop_zone_shown", "drop_received", "drop_refused", "drop_drafted",
        "drop_no_proposals", "drop_receipt_opened",
    }


def test_no_drop_event_can_carry_anything_that_could_hold_a_filename():
    """`ACCOUNT-INTAKE-SPEC.md` §17 — "a filename is document content by another name".

    The per-event allowlists are the enforcement, so the assertion is that they are *empty* apart
    from a reason code. A future key added to one of these six has to fail here first.
    """
    from app import telemetry
    for name in [e for e in telemetry.EVENTS if e.startswith("drop_")]:
        assert set(telemetry.EVENTS[name]) <= {"reason_code"}, name


def test_an_unknown_event_is_rejected_in_development_and_dropped_in_production(client):
    """§17.3 asks for two behaviours from one condition. Both are exercised here."""
    os.environ["VALENCE_OS_TELEMETRY_STRICT"] = "1"
    strict = _post(client, "next_move_admired", account_id="a1")
    assert strict.status_code == 422
    assert "allowlist" in strict.json()["detail"]

    os.environ["VALENCE_OS_TELEMETRY_STRICT"] = "0"
    try:
        relaxed = _post(client, "next_move_admired", account_id="a1")
        assert relaxed.status_code == 202
        assert relaxed.json()["recorded"] is False
        assert "allowlist" in relaxed.json()["reason"]
    finally:
        os.environ.pop("VALENCE_OS_TELEMETRY_STRICT", None)
    assert _sql(client, "SELECT COUNT(*) n FROM product_events")[0]["n"] == 0


def test_a_property_the_event_did_not_declare_is_rejected_not_trimmed(client):
    """A trimmed payload is one nobody notices. The whole event is refused instead."""
    res = _post(client, "next_move_opened", account_id="a1",
                properties={"reason_code": "overdue_operator_task", "customer_mood": "warm"})
    assert res.status_code == 422
    assert "not declared by 'next_move_opened'" in res.json()["detail"]


@pytest.mark.parametrize("properties,fragment", [
    ({"title": "renew-emea"}, "customer or person content"),
    ({"email": "someone.example"}, "customer or person content"),
    ({"description": "a-note"}, "customer or person content"),
    ({"person_name": "casey"}, "customer or person content"),
])
def test_sensitive_property_names_are_refused_by_name(client, properties, fragment):
    """§17.9 sensitive-property rejection.

    Every one of these would also fail the per-event allowlist. They are named separately so the
    refusal cites the trust boundary rather than saying "unknown key" — and so a future event
    definition cannot quietly adopt one of them.
    """
    res = _post(client, "next_move_opened", account_id="a1", properties=properties)
    assert res.status_code == 422
    assert fragment in res.json()["detail"]


def test_no_allowlisted_property_is_a_sensitive_name():
    """The two lists must never agree. If they do, the denylist has stopped denying anything."""
    from app import telemetry
    declared = {key for keys in telemetry.EVENTS.values() for key in keys}
    assert not declared & telemetry.SENSITIVE_KEYS


@pytest.mark.parametrize("value", [
    "Confirm the data-processing addendum with the works council",  # a title
    "casey@example.invalid",                                        # an address
    "Casey Rivera",                                                 # a name
    "lines 41-58 of the signed agreement",                          # a source span
    "x" * 80,                                                       # unbounded
])
def test_a_property_value_that_is_not_a_slug_cannot_be_measured(client, value):
    """§17.2's prohibition, enforced by shape rather than by a list of forbidden phrases.

    A denylist of key names is defeated by the next key nobody thought of. A value rule is not:
    none of the things §17.2 names can be spelled as a lower-case slug.
    """
    res = _post(client, "next_move_opened", account_id="a1",
                properties={"reason_code": value})
    assert res.status_code == 422
    assert "bounded slug value" in res.json()["detail"]


def test_a_well_formed_event_is_stored_with_its_schema_version(client):
    res = _post(client, "next_move_opened", account_id="acc-1", program_id="prog-1",
                session_id="local-abc12345", occurred_at="2026-08-05T09:15:00Z",
                ranking_rule_version="v1-2026-08-04",
                properties={"source_type": "task", "reason_code": "overdue_operator_task",
                            "band": 3, "urgency": "now", "scope_mode": "program"})
    assert res.status_code == 202 and res.json()["recorded"] is True
    row = _sql(client, "SELECT * FROM product_events")[0]
    assert row["event_name"] == "next_move_opened"
    assert row["schema_version"] == 1
    assert row["ranking_rule_version"] == "v1-2026-08-04"
    # Normalised to the application's own timestamp spelling; two spellings of one instant sort
    # differently, and a retention cutoff would then disagree with a funnel window.
    assert row["occurred_at"] == "2026-08-05T09:15:00+00:00"
    assert json.loads(row["properties_json"])["reason_code"] == "overdue_operator_task"


def test_the_session_identifier_is_pseudonymous_and_bounded(client):
    assert _post(client, "account_path_viewed", session_id="operator.casey@example.invalid"
                 ).status_code == 422
    assert _post(client, "account_path_viewed", session_id="local-9f2b41ce"
                 ).status_code == 202


# --- §17.4 the local implementation ---------------------------------------------------------

def test_measurement_can_be_disabled_and_disabling_clears_what_was_kept(client):
    _post(client, "account_path_viewed", account_id="acc-1", properties={"program_count": 2})
    assert _sql(client, "SELECT COUNT(*) n FROM product_events")[0]["n"] == 1

    off = client.patch("/api/telemetry/settings", json={"enabled": False})
    assert off.status_code == 200 and off.json()["enabled"] is False
    # "Measurement is disabled" and "there is measurement data" must not both be true.
    assert _sql(client, "SELECT COUNT(*) n FROM product_events")[0]["n"] == 0

    dropped = _post(client, "account_path_viewed", account_id="acc-1")
    assert dropped.status_code == 202
    assert dropped.json() == {"recorded": False, "reason": "measurement is disabled"}
    assert _sql(client, "SELECT COUNT(*) n FROM product_events")[0]["n"] == 0


def test_retention_is_bounded_and_purges_on_write(client):
    from app import telemetry
    client.patch("/api/telemetry/settings", json={"retention_days": 30})
    conn = sqlite3.connect(client.db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO product_events (id,event_name,schema_version,occurred_at,session_id,"
                "properties_json,created_at) VALUES ('old','account_path_viewed',1,?, 'local-x1',"
                "'{}',?)", (f"{utc_day(-120)}T00:00:00+00:00", f"{utc_day(-120)}T00:00:00+00:00"))
    finally:
        conn.close()
    assert _sql(client, "SELECT COUNT(*) n FROM product_events")[0]["n"] == 1
    _post(client, "account_path_viewed", account_id="acc-1")
    remaining = _sql(client, "SELECT id FROM product_events")
    assert [r["id"] for r in remaining] != ["old"]
    assert "old" not in {r["id"] for r in remaining}
    assert client.get("/api/telemetry/settings").json()["retention_days"] == 30
    assert client.patch("/api/telemetry/settings", json={"retention_days": 5000}).status_code == 422


def test_a_broken_sink_never_reaches_the_caller(client):
    """§17.8: measurement failure cannot block Account Path.

    The table is dropped out from under the adapter, which is the bluntest version of every
    failure a real sink could have. `record()` still returns rather than raising.
    """
    from app import telemetry
    conn = sqlite3.connect(client.db_path)
    try:
        with conn:
            conn.execute("DROP TABLE product_events")
        result = telemetry.record(conn, "account_path_viewed", account_id="acc-1")
    finally:
        conn.close()
    assert result == {"recorded": False, "reason": "measurement sink unavailable"}


def test_telemetry_never_enters_the_audit_log(client):
    """§17.4: opening UI is not a domain mutation."""
    before = _sql(client, "SELECT COUNT(*) n FROM audit_events")[0]["n"]
    for _ in range(3):
        _post(client, "account_path_viewed", account_id="acc-1", properties={"program_count": 1})
    assert _sql(client, "SELECT COUNT(*) n FROM audit_events")[0]["n"] == before


def test_product_events_carry_no_foreign_keys(client):
    """A diagnostic row may never complicate a domain mutation (§17.8).

    Asserted structurally rather than by deleting an account, because the guarantee is about
    every future delete, restore, and import — not the one this test happens to run.
    """
    keys = _sql(client, "PRAGMA foreign_key_list(product_events)")
    assert keys == []


def test_the_schema_refuses_free_text_even_if_the_adapter_is_bypassed(client):
    """The CHECK constraints are the backstop for a caller who writes the table directly."""
    conn = sqlite3.connect(client.db_path)
    try:
        for payload in ('{"note":"casey@example.invalid"}', '{"note":"%s"}' % ("x" * 600)):
            with pytest.raises(sqlite3.IntegrityError):
                with conn:
                    conn.execute(
                        "INSERT INTO product_events (id,event_name,schema_version,occurred_at,"
                        "session_id,properties_json,created_at) VALUES (?,?,1,?,?,?,?)",
                        ("x", "account_path_viewed", "2026-08-05T00:00:00+00:00", "local-x1",
                         payload, "2026-08-05T00:00:00+00:00"))
    finally:
        conn.close()


# --- §17.1 / §17.8 measurement is not truth --------------------------------------------------

def test_no_domain_module_reads_product_events():
    """§17.8: account truth and ranking never read product events.

    Asserted over the source tree rather than over one code path, because the rule is about
    every module that could later be tempted, not the ones that exist today.
    """
    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    allowed = {"telemetry.py", "routers/telemetry.py", "portfolio_io.py"}
    offenders = []
    for path in sorted(app_dir.rglob("*.py")):
        rel = str(path.relative_to(app_dir))
        if rel in allowed or rel.startswith("__"):
            continue
        text = path.read_text()
        if "product_events" in text or "product_telemetry_settings" in text:
            offenders.append(rel)
        if "import telemetry" in text or "from .telemetry" in text or "from ..telemetry" in text:
            offenders.append(rel)
    # `main.py` imports the router package, not the module; a direct import from any domain
    # service is what this is looking for.
    assert offenders == [], (
        f"these modules reach into product measurement: {offenders}. §17.1 makes product events "
        f"operational diagnostics — account status, pillar state, ranking, generated outputs, and "
        f"customer-facing surfaces may never read them.")


def test_opening_the_execution_path_writes_no_product_event(client):
    """The projection stays a projection.

    Slice 1 promised the read model writes nothing. Recording the view server-side would have
    been the easy place to put it and would have quietly broken that.
    """
    account = _account(client)
    _program(client, account["id"])
    assert client.get(f"/api/accounts/{account['id']}/execution-path").status_code == 200
    assert _sql(client, "SELECT COUNT(*) n FROM product_events")[0]["n"] == 0


def test_account_export_excludes_telemetry(client):
    """§17.4: export/import excludes telemetry by default."""
    account = _account(client)
    _program(client, account["id"])
    _post(client, "account_path_viewed", account_id=account["id"],
          properties={"program_count": 1, "coverage_status": "complete"})
    bundle = client.get(f"/api/accounts/{account['id']}/export").json()
    serialized = json.dumps(bundle)
    assert "product_events" not in bundle.get("tables", bundle)
    assert "account_path_viewed" not in serialized


# --- §17.5 the funnel ------------------------------------------------------------------------

def test_the_funnel_reports_denominators_and_refuses_to_score(client):
    account = _account(client)
    for i in range(3):
        _post(client, "account_path_viewed", account_id=account["id"],
              properties={"has_next_move": True, "coverage_status": "complete",
                          "program_count": 1})
    _post(client, "account_path_viewed", account_id=account["id"],
          properties={"has_next_move": False, "coverage_status": "partial"})
    _post(client, "next_move_opened", account_id=account["id"],
          properties={"reason_code": "overdue_operator_task", "source_type": "task"})
    _post(client, "next_move_left_list", account_id=account["id"],
          properties={"reason_code": "overdue_operator_task", "source_type": "task"})
    _post(client, "next_move_snoozed", account_id=account["id"],
          properties={"reason_code": "milestone_preparation", "source_type": "milestone"})

    funnel = client.get(f"/api/telemetry/funnel?account_id={account['id']}").json()
    assert funnel["totals"]["views"] == 4
    assert funnel["totals"]["views_with_next_move"] == 3
    assert funnel["totals"]["next_move_opened"] == 1
    assert funnel["totals"]["views_with_incomplete_coverage"] == 1
    by_code = {row["reason_code"]: row for row in funnel["by_reason_code"]}
    # `left_list`, not `completed`. §17.3 says the absence this event observes is also produced by
    # cancellation, archival, and an aged-out band window, and "must not be read or reported as a
    # completion count" — so the funnel may not offer a key that invites exactly that reading.
    assert by_code["overdue_operator_task"]["left_list"] == 1
    assert "completed" not in by_code["overdue_operator_task"]
    assert by_code["milestone_preparation"]["snoozed"] == 1
    # §17.5 ends by saying clicks do not define success. The response says so too, because this
    # is the number most likely to be quoted on its own.
    assert "qualitative review" in funnel["caveat"]
    assert not any(k in funnel["totals"] for k in ("score", "rate", "conversion"))
    # One ordering in the data, so there is nothing to separate and nothing to warn about.
    assert funnel["spans_multiple_rule_versions"] is False
    assert " span more than one ranking ruleset" not in funnel["caveat"]


def test_a_funnel_spanning_two_rulesets_separates_them_and_says_the_aggregate_does_not(client):
    """Every event carries its ranking rule version so a funnel cannot average two orderings.

    Recording the column and then reading past it is that same failure with an extra step: an
    aggregate over a re-ranking describes no ordering that ever shipped. The counts are still
    returned — an operator asking "how much traffic" deserves an answer — but they are labelled,
    and the separable numbers are returned beside them.
    """
    account = _account(client)
    for version, opens in (("v1", 2), ("v2", 1)):
        for _ in range(opens):
            _post(client, "next_move_opened", account_id=account["id"],
                  ranking_rule_version=version,
                  properties={"reason_code": "overdue_operator_task", "source_type": "task"})

    funnel = client.get(f"/api/telemetry/funnel?account_id={account['id']}").json()
    assert funnel["spans_multiple_rule_versions"] is True
    assert funnel["totals"]["next_move_opened"] == 3
    assert "span more than one ranking ruleset" in funnel["caveat"]
    assert "by_rule_version" in funnel["caveat"]

    blocks = {b["ranking_rule_version"]: b for b in funnel["by_rule_version"]}
    assert blocks["v1"]["totals"]["next_move_opened"] == 2
    assert blocks["v2"]["totals"]["next_move_opened"] == 1
    # And the per-version block is a whole funnel, not a headline count.
    v1_codes = {r["reason_code"]: r for r in blocks["v1"]["by_reason_code"]}
    assert v1_codes["overdue_operator_task"]["opened"] == 2


# --- §17.6 governed rule refinement ----------------------------------------------------------

def test_the_execution_path_names_the_ruleset_it_ranked_under(client):
    from app import execution_path
    account = _account(client)
    _program(client, account["id"])
    body = client.get(f"/api/accounts/{account['id']}/execution-path").json()
    rules = body["ranking_rules"]
    assert rules["version"] == execution_path.DEFAULT_RANKING_VERSION
    assert rules["status"] == "active"
    assert rules["flag"] == "VALENCE_OS_RANKING_RULES"
    assert "v2-candidate-notice-first" in rules["available_versions"]


def test_a_candidate_ruleset_is_not_live_without_the_flag(client):
    """Shipping a candidate must not ship the rule change."""
    from app import execution_path
    assert execution_path.active_ranking_version() == execution_path.DEFAULT_RANKING_VERSION
    assert execution_path.RANKING_RULE_VERSIONS["v2-candidate-notice-first"]["status"] == "candidate"
    os.environ["VALENCE_OS_RANKING_RULES"] = "v9-does-not-exist"
    try:
        # An unknown flag value falls back to the default rather than failing the page. A ranking
        # the operator can read beats a 500 that explains a typo.
        assert execution_path.active_ranking_version() == execution_path.DEFAULT_RANKING_VERSION
    finally:
        os.environ.pop("VALENCE_OS_RANKING_RULES", None)


def test_two_rule_versions_can_be_compared_deterministically(client):
    """§17.6 step 4, over a fixture built to be sensitive to exactly the candidate's change.

    An overdue Task and a contract notice window rank 3 and 4 under v1 and swap under v2, so the
    comparison has something real to report rather than an empty diff that proves nothing.
    """
    from app import execution_path
    account = _account(client)
    program = _program(client, account["id"])
    assert client.post("/api/tasks", json={
        "program_id": program["id"], "description": "Send the draft plan",
        "due_date": utc_day(-4)}).status_code == 201
    client.post("/api/contracts", json={
        "account_id": account["id"], "version_label": "Initial term",
        "renewal_date": utc_day(30), "notice_period_days": 60})

    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        first = execution_path.compare_rule_versions(
            conn, [account["id"]], execution_path.DEFAULT_RANKING_VERSION,
            "v2-candidate-notice-first")
        second = execution_path.compare_rule_versions(
            conn, [account["id"]], execution_path.DEFAULT_RANKING_VERSION,
            "v2-candidate-notice-first")
    finally:
        conn.close()

    assert first == second, "the comparison must be deterministic to be reviewable"
    assert first["accounts_with_changes"] == 1
    account_row = first["accounts"][0]
    assert account_row["next_move_changed"] is True
    assert account_row["next_move_before"] != account_row["next_move_after"]
    assert account_row["next_move_after"].startswith("contract_version:")
    assert account_row["moved_rows"], "a ruleset change with no moved row explains nothing"


def test_comparing_a_version_with_itself_is_refused(client):
    from app import execution_path
    conn = sqlite3.connect(client.db_path)
    try:
        with pytest.raises(Exception) as caught:
            execution_path.compare_rule_versions(
                conn, [], execution_path.DEFAULT_RANKING_VERSION,
                execution_path.DEFAULT_RANKING_VERSION)
        assert "two different versions" in str(caught.value)
    finally:
        conn.close()


def test_the_ranking_rule_registry_is_readable(client):
    body = client.get("/api/telemetry/ranking-rules").json()
    versions = {row["version"]: row for row in body["versions"]}
    assert versions[body["active_version"]]["status"] == "active"
    # Every band map must cover every reason code the projection can emit, or a candidate would
    # crash the page it was meant to be compared on.
    from app.execution_path import BANDS
    for row in body["versions"]:
        assert set(row["bands"]) == set(BANDS), row["version"]


# --- the measurement boundary is registered --------------------------------------------------

def test_the_measurement_sink_is_a_registered_connection_boundary(client):
    """Local today, a vendor tomorrow — and that day is a data-handling decision, not a config."""
    registry = client.get("/api/operations").json()["connection_registry"]
    entry = next(r for r in registry["connections"] if r["id"] == "product_telemetry_sink")
    assert entry["gate_status"] == "local"
    assert entry["current_mode"] == "local_sqlite_only"
    assert "leave the installation" in entry["real_requires"]


def test_the_client_event_names_match_the_server_allowlist():
    """The one duplication in the contract, so a client typo fails here instead of silently.

    `frontend/src/telemetry.js` holds its own copy of the sixteen names because it drops an
    unknown one before sending — a call site with a typo should be a no-op the developer can see,
    not a request the server discards. That is only safe while the two lists agree.
    """
    from app import telemetry

    source = (pathlib.Path(__file__).resolve().parents[2]
              / "frontend" / "src" / "telemetry.js").read_text()
    block = source.split("export const EVENT_NAMES = Object.freeze([", 1)[1].split("]);", 1)[0]
    client_names = set(re.findall(r'"([a-z0-9_]+)"', block))
    assert client_names == set(telemetry.EVENTS)
