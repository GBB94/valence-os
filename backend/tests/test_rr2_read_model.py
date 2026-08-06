"""Acceptance tests for RELATIONSHIP-READINESS-SPEC.md §7.2, §8.1, and §0.5 — the read model.

The thing that can go wrong here is subtler than a bad query. §0.5 forbids copying extraction
proposals into `capture_inbox_items`, and the tempting shortcut is not an INSERT — it is a response
shape that merges the two into one list with one status vocabulary. That reads as one store, and a
reader who cannot tell the two apart cannot tell which command applies. These tests assert the two
stay distinguishable in the response, that nothing is written on a read, and that the Today item
counts accounts rather than proposals.
"""
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

from app import proposal_read


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


TRANSCRIPT = ("Action item: publish the rollout plan. "
              "We decided to start with the support org. "
              "The blocker is that SSO is not provisioned yet.")
OTHER_TRANSCRIPT = "Action item: schedule the SSO workshop."


def _account(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _program(c, account_id, name="Launch"):
    return c.post("/api/programs", json={"account_id": account_id, "name": name,
                                         "phase": "launch"}).json()


def _interaction(c, account_id, program_id=None, notes=(), occurred_on=None):
    r = c.post("/api/interactions", json={"account_id": account_id, "program_id": program_id,
                                          "occurred_on": occurred_on, "summary": "Weekly sync",
                                          "inbox_notes": list(notes)})
    assert r.status_code == 201, r.text
    return r.json()


def _run(c, account_id, program_id=None, transcript=TRANSCRIPT, interaction_id=None):
    r = c.post("/api/extraction/run", json={"transcript": transcript, "account_id": account_id,
                                            "program_id": program_id, "backend": "mock",
                                            "interaction_id": interaction_id})
    assert r.status_code == 201, r.text
    return r.json()


def _exec_sql(client, sql, params=()):
    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def _all_proposals(payload):
    return [p for g in payload["groups"] for t in g["targets"] for p in t["proposals"]]


# --- §0.5: composition, not duplication -----------------------------------------------------------

def test_combined_view_does_not_copy_proposals_into_the_capture_inbox(client):
    """The exit criterion, checked where it actually fails: the row count after a read.

    A read model that "materializes" for convenience is the second persistence model §6.1 bans,
    and it would only be visible in the table — the response would look identical.
    """
    a = _account(client)
    inter = _interaction(client, a["id"], notes=["Ask about the security review"])
    _run(client, a["id"], interaction_id=inter["id"])

    before = _exec_sql(client, "SELECT COUNT(*) c FROM capture_inbox_items")[0]["c"]
    r = client.get(f"/api/accounts/{a['id']}/proposed-updates")
    assert r.status_code == 200, r.text
    after = _exec_sql(client, "SELECT COUNT(*) c FROM capture_inbox_items")[0]["c"]

    assert before == after == 1
    body = r.json()
    assert body["counts"]["proposals"] >= 3
    assert body["counts"]["manual_capture"] == 1


def test_manual_notes_and_proposals_stay_distinguishable_in_one_response(client):
    """§0.5's "read-model composition" — one experience, two vocabularies, two command sets.

    Restating an `untriaged` note as `proposed` would be the merge in everything but the schema.
    """
    a = _account(client)
    inter = _interaction(client, a["id"], notes=["Ask about the security review"])
    _run(client, a["id"], interaction_id=inter["id"])

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()
    note = body["manual_capture"][0]
    assert note["kind"] == "capture_item"
    assert note["status"] == "untriaged"                 # not "proposed"
    assert note["commands"] == ["convert", "dismiss"]    # not accept/reject/use_existing
    # A hand-typed line has no intent, target, or citation. Inventing them would make an operator's
    # own note look machine-cited.
    assert not {"intent", "target_type", "source", "proposal_fingerprint"} & set(note)

    for p in _all_proposals(body):
        assert p["kind"] == "extraction_proposal"
        assert p["status"] == "proposed"
        assert p["intent"] and p["target_type"] and p["source"]["span"]


# --- §7.2: grouping, provenance, warnings, conflicts, candidates -----------------------------------

def test_grouping_is_by_run_not_by_interaction(client):
    """Two reads of one meeting are two sources. Collapsing them would hide that some proposals
    came from superseded material — which is the whole reason a source version key exists."""
    a = _account(client)
    inter = _interaction(client, a["id"])
    first = _run(client, a["id"], interaction_id=inter["id"])
    second = _run(client, a["id"], interaction_id=inter["id"], transcript=OTHER_TRANSCRIPT)

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()
    run_ids = [g["source"]["run_id"] for g in body["groups"]]
    assert sorted(run_ids) == sorted([first["id"], second["id"]])
    hashes = {g["source"]["content_hash"] for g in body["groups"]}
    assert len(hashes) == 2, "different material must not share a source identity"
    for g in body["groups"]:
        assert g["source"]["interaction_id"] == inter["id"]
        assert g["source"]["interaction"]["occurred_on"]


def test_each_group_is_split_by_target_type_and_counts_are_derived(client):
    a = _account(client)
    _run(client, a["id"])
    body = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()

    group = body["groups"][0]
    types = [t["target_type"] for t in group["targets"]]
    assert types == sorted(types), "target groups are ordered, not insertion-dependent"
    assert len(set(types)) == len(types)
    assert group["count"] == sum(t["count"] for t in group["targets"])
    assert body["counts"]["proposals"] == sum(g["count"] for g in body["groups"])
    assert sum(body["counts"]["by_target_type"].values()) == body["counts"]["proposals"]
    # Nothing stores these. The response is the only place they exist — a stored count is the
    # second source of truth that drifts the first time a proposal is resolved elsewhere.
    cols = {c["name"] for c in _exec_sql(client, "PRAGMA table_info(extraction_runs)")}
    assert not (cols & {"proposal_count", "pending_count", "accepted_count", "counts_json"}), cols


def test_provenance_is_exact_enough_to_re_find_the_source(client):
    a = _account(client)
    _run(client, a["id"])
    src = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()["groups"][0]["source"]
    assert src["kind"] == "transcript"
    assert src["content_hash"].startswith("sha256:")
    assert src["extractor"]["backend"] == "mock"
    assert src["extractor"]["model_version"] and src["extractor"]["prompt_version"]


def test_every_proposal_carries_its_warnings_conflict_and_candidates(client):
    """§7.2 names all three. An absent key is not the same as an empty one: the UI cannot tell
    "no conflict" from "not computed" if the field is missing."""
    a = _account(client)
    _run(client, a["id"])
    for p in _all_proposals(client.get(f"/api/accounts/{a['id']}/proposed-updates").json()):
        assert p["validation_warnings"] == []
        assert "conflict" in p and p["conflict"] is None   # creates have nothing to conflict with
        assert isinstance(p["match_candidates"], list)


def test_a_duplicate_create_surfaces_as_a_candidate_not_as_a_merge(client):
    """§6.7's closing line — candidates are suggestions. The second proposal must still be there."""
    a = _account(client)
    prog = _program(client, a["id"])
    first = _run(client, a["id"], program_id=prog["id"])
    task = next(p for p in first["proposals"] if p["target_type"] == "task")
    assert client.post(f"/api/extraction/proposals/{task['id']}/accept",
                       json={}).status_code == 200
    _run(client, a["id"], program_id=prog["id"])           # same transcript, same sentences

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()
    twins = [p for p in _all_proposals(body) if p["target_type"] == "task"]
    assert len(twins) == 1, "the accepted one is gone from the pending view, the new one is not"
    checks = {c["check"] for c in twins[0]["match_candidates"]}
    assert "identical_source_proposal" in checks or "exact_content" in checks
    assert twins[0]["status"] == "proposed", "a candidate never resolves anything by itself"


# --- Scope ----------------------------------------------------------------------------------------

def test_the_read_model_never_crosses_an_account(client):
    a, b = _account(client), _account(client, "Contoso Synthetic")
    _run(client, a["id"])
    _run(client, b["id"], transcript=OTHER_TRANSCRIPT)

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()
    run_ids = {g["source"]["run_id"] for g in body["groups"]}
    other = {r["id"] for r in _exec_sql(client, "SELECT id FROM extraction_runs WHERE account_id=?",
                                        (b["id"],))}
    assert not (run_ids & other)


def test_a_program_filter_excludes_account_level_runs(client):
    """A run with no program is account-level work, not work in every program. Sweeping it into a
    program view would attribute it to a program nobody chose."""
    a = _account(client)
    prog = _program(client, a["id"])
    account_level = _run(client, a["id"])
    in_program = _run(client, a["id"], program_id=prog["id"], transcript=OTHER_TRANSCRIPT)

    scoped = client.get(f"/api/accounts/{a['id']}/proposed-updates",
                        params={"program_id": prog["id"]}).json()
    ids = {g["source"]["run_id"] for g in scoped["groups"]}
    assert ids == {in_program["id"]}
    unscoped = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()
    assert {g["source"]["run_id"] for g in unscoped["groups"]} == {account_level["id"], in_program["id"]}


def test_a_foreign_program_is_a_scoped_error_not_an_account_wide_fallback(client):
    a, b = _account(client), _account(client, "Contoso Synthetic")
    _run(client, a["id"])
    assert client.get(f"/api/accounts/{a['id']}/proposed-updates",
                      params={"program_id": "no-such-program"}).status_code == 404
    other_prog = _program(client, b["id"])
    scoped = client.get(f"/api/accounts/{a['id']}/proposed-updates",
                        params={"program_id": other_prog["id"]}).json()
    assert scoped["groups"] == []


def test_status_filter_keeps_resolved_history_readable(client):
    """An RR-2 exit criterion: existing accepted/rejected history remains readable. It must not
    need a second endpoint, and it must not leak back into the default pending view."""
    a = _account(client)
    prog = _program(client, a["id"])
    run = _run(client, a["id"], program_id=prog["id"])
    task = next(p for p in run["proposals"] if p["target_type"] == "task")
    assert client.post(f"/api/extraction/proposals/{task['id']}/accept",
                       json={}).status_code == 200

    pending = client.get(f"/api/accounts/{a['id']}/proposed-updates").json()
    assert task["id"] not in {p["id"] for p in _all_proposals(pending)}
    every = client.get(f"/api/accounts/{a['id']}/proposed-updates", params={"status": "all"}).json()
    accepted = next(p for p in _all_proposals(every) if p["id"] == task["id"])
    assert accepted["status"] == "accepted"
    assert accepted["resolved_target"]["id"]
    assert set(every["counts"]["by_status"]) == {"proposed", "accepted"}


def test_source_interaction_filter_narrows_both_lists(client):
    a = _account(client)
    one = _interaction(client, a["id"], notes=["Note on the first call"])
    two = _interaction(client, a["id"], notes=["Note on the second call"])
    _run(client, a["id"], interaction_id=one["id"])
    _run(client, a["id"], interaction_id=two["id"], transcript=OTHER_TRANSCRIPT)

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates",
                      params={"source_interaction_id": one["id"]}).json()
    assert {g["source"]["interaction_id"] for g in body["groups"]} == {one["id"]}
    assert [n["text"] for n in body["manual_capture"]] == ["Note on the first call"]


