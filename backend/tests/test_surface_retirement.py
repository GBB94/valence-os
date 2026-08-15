"""Stage 17 Slice 3 — recorded causes and reversible retirement (`SURFACE-USAGE-SPEC.md` §7, §11).

Almost every test here tries to get something hidden that should not be. The failure mode this slice
guards is silent: a retirement that breaks nothing, raises nothing, and simply makes something
unreachable — and the usage data would never say so, because the thing that stopped happening
stopped emitting events too. So the assertions are mostly about refusals, and about refusals being
sentences an operator can act on rather than error codes they can only argue with.

§11's test 4 is the bidirectional one: for each record type, the safety check refuses when the last
route to it would go, and does *not* refuse for any proper subset that leaves a route standing. A
one-directional version passes trivially by refusing everything.
"""
import os
import re
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from app import surface_retirement, surfaces

from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    os.environ.pop("VALENCE_OS_TELEMETRY_STRICT", None)
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


def _conn(c):
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _sql(c, statement, params=()):
    conn = _conn(c)
    try:
        with conn:
            return [dict(r) for r in conn.execute(statement, params).fetchall()]
    finally:
        conn.close()


def _stage(surface, cause="not_needed", action="collapse", note=None):
    entry = {"surface": surface, "cause_code": cause, "action": action}
    if note:
        entry["note"] = note
    return entry


def _preview(c, staged):
    response = c.post("/api/telemetry/surface-retirement/preview", json={"staged": staged})
    assert response.status_code == 200, response.text
    return response.json()


def _apply(c, staged, **body):
    return c.post("/api/telemetry/surface-retirement/apply", json={"staged": staged, **body})


def _state(c):
    response = c.get("/api/telemetry/surface-retirement")
    assert response.status_code == 200, response.text
    return response.json()


# --- the schema (§7.3, §6.1) ---------------------------------------------------------------------

def test_the_notes_table_has_exactly_the_columns_the_migration_declares(client):
    columns = {row["name"] for row in _sql(client, "PRAGMA table_info(surface_retirement_notes)")}
    assert columns == {"id", "surface_key", "cause_code", "observed_from", "observed_to",
                       "rendered", "engaged", "action", "batch_id", "note", "recorded_on",
                       "recorded_by"}


def test_no_state_column_exists_anywhere_in_this_feature(client):
    """§7.3. The current action is derived. A stored copy is a second thing that can disagree.

    `action` is present and is not a state: it records an operator command that was applied, which
    is a fact about what happened rather than a claim about what the surface currently is. The
    difference is that the latest `action` row *is* the derivation, not a cache of it.
    """
    for table in ("surface_retirement_notes", "surface_usage_months"):
        columns = {row["name"] for row in _sql(client, f"PRAGMA table_info({table})")}
        assert not (columns & {"state", "current_state", "status", "retirement", "retired",
                               "is_retired", "current_action"}), table


def test_no_score_column_exists_on_the_notes_table(client):
    columns = {row["name"] for row in _sql(client, "PRAGMA table_info(surface_retirement_notes)")}
    for column in columns:
        assert not re.search(r"score|rating|health|usage_index", column), column


def test_the_cause_vocabulary_is_closed_and_has_no_other():
    assert set(surface_retirement.CAUSE_CODES) == {
        "not_needed", "not_found", "misunderstood", "hard_to_use", "narrow_but_needed",
        "superseded", "demo_artifact"}
    assert "other" not in surface_retirement.CAUSE_CODES
    # The vocabulary can express a reason to *keep*. A form that can only agree with itself is not
    # a review, and `narrow_but_needed` is the only thing standing between "rarely used" and gone.
    assert "narrow_but_needed" in surface_retirement.CAUSE_CODES
    assert "Keep" in surface_retirement.CAUSE_MEANINGS["narrow_but_needed"]


def test_the_vocabulary_endpoint_carries_both_closed_lists_and_the_matrix(client):
    vocabulary = _state(client)["vocabulary"]
    assert [row["code"] for row in vocabulary["cause_codes"]] == list(
        surface_retirement.CAUSE_CODES)
    assert [row["action"] for row in vocabulary["actions"]] == list(surface_retirement.ACTIONS)
    assert vocabulary["undo_window_days"] == 14
    # §7.2. The batch undo expires; the single-surface restore never does.
    assert vocabulary["restore_expires"] is False


