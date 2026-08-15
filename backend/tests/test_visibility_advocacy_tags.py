"""VISIBILITY-SPEC §8 — advocacy tags on people (migration 0054).

Five kinds of public-facing advocacy — reference, review, quote, beta participant, speaking — each
carrying a date and an evidence note that the schema requires rather than the UI encourages.

Three things are load-bearing and each has a test that fails loudly if it is undone:

- **The date and the note are structural.** Not "should be filled in": NOT NULL plus a non-empty
  CHECK, so a tag cannot exist without them. §8's phrasing is exact — a tag without them "is not a
  lighter version of the record; it is a different and worse one", because a bare kind on a named
  person is an unevidenced judgement.
- **Nothing here is a level.** No score, no sentiment, no inferred willingness, no rollup. The
  column set is asserted exactly, and the person card returns records rather than a count, because
  "3 advocacy tags" is one short step from an advocacy level.
- **It never feeds the champion gate.** `advocacy_events` answers "does this person advocate for us
  inside their own organisation when we are not in the room". A public quote is not an answer to
  that question, and the two tables stay separate so it can never become one.
"""
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient


KINDS = ["reference", "review", "quote", "beta_participant", "speaking"]

# Everything the table is allowed to hold. The list is the point of the test: a `strength`,
# `level`, `sentiment`, or `score` column added later has to delete a line here first.
COLUMNS = {
    "id", "person_id", "kind", "occurred_on", "evidence_note", "source_reference_id",
    "actor_id", "created_at", "updated_at", "archived", "archived_at", "archived_by",
}


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


def _person(c, name="Ilse Marchetti"):
    account = c.post("/api/accounts", json={"name": "Northwind Synthetic"}).json()
    r = c.post("/api/persons", json={"name": name, "account_id": account["id"]})
    assert r.status_code == 201, r.text
    return account, r.json()


def _tag(c, person_id, **over):
    body = {"person_id": person_id, "kind": "reference", "occurred_on": "2026-06-18",
            "evidence_note": "Agreed on the 18 Jun call to take reference calls for the rollout.",
            **over}
    return c.post("/api/advocacy-tags", json=body)


def _conn(c):
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    return conn


# --- the record ---------------------------------------------------------------------------------

def test_every_kind_records_with_a_date_and_an_evidence_note(client):
    _, person = _person(client)
    for kind in KINDS:
        r = _tag(client, person["id"], kind=kind)
        assert r.status_code == 201, (kind, r.text)
        tag = r.json()
        assert tag["kind"] == kind
        assert tag["occurred_on"] == "2026-06-18"
        assert tag["evidence_note"]
        # The operator-facing name, so a raw enum never reaches a screen.
        assert tag["kind_label"] == {
            "reference": "Reference", "review": "Review", "quote": "Quote",
            "beta_participant": "Beta participant", "speaking": "Speaking"}[kind]


def test_a_tag_without_a_date_or_a_note_is_refused(client):
    """§8. Not softened to a warning: the record cannot be created."""
    _, person = _person(client)
    for missing in ("occurred_on", "evidence_note"):
        body = {"person_id": person["id"], "kind": "quote",
                "occurred_on": "2026-06-18", "evidence_note": "Quoted in the rollout summary."}
        body.pop(missing)
        assert client.post("/api/advocacy-tags", json=body).status_code == 422, missing
        # An empty string is the same refusal. NOT NULL alone is satisfied by "", which is how a
        # required field quietly becomes an optional one.
        assert _tag(client, person["id"], **{missing: ""}).status_code == 422, missing
        assert _tag(client, person["id"], **{missing: "   "}).status_code == 422, missing