# --- §8.1 preview ---------------------------------------------------------------------------------

def test_preview_shows_at_most_three_from_the_latest_source_but_counts_them_all(client):
    """Three cards must never imply three items of work — hence a scope-wide `pending_count`
    alongside a bounded preview and an explicit `truncated`."""
    a = _account(client)
    older = _run(client, a["id"], transcript=OTHER_TRANSCRIPT)
    newest = _run(client, a["id"])

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates/preview").json()
    assert body["latest_source"]["run_id"] == newest["id"]
    assert len(body["proposals"]) <= 3
    assert body["pending_count"] == len(newest["proposals"]) + len(older["proposals"])
    assert body["pending_count"] > len(body["proposals"])
    assert body["truncated"] is True
    assert body["review_all_href"].endswith(f"/accounts/{a['id']}/proposed-updates")


def test_preview_is_empty_and_honest_when_nothing_is_pending(client):
    a = _account(client)
    body = client.get(f"/api/accounts/{a['id']}/proposed-updates/preview").json()
    assert body == {"account_id": a["id"], "program_id": None, "pending_count": 0,
                    "latest_source": None, "proposals": [], "truncated": False,
                    "review_all_href": f"/api/accounts/{a['id']}/proposed-updates"}


def test_preview_skips_a_run_whose_proposals_are_all_resolved(client):
    """"Latest" means the latest source with work left, not the latest source. A card showing an
    empty run would report nothing to do while an older run still had a backlog."""
    a = _account(client)
    older = _run(client, a["id"], transcript=OTHER_TRANSCRIPT)
    newest = _run(client, a["id"])
    for p in newest["proposals"]:
        assert client.post(f"/api/extraction/proposals/{p['id']}/reject",
                           json={"reason": "Not what was said."}).status_code == 200

    body = client.get(f"/api/accounts/{a['id']}/proposed-updates/preview").json()
    assert body["latest_source"]["run_id"] == older["id"]
    assert body["pending_count"] == len(older["proposals"])