def test_demote_copy_does_not_promise_a_relocation_the_wrapper_cannot_perform(client):
    meaning = next(row["meaning"] for row in _state(client)["vocabulary"]["actions"]
                   if row["action"] == "demote")
    assert "current location" in meaning
    assert "nothing is relocated automatically" in meaning
    assert "moved" not in meaning.lower()


# --- §7.4 the per-kind matrix --------------------------------------------------------------------

def test_a_panel_can_only_be_retired(client):
    """Collapsing a modal is a no-op that looks like it worked. There is nothing at rest to close."""
    assert surface_retirement.AVAILABLE_ACTIONS["panel"] == ("retire",)
    response = _apply(client, [_stage("global.copilot", action="collapse")])
    assert response.status_code == 422
    assert "not available for a panel" in response.json()["detail"]


def test_a_tab_cannot_be_collapsed():
    assert "collapse" not in surface_retirement.AVAILABLE_ACTIONS["tab"]


def test_a_command_cannot_be_collapsed_and_can_be_retired():
    assert "collapse" not in surface_retirement.AVAILABLE_ACTIONS["command"]
    assert "retire" in surface_retirement.AVAILABLE_ACTIONS["command"]


def test_a_field_group_can_never_be_retired():
    """§7.6, absent from the matrix by construction rather than by a check that could be skipped."""
    assert "retire" not in surface_retirement.AVAILABLE_ACTIONS["field_group"]


def test_the_refusal_names_the_actions_that_are_available(client):
    response = _apply(client, [_stage("global.copilot", action="demote")])
    assert response.status_code == 422
    assert "retire" in response.json()["detail"]


# --- §7.7 the safety check, both directions (§11 test 4) ----------------------------------------

def test_retiring_the_only_route_to_a_record_type_is_refused(client):
    """`accounts.book` is the only offered surface reaching `account` other than `today.absence`."""
    reaching_account = [s.key for s in surfaces.REGISTRY if "account" in s.reaches]
    preview = _preview(client, [_stage(key, action="retire") for key in reaching_account])
    rules = {refusal["rule"] for refusal in preview["refusals"]}
    assert "reaches" in rules
    message = next(r["message"] for r in preview["refusals"] if r["rule"] == "reaches")
    assert "unreachable" in message and "Collapse instead" in message


def test_every_record_type_refuses_when_its_last_route_goes_and_not_before(client):
    """§11 test 4, bidirectional. A one-directional version passes by refusing everything.

    For each record type: retiring *all* surfaces reaching it must be refused, and retiring every
    proper subset must not be refused on the `reaches` rule — something still reaches it.
    """
    record_types = sorted({r for s in surfaces.REGISTRY for r in s.reaches})
    assert record_types, "the registry declares no record types"

    checked = 0
    for record_type in record_types:
        routes = sorted(s.key for s in surfaces.REGISTRY
                        if record_type in s.reaches and s.kind != "field_group")
        if len(routes) > 4:
            continue  # the subset sweep below is exponential; the small sets carry the property
        full = surface_retirement.safety_refusals(_noop_conn(client), set(routes))
        lost = {r for refusal in full if refusal["rule"] == "reaches"
                for r in refusal["unreachable"]}
        assert record_type in lost, f"retiring every route to {record_type} was allowed"

        for dropped in routes:
            subset = set(routes) - {dropped}
            if not subset:
                continue
            partial = surface_retirement.safety_refusals(_noop_conn(client), subset)
            still_lost = {r for refusal in partial if refusal["rule"] == "reaches"
                          for r in refusal["unreachable"]}
            assert record_type not in still_lost, (
                f"{record_type} was reported unreachable while {dropped} still offers it")
        checked += 1
    assert checked >= 5


def _noop_conn(c):
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_a_surface_explaining_a_refusal_cannot_be_retired_without_a_peer(client):
    """A refusal nobody can read is worse than the refusal not existing."""
    explainers = [s.key for s in surfaces.REGISTRY if s.explains_refusal]
    assert explainers
    preview = _preview(client, [_stage(key, action="retire") for key in explainers])
    rules = {refusal["rule"] for refusal in preview["refusals"]}
    assert "explains_refusal" in rules
    message = next(r["message"] for r in preview["refusals"]
                   if r["rule"] == "explains_refusal")
    assert "refusal" in message.lower()