def test_the_database_refuses_the_same_record_the_api_does(client):
    """The schema is the guarantee, not the request model. A future writer that bypasses the
    router must hit the same wall — otherwise the constraint lives in one code path only."""
    _, person = _person(client)
    conn = _conn(client)
    try:
        for values in (("x1", person["id"], "quote", None, "note"),
                       ("x2", person["id"], "quote", "2026-06-18", None),
                       ("x3", person["id"], "quote", "", "note"),
                       ("x4", person["id"], "quote", "2026-06-18", "  "),
                       ("x5", person["id"], "advocacy_level", "2026-06-18", "note")):
            with pytest.raises(sqlite3.IntegrityError):
                with conn:
                    conn.execute(
                        "INSERT INTO advocacy_tags (id, person_id, kind, occurred_on, "
                        "evidence_note, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                        (*values, "2026-06-18T00:00:00Z", "2026-06-18T00:00:00Z"))
    finally:
        conn.close()


def test_an_unknown_kind_is_refused_and_there_is_no_other(client):
    """§9's escape-hatch rule. `other: very keen` is a sentiment in a field nobody validates."""
    _, person = _person(client)
    assert _tag(client, person["id"], kind="other").status_code == 422
    assert _tag(client, person["id"], kind="enthusiastic").status_code == 422
    body = client.get(f"/api/persons/{person['id']}/advocacy-tags").json()
    assert body["kinds"] == KINDS


# --- what the table may not hold ----------------------------------------------------------------

def test_the_table_holds_no_score_level_or_sentiment(client):
    conn = _conn(client)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(advocacy_tags)")}
    finally:
        conn.close()
    assert cols == COLUMNS, cols ^ COLUMNS
    for banned in ("level", "score", "strength", "sentiment", "enthusiasm", "willingness",
                   "stance", "rating", "tier", "confidence"):
        assert not [c for c in cols if banned in c], banned


def test_nothing_here_reads_or_implies_individual_product_usage(client):
    """The §2 trust boundary. Deployment engagement is permitted by name; usage is not, and this
    table has no column that could hold it and no route that joins one."""
    conn = _conn(client)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(advocacy_tags)")}
    finally:
        conn.close()
    for banned in ("usage", "last_seen", "sessions", "logins", "active", "seat", "adoption"):
        assert not [c for c in cols if banned in c], banned


def test_the_person_card_returns_records_not_a_count(client):
    """A count is a rollup, and a rollup of dated evidence is where a level comes from."""
    _, person = _person(client)
    _tag(client, person["id"], kind="speaking", occurred_on="2026-05-02",
         evidence_note="Spoke on the enablement panel; agenda in the event source reference.")
    _tag(client, person["id"], kind="review", occurred_on="2026-07-11",
         evidence_note="Posted a review on the partner directory, captured 11 Jul.")

    card = client.get(f"/api/persons/{person['id']}/card").json()
    tags = card["advocacy_tags"]
    assert [t["kind"] for t in tags] == ["review", "speaking"]   # newest first
    for tag in tags:
        assert tag["occurred_on"] and tag["evidence_note"]
    for banned in ("advocacy_level", "advocacy_score", "advocacy_count", "advocacy_strength"):
        assert banned not in card, banned


# --- the separation from the champion gate -------------------------------------------------------

def test_a_public_tag_is_not_champion_evidence(client):
    """The reason this is a second table. `advocacy_events` answers a question about behaviour
    inside the customer's organisation; a conference talk is not an answer to it, and widening the
    older table's CHECK would have made it one in four evaluators at once."""
    from app import people_core

    _, person = _person(client)
    for kind in KINDS:
        _tag(client, person["id"], kind=kind)

    conn = _conn(client)
    try:
        assert people_core.has_champion_evidence(conn, person["id"]) is False
        # And the older table never acquired the new vocabulary.
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'advocacy_events'").fetchone()["sql"]
        for kind in KINDS:
            assert f"'{kind}'" not in sql, kind
    finally:
        conn.close()


def test_the_two_arrays_stay_separate_on_the_card(client):
    """One combined array is how the public tag starts satisfying the internal question."""
    _, person = _person(client)
    _tag(client, person["id"], kind="quote")
    r = client.post("/api/advocacy-events", json={
        "person_id": person["id"], "kind": "defended_us", "occurred_on": "2026-06-01",
        "note": "Defended the rollout timeline in their steering meeting."})
    assert r.status_code == 201, r.text

    card = client.get(f"/api/persons/{person['id']}/card").json()
    assert [e["kind"] for e in card["advocacy"]] == ["defended_us"]
    assert [t["kind"] for t in card["advocacy_tags"]] == ["quote"]