# --- §8.1 review debt ----------------------------------------------------------------------------

def test_review_debt_is_one_item_per_account_not_per_run(client):
    """Reviewing a backlog is one piece of work on one surface. Five items would be four lies about
    how much is waiting."""
    a = _account(client)
    _run(client, a["id"])
    _run(client, a["id"], transcript=OTHER_TRANSCRIPT)
    _exec_sql(client, "UPDATE extraction_proposals SET created_at = date('now','-30 days')")

    items = [i for i in client.get("/api/queue").json()["items"]
             if i["trigger_type"] == "proposal_review_debt"]
    assert len(items) == 1
    assert items[0]["account_id"] == a["id"]
    assert items[0]["object_type"] == "account"
    assert "review" in items[0]["title"].lower()
    assert items[0]["next_action"]


def test_review_debt_stays_quiet_below_both_thresholds(client):
    """A handful of proposals drafted this morning is not debt. A Today item that fires on arrival
    would train the operator to ignore the surface."""
    a = _account(client)
    run = _run(client, a["id"])
    assert 0 < len(run["proposals"]) < proposal_read.REVIEW_DEBT_COUNT
    items = [i for i in client.get("/api/queue").json()["items"]
             if i["trigger_type"] == "proposal_review_debt"]
    assert items == []


def test_review_debt_fires_on_volume_without_waiting_for_age(client):
    a = _account(client)
    for _ in range(4):
        _run(client, a["id"])
    debt = proposal_read.review_debt(_conn(client))
    assert len(debt) == 1
    assert debt[0]["pending"] >= proposal_read.REVIEW_DEBT_COUNT
    assert debt[0]["thresholds_breached"] == ["count"]


def test_resolved_proposals_stop_counting_as_debt(client):
    a = _account(client)
    run = _run(client, a["id"])
    _exec_sql(client, "UPDATE extraction_proposals SET created_at = date('now','-30 days')")
    assert proposal_read.review_debt(_conn(client))
    for p in run["proposals"]:
        client.post(f"/api/extraction/proposals/{p['id']}/reject", json={"reason": "Misheard."})
    assert proposal_read.review_debt(_conn(client)) == []


def _conn(client):
    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    return conn