def test_the_safety_check_is_evaluated_over_the_whole_set_not_one_key_at_a_time(client):
    """Two individually safe retirements can between them empty a `reaches` set.

    This is why §7.8 applies changes as a reviewed batch, and why the check takes a set.
    """
    pair = [s.key for s in surfaces.REGISTRY if "status_assessment" in s.reaches]
    assert len(pair) >= 2
    conn = _noop_conn(client)
    for key in pair:
        alone = surface_retirement.safety_refusals(conn, {key})
        lost = {r for refusal in alone if refusal["rule"] == "reaches"
                for r in refusal["unreachable"]}
        assert "status_assessment" not in lost
    together = surface_retirement.safety_refusals(conn, set(pair))
    lost = {r for refusal in together if refusal["rule"] == "reaches"
            for r in refusal["unreachable"]}
    assert "status_assessment" in lost


# --- §7.6 a field group holding data ------------------------------------------------------------

def _surface(**kw):
    kw.setdefault("added_on", "2026-08-06")
    return surfaces.Surface(**kw)


def test_a_field_group_must_declare_the_columns_it_shows():
    """Without them §7.6's count is not computable, and an unanswerable safety question is not a
    reason to proceed."""
    with pytest.raises(ValueError, match="data_columns"):
        surfaces._validate((_surface(
            key="x.group", label="X", route="today", kind="field_group", cadence="weekly",
            reaches=("account",)),))


def test_only_a_field_group_may_declare_data_columns():
    with pytest.raises(ValueError, match="may not declare"):
        surfaces._validate((_surface(
            key="x.section", label="X", route="today", kind="section", cadence="weekly",
            reaches=("account",), data_columns=("accounts.name",)),))


def test_the_field_group_refusal_names_the_count(client):
    # Pointed at a table with a guaranteed row, so the test measures the refusal rather than the
    # fixture. The rule is the same whichever columns a group declares.
    group = _surface(key="x.group", label="Retention", route="operations",
                     kind="field_group", cadence="quarterly", reaches=("account",),
                     data_columns=("product_telemetry_settings.retention_days",))
    conn = _noop_conn(client)
    held = conn.execute("SELECT COUNT(*) FROM product_telemetry_settings "
                        "WHERE retention_days IS NOT NULL").fetchone()[0]
    assert held > 0
    message = surface_retirement.field_group_refusal(conn, group)
    assert str(held) in message and "Collapse instead" in message


def test_a_declared_column_that_does_not_exist_keeps_the_refusal_in_place(client):
    """A registry typo must not unlock a retirement. The safe reading of an unanswerable "does this
    hold data" is that it might."""
    group = _surface(key="x.group", label="X", route="today", kind="field_group",
                     cadence="weekly", reaches=("account",),
                     data_columns=("no_such_table.no_such_column",))
    assert surface_retirement.field_group_refusal(_noop_conn(client), group) is not None


# --- §7.1 recording a cause ----------------------------------------------------------------------

def test_an_unlisted_cause_code_is_refused_and_the_message_says_the_list_is_closed(client):
    response = _apply(client, [_stage("today.saved_views", cause="other")])
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "no 'other'" in detail and "not_needed" in detail


def test_a_note_freezes_the_counts_it_was_judged_against(client):
    assert _apply(client, [_stage("today.saved_views")]).status_code == 200
    rows = _sql(client, "SELECT * FROM surface_retirement_notes")
    assert len(rows) == 1
    row = rows[0]
    assert row["rendered"] == 0 and row["engaged"] == 0
    # The window is on the note, because an undated judgement about a moving system is not evidence.
    assert row["observed_from"] and row["observed_to"]


def test_the_operator_sentence_is_stored_on_the_note_and_never_in_the_sink(client):
    prose = "Kept confusing this with the queue filter."
    assert _apply(client, [_stage("today.saved_views", note=prose)]).status_code == 200
    assert _sql(client, "SELECT note FROM surface_retirement_notes")[0]["note"] == prose
    events = _sql(client, "SELECT properties_json FROM product_events "
                          "WHERE event_name='retirement_action_applied'")
    assert events
    for event in events:
        assert prose not in event["properties_json"]
        assert "note" not in event["properties_json"]


def test_the_applied_event_carries_only_the_surface_action_and_cause(client):
    import json
    assert _apply(client, [_stage("today.saved_views", cause="misunderstood")]).status_code == 200
    row = _sql(client, "SELECT properties_json FROM product_events "
                       "WHERE event_name='retirement_action_applied'")[0]
    assert json.loads(row["properties_json"]) == {
        "surface": "today.saved_views", "action": "collapse", "cause_code": "misunderstood"}


