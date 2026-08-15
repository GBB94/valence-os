"""Phase 3 Stage 4 — communications ingestion + shared association engine (Comprehensive Spec Part 4).
Email sync (.eml fixtures) -> comm records + priority flags; recording ingest -> draft interaction +
extraction, low-confidence -> capture inbox; corrections teach the association engine; the
unanswered-email queue trigger.
"""
import os
import tempfile

import pytest
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


@pytest.fixture()
def scene(client):
    """Bluepeak-like account whose people match the .eml fixtures' addresses."""
    a = client.post("/api/accounts", json={"name": "Bluepeak"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Launch", "phase": "launch"}).json()
    aisha = client.post("/api/persons", json={"name": "Aisha Kone", "account_id": a["id"],
                                              "email": "aisha.kone@example-bluepeak.test"}).json()
    client.post("/api/stakeholder-roles", json={"program_id": p["id"], "person_id": aisha["id"], "role": "champion"})
    return {"c": client, "a": a, "p": p, "aisha": aisha}


# --- §4.2/§4.3 email sync + priority flagging -------------------------------

def test_sync_ingests_emails_and_flags_priority(scene):
    c, a = scene["c"], scene["a"]
    res = c.post("/api/ingest/emails/sync").json()
    assert res["status"] == "succeeded"
    assert res["result"]["created"] >= 3
    comms = c.get(f"/api/accounts/{a['id']}/comms").json()["comms"]
    # Aisha's email resolved to Bluepeak by address, and her question was flagged. Selected by
    # message id, not sender: she also sent the threaded reply (fixture 004), and that message
    # asks nothing — flagging it would be the quoted-history re-flag §14.8 exists to prevent.
    aisha_msg = next(m for m in comms if m["message_id"] == "fixture-001@example-bluepeak.test")
    assert aisha_msg["needs_response"] is True and "question" in aisha_msg["flag_reason"]
    assert aisha_msg["confidence"] >= 0.9 and aisha_msg["summary"]
    # the newsletter is noise — not flagged
    flagged = c.get("/api/comms/flagged").json()["comms"]
    assert all("newsletter" not in (m["from_addr"] or "") for m in flagged)


def test_sync_is_idempotent(scene):
    c = scene["c"]
    c.post("/api/ingest/emails/sync")
    again = c.post("/api/ingest/emails/sync").json()
    assert again["result"]["created"] == 0 and again["result"]["skipped"] >= 3


def test_unanswered_email_fires_into_today(scene):
    c = scene["c"]
    c.post("/api/ingest/emails/sync")
    q = c.get("/api/queue").json()
    email_items = [i for i in q["items"] if i["trigger_type"] == "unanswered_email"]
    assert email_items and any("unanswered" in i["because"] for i in email_items)
    # marking responded clears it
    comm_id = c.get("/api/comms/flagged").json()["comms"][0]["id"]
    c.post(f"/api/comms/{comm_id}/responded")
    q2 = c.get("/api/queue").json()
    assert not any(i["object_id"] == comm_id for i in q2["items"])


# --- §4.5 association corrections teach the engine --------------------------

def test_correction_teaches_association_hint(scene):
    c, a, p = scene["c"], scene["a"], scene["p"]
    c.post("/api/ingest/emails/sync")
    # procurement@ matched no person/keyword -> unresolved, surfaced for triage (never guessed)
    unresolved = c.get("/api/comms/unresolved").json()["comms"]
    proc = next(m for m in unresolved if "procurement" in m["from_addr"])
    person = c.post("/api/persons", json={"name": "Procurement Desk", "account_id": a["id"],
                                          "email": "procurement@example-bluepeak.test"}).json()
    c.post(f"/api/comms/{proc['id']}/associate", json={"account_id": a["id"], "person_id": person["id"]})
    # the hint now resolves that address directly (association engine learned)
    from app import association
    conn = c.app.state.conn
    res = association.resolve(conn, emails=["procurement@example-bluepeak.test"])
    assert res["person_id"] == person["id"] and res["confidence"] >= 0.9


# --- §4.1 recording ingest via the job table --------------------------------

def test_recording_ingest_creates_interaction_and_extraction(scene):
    c, a, p = scene["c"], scene["a"], scene["p"]
    res = c.post("/api/ingest/recording", json={
        "reference": "kickoff-call.txt", "attendees": ["Aisha Kone"], "keywords": ["bluepeak"]}).json()
    assert res["status"] == "succeeded"
    r = res["result"]
    assert r["status"] == "ingested" and r["account_id"] == a["id"]
    assert r["proposals"] >= 3          # commitment/decision/risk/task cues in the fixture
    assert r["needs_triage"] is False   # Aisha matched by name -> confident
    board = c.get(f"/api/programs/{p['id']}/execution").json()
    assert sum(len(v) for v in board.values()) == 0   # extraction proposes; nothing writes unaccepted


def test_low_confidence_recording_lands_in_inbox(scene):
    c, a = scene["c"], scene["a"]
    # unknown attendee + a keyword that still resolves the account, but weakly
    res = c.post("/api/ingest/recording", json={
        "reference": "kickoff-call.txt", "attendees": ["Unknown Person"], "keywords": ["bluepeak"]}).json()
    r = res["result"]
    assert r["status"] == "ingested" and r["needs_triage"] is True
    inbox = c.get("/api/inbox?status=untriaged").json()
    assert any("Low-confidence" in i["raw_text"] for i in inbox)