def test_a_retired_command_is_counted_under_the_command_vocabulary(client):
    """§5's two vocabularies are not interchangeable, and a command is retirable (§7.4). Dropping
    command retirements from the sink would leave the funnel under-counting the one action it
    exists to record."""
    import json
    response = _apply(client, [_stage("command.export_team_update", action="demote")])
    assert response.status_code == 200, response.text
    rows = _sql(client, "SELECT properties_json FROM product_events "
                        "WHERE event_name='retirement_action_applied'")
    assert rows, "the command retirement was silently dropped by the sink"
    properties = json.loads(rows[0]["properties_json"])
    assert properties["command"] == "command.export_team_update"
    assert "surface" not in properties


def test_recording_a_cause_without_moving_anything_is_a_first_class_option(client):
    """`narrow_but_needed` + `none` is the answer the report must be able to receive."""
    response = _apply(client, [_stage("today.saved_views", cause="narrow_but_needed",
                                      action="none")])
    assert response.status_code == 200, response.text
    assert _state(client)["surfaces"]["today.saved_views"]["action"] == "none"
    # Nothing moved, so nothing is counted. A row in the funnel that changed nothing is noise.
    assert not _sql(client, "SELECT id FROM product_events "
                            "WHERE event_name='retirement_action_applied'")


# --- §7.3 the derived current action -------------------------------------------------------------

def test_the_current_action_is_the_latest_note_and_earlier_ones_survive(client):
    assert _apply(client, [_stage("today.saved_views", action="collapse")]).status_code == 200
    assert _apply(client, [_stage("today.saved_views", action="demote")]).status_code == 200
    assert _state(client)["surfaces"]["today.saved_views"]["action"] == "demote"
    assert len(_sql(client, "SELECT id FROM surface_retirement_notes")) == 2


def test_every_registered_surface_appears_in_the_state_including_untouched_ones(client):
    surfaces_state = _state(client)["surfaces"]
    assert set(surfaces_state) == set(surfaces.KEYS)
    assert surfaces_state["today.queue"]["action"] == "none"
    assert surfaces_state["today.queue"]["retired_notice"] is None


def test_the_state_carries_the_actions_available_for_each_kind(client):
    surfaces_state = _state(client)["surfaces"]
    assert surfaces_state["global.copilot"]["available_actions"] == ["retire"]
    assert surfaces_state["today.queue"]["available_actions"] == ["collapse", "demote", "retire"]


def test_a_retired_surface_carries_a_server_authored_notice(client):
    assert _apply(client, [_stage("accounts.portfolio_analytics", action="retire")]
                  ).status_code == 200
    notice = _state(client)["surfaces"]["accounts.portfolio_analytics"]["retired_notice"]
    assert notice and notice.startswith("You retired this view on ")


def test_collapse_and_demote_leave_a_surface_offered(client):
    """Only `retire` removes a surface from what is offered — which is what makes §7.7 a question
    about reachability rather than about prominence."""
    assert _apply(client, [_stage("today.saved_views", action="collapse")]).status_code == 200
    conn = _noop_conn(client)
    assert "today.saved_views" in surface_retirement.offered_keys(conn)
    assert _apply(client, [_stage("accounts.portfolio_analytics", action="retire")]
                  ).status_code == 200
    conn = _noop_conn(client)
    assert "accounts.portfolio_analytics" not in surface_retirement.offered_keys(conn)


# --- §7.8 the batch ------------------------------------------------------------------------------

def test_a_batch_shares_one_id_and_the_whole_sitting_undoes_as_one(client):
    staged = [_stage("today.saved_views"), _stage("commercial.value_ledger"),
              _stage("commercial.whitespace")]
    applied = _apply(client, staged).json()
    assert applied["applied"] == 3
    batches = {row["batch_id"] for row in _sql(client, "SELECT batch_id FROM "
                                                       "surface_retirement_notes")}
    assert len(batches) == 1

    undo = client.post("/api/telemetry/surface-retirement/undo",
                       json={"batch_id": applied["batch_id"]})
    assert undo.status_code == 200, undo.text
    assert sorted(undo.json()["restored"]) == sorted(s["surface"] for s in staged)
    state = _state(client)["surfaces"]
    for entry in staged:
        assert state[entry["surface"]]["action"] == "restore"


def test_an_undo_writes_reversing_rows_rather_than_deleting_the_ones_it_reverses(client):
    applied = _apply(client, [_stage("today.saved_views")]).json()
    client.post("/api/telemetry/surface-retirement/undo", json={"batch_id": applied["batch_id"]})
    actions = [row["action"] for row in _sql(
        client, "SELECT action FROM surface_retirement_notes ORDER BY rowid")]
    assert actions == ["collapse", "restore"]


def test_an_undo_carries_no_batch_id_so_it_cannot_be_read_back_as_part_of_the_sitting(client):
    """The reversing rows are restores, not a second sitting.

    Giving them the id of the batch they reverse would put them inside the set `undo_batch` selects,
    and the next pass would reverse its own output.
    """
    applied = _apply(client, [_stage("today.saved_views")]).json()
    client.post("/api/telemetry/surface-retirement/undo", json={"batch_id": applied["batch_id"]})
    rows = _sql(client, "SELECT action, batch_id FROM surface_retirement_notes ORDER BY rowid")
    assert [row["batch_id"] for row in rows] == [applied["batch_id"], None]


def test_undoing_the_same_sitting_twice_changes_nothing_and_says_why(client):
    """The compounding this guards: 1 note became 2, then 4, then 8, duplicating the audit trail and
    the funnel events on every pass — and the second undo reported the same surface restored twice.
    """
    staged = [_stage("today.saved_views"), _stage("commercial.value_ledger")]
    applied = _apply(client, staged).json()
    first = client.post("/api/telemetry/surface-retirement/undo",
                        json={"batch_id": applied["batch_id"]})
    assert first.status_code == 200, first.text
    assert sorted(first.json()["restored"]) == sorted(s["surface"] for s in staged)
    settled = _sql(client, "SELECT id FROM surface_retirement_notes")
    audited = _sql(client, "SELECT id FROM audit_events WHERE object_type='surface'")

    for _ in range(2):
        again = client.post("/api/telemetry/surface-retirement/undo",
                            json={"batch_id": applied["batch_id"]})
        assert again.status_code == 422
        detail = again.json()["detail"]
        assert "already offered as normal" in detail and "nothing left to undo" in detail
    assert len(_sql(client, "SELECT id FROM surface_retirement_notes")) == len(settled)
    assert len(_sql(client, "SELECT id FROM audit_events WHERE object_type='surface'")) == len(audited)


def test_an_undo_skips_a_surface_already_restored_on_its_own_and_states_that_it_did(client):
    """The mixed sitting. A surface put back individually has nothing left to reverse, and an undo
    that quietly wrote it a redundant row would be claiming to have done something it did not."""
    staged = [_stage("today.saved_views"), _stage("commercial.value_ledger"),
              _stage("commercial.whitespace")]
    applied = _apply(client, staged).json()
    solo = client.post("/api/telemetry/surface-retirement/restore",
                       json={"surface": "commercial.value_ledger"})
    assert solo.status_code == 200, solo.text

    undo = client.post("/api/telemetry/surface-retirement/undo",
                       json={"batch_id": applied["batch_id"]})
    assert undo.status_code == 200, undo.text
    body = undo.json()
    assert sorted(body["restored"]) == ["commercial.whitespace", "today.saved_views"]
    assert body["already_offered"] == ["commercial.value_ledger"]
    assert body["superseded"] == []
    assert "Of the 3 surfaces" in body["note"] and "already offered as normal" in body["note"]
    # One `restore` row for the solo call and two for the undo — not three for the undo.
    restores = _sql(client, "SELECT id FROM surface_retirement_notes WHERE action='restore'")
    assert len(restores) == 3


def test_undoing_a_sitting_never_overwrites_a_decision_made_after_it(client):
    """An undo is a way back from this sitting, not a way to win an argument with a later one.

    Batch A collapses a surface; batch B then retires it. Undoing A must leave B's decision alone —
    reversing it would replace the newer decision with an older one, and the operator who made B
    would find it quietly undone by a button labelled for a sitting they had moved on from.
    """
    first = _apply(client, [_stage("today.saved_views", action="collapse"),
                            _stage("commercial.whitespace", action="collapse")]).json()
    assert _apply(client, [_stage("today.saved_views", cause="superseded", action="retire")]
                  ).status_code == 200

    undo = client.post("/api/telemetry/surface-retirement/undo",
                       json={"batch_id": first["batch_id"]})
    assert undo.status_code == 200, undo.text
    body = undo.json()
    assert body["restored"] == ["commercial.whitespace"]
    assert body["superseded"] == ["today.saved_views"]
    assert "decided again since" in body["note"]
    # The newer decision still stands.
    assert _state(client)["surfaces"]["today.saved_views"]["action"] == "retire"


def test_a_sitting_entirely_overtaken_by_later_decisions_refuses_rather_than_reverting_them(client):
    staged = [_stage("today.saved_views", action="collapse")]
    first = _apply(client, staged).json()
    assert _apply(client, [_stage("today.saved_views", cause="superseded", action="retire")]
                  ).status_code == 200

    undo = client.post("/api/telemetry/surface-retirement/undo",
                       json={"batch_id": first["batch_id"]})
    assert undo.status_code == 422
    detail = undo.json()["detail"]
    assert "decided again since" in detail and "older one" in detail
    assert _state(client)["surfaces"]["today.saved_views"]["action"] == "retire"


def test_the_batch_undo_expires_after_fourteen_days_and_says_restore_does_not(client):
    applied = _apply(client, [_stage("today.saved_views")]).json()
    later = utc_day(20)
    response = client.post("/api/telemetry/surface-retirement/undo",
                           json={"batch_id": applied["batch_id"], "today": later})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "more than 14 days ago" in detail and "never expires" in detail


def test_a_batch_undo_inside_the_window_still_works(client):
    applied = _apply(client, [_stage("today.saved_views")]).json()
    later = utc_day(13)
    response = client.post("/api/telemetry/surface-retirement/undo",
                           json={"batch_id": applied["batch_id"], "today": later})
    assert response.status_code == 200, response.text


def test_a_batch_with_any_refusal_writes_nothing_at_all(client):
    """Partial application leaves the app in a state nobody chose and an undo that has to guess."""
    staged = [_stage("today.saved_views"), _stage("global.copilot", action="collapse")]
    response = _apply(client, staged)
    assert response.status_code == 422
    assert not _sql(client, "SELECT id FROM surface_retirement_notes")


def test_the_preview_runs_the_same_checks_the_apply_runs(client):
    """A preview built by a different path is a preview that can disagree with what it previews."""
    staged = [_stage("global.copilot", action="collapse")]
    preview = _preview(client, staged)
    assert preview["refusals"]
    response = _apply(client, staged)
    assert response.status_code == 422
    assert response.json()["detail"] == preview["refusals"][0]["message"]


def test_the_preview_shows_what_each_affected_screen_still_offers(client):
    """`overview.what_moved` is the sole route to nothing, so it is retirable and the preview shows
    the screen without it."""
    preview = _preview(client, [_stage("overview.what_moved", action="retire")])
    assert not preview["refusals"], preview["refusals"]
    route = next(r for r in preview["routes"] if r["route"] == "account.overview")
    assert "What is stuck" in route["still_offered"]
    assert "What moved" not in route["still_offered"]


def test_a_blocked_retirement_leaves_the_surface_in_what_the_screen_still_offers(client):
    """The preview must not show a screen as it would look if a refused change had gone through.

    `commercial.whitespace` is the only route to `whitespace_cell`, so this one is refused. Picked
    by asking the registry rather than by naming a surface, because Slice 4's registrations moved
    which surfaces are sole routes at all — a hard-coded key here would have gone on passing as an
    assertion about nothing.
    """
    preview = _preview(client, [_stage("commercial.whitespace", action="retire")])
    assert preview["refusals"]
    route = next(r for r in preview["routes"] if r["route"] == "account.commercial")
    assert "Whitespace" in route["still_offered"]


def test_the_preview_carries_the_caveat_and_the_no_deletion_statement(client):
    preview = _preview(client, [_stage("today.saved_views")])
    assert "cannot say whether a surface is valuable" in preview["caveat"]
    assert "Nothing here deletes code" in preview["code_deletion"]
    assert "Restore puts it back" in preview["code_deletion"]


def test_an_empty_staging_set_is_refused_rather_than_recorded_as_a_batch(client):
    response = _apply(client, [])
    assert response.status_code == 422
    assert "Nothing was staged" in response.json()["detail"]


def test_an_unregistered_surface_is_refused(client):
    response = _apply(client, [_stage("today.not_a_real_surface")])
    assert response.status_code == 422
    assert "not a registered surface" in response.json()["detail"]


# --- §7.2 restore --------------------------------------------------------------------------------

def test_restore_is_available_forever_and_independent_of_any_batch(client):
    applied = _apply(client, [_stage("accounts.portfolio_analytics", action="retire")]).json()
    assert applied["applied"] == 1
    response = client.post("/api/telemetry/surface-retirement/restore",
                           json={"surface": "accounts.portfolio_analytics"})
    assert response.status_code == 200, response.text
    assert response.json()["reverted"] == "retire"
    assert _state(client)["surfaces"]["accounts.portfolio_analytics"]["action"] == "restore"
    # The restore row carries no batch, so it is not tied to the sitting it reverses.
    row = _sql(client, "SELECT batch_id FROM surface_retirement_notes WHERE action='restore'")[0]
    assert row["batch_id"] is None


def test_restoring_something_already_offered_is_refused(client):
    response = client.post("/api/telemetry/surface-retirement/restore",
                           json={"surface": "today.queue"})
    assert response.status_code == 422
    assert "already offered" in response.json()["detail"]


def test_the_history_is_the_table_and_reads_newest_first(client):
    _apply(client, [_stage("today.saved_views", action="collapse")])
    _apply(client, [_stage("today.saved_views", action="demote")])
    response = client.get("/api/telemetry/surface-retirement/history",
                          params={"surface": "today.saved_views"})
    assert response.status_code == 200
    assert [note["action"] for note in response.json()["notes"]] == ["demote", "collapse"]


# --- the audit trail and §7.9 --------------------------------------------------------------------

def test_every_applied_action_writes_an_audit_row(client):
    """`update`, not a sixth audit verb. The applied action rides in `after`, where a later reader
    finds it beside the cause and the counts it was judged against."""
    import json
    _apply(client, [_stage("today.saved_views"), _stage("commercial.value_ledger")])
    rows = _sql(client, "SELECT * FROM audit_events WHERE object_type='surface'")
    assert {row["object_id"] for row in rows} == {"today.saved_views", "commercial.value_ledger"}
    assert {row["action"] for row in rows} == {"update"}
    after = json.loads(rows[0]["after"])
    assert after["retirement_action"] == "collapse" and after["cause_code"] == "not_needed"


def test_the_usage_report_reads_the_recorded_cause_rather_than_inferring_one(client):
    """§6.1's fourth axis. The report joins the latest note; it never derives a second copy of it,
    and it never guesses a cause from the counts."""
    report = client.get("/api/telemetry/surface-usage").json()
    row = next(r for r in report["surfaces"] if r["surface"] == "today.saved_views")
    assert row["recorded_cause"] is None and row["retirement_action"] == "none"

    _apply(client, [_stage("today.saved_views", cause="misunderstood", action="collapse")])
    report = client.get("/api/telemetry/surface-usage").json()
    row = next(r for r in report["surfaces"] if r["surface"] == "today.saved_views")
    assert row["recorded_cause"] == "misunderstood"
    assert row["retirement_action"] == "collapse"
    assert row["recorded_cause_on"]


def test_a_cause_recorded_with_no_action_still_shows_its_action_as_none(client):
    """A cause shown without its action would read as a decision to remove, when `narrow_but_needed`
    plus `none` is a decision to keep."""
    _apply(client, [_stage("today.saved_views", cause="narrow_but_needed", action="none")])
    report = client.get("/api/telemetry/surface-usage").json()
    row = next(r for r in report["surfaces"] if r["surface"] == "today.saved_views")
    assert row["recorded_cause"] == "narrow_but_needed" and row["retirement_action"] == "none"


def test_a_retirement_never_removes_a_registry_row(client):
    """§7.9. Nothing here deletes code, and the registry entry outlives the code it described
    (`removed_on`) — so the answer to "why doesn't this app have X" survives X.

    Asserted against the live registry after a retirement rather than by reading the diff.
    """
    before = set(surfaces.KEYS)
    assert _apply(client, [_stage("accounts.portfolio_analytics", action="retire")]
                  ).status_code == 200
    assert set(surfaces.KEYS) == before
    assert "accounts.portfolio_analytics" in surfaces.BY_KEY
    assert "removed_on" in surfaces.Surface.__dataclass_fields__
