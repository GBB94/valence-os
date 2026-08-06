"""Mutual Action Plan — promotion flag + by-construction client-facing view.

Originally written against template v1's flat mixed table (Section 5N). ACCOUNT-PATH-SPEC.md §16.5
replaced that with a grouped plan and a `{artifact, diagnostics}` response, so the assertions below
were rewritten against the new contract. Their intent is unchanged: promotion is affirmative, an
unsourced record cannot be promoted, and an unpromoted one is absent by construction rather than by
filtering.
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
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


@pytest.fixture()
def scene(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Europe"}).json()
    resp = client.post("/api/persons", json={"name": "Sofie", "account_id": a["id"]}).json()
    owner = client.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()
    source = client.post("/api/source-references", json={"label": "Joint plan notes"}).json()
    interaction = client.post("/api/interactions", json={
        "account_id": a["id"], "program_id": p["id"], "type": "meeting", "summary": "Plan agreed"}).json()
    cm = client.post("/api/commitments", json={"program_id": p["id"], "description": "Client to secure DPO sign-off",
                                               "responsible_party_id": resp["id"], "internal_owner_id": owner["id"], "due_date": "2026-08-15",
                                               "source_reference_id": source["id"]}).json()
    ms = client.post("/api/milestones", json={"program_id": p["id"], "name": "Europe go-live", "target_date": "2026-09-15",
                                               "source_interaction_id": interaction["id"]}).json()
    internal = client.post("/api/commitments", json={"program_id": p["id"], "description": "INTERNAL: prep board memo",
                                                     "responsible_party_id": owner["id"], "internal_owner_id": owner["id"], "due_date": "2026-08-01"}).json()
    return {"c": client, "a": a, "p": p, "cm": cm, "ms": ms, "internal": internal}


def _artifact(c, account_id):
    r = c.get(f"/api/accounts/{account_id}/map")
    assert r.status_code == 200, r.text
    return r.json()["artifact"]


def _shared_items(artifact):
    return [action for program in artifact["programs"]
            for group in program["groups"] for action in group["actions"]]


def test_map_empty_until_items_promoted(scene):
    artifact = _artifact(scene["c"], scene["a"]["id"])
    assert artifact["programs"] == []
    assert "No items have been shared" in artifact["markdown"]


def test_promote_puts_item_on_map_by_construction(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/map/promote", json={"object_type": "commitment", "object_id": scene["cm"]["id"], "client_visible": True})
    c.post("/api/map/promote", json={"object_type": "milestone", "object_id": scene["ms"]["id"], "client_visible": True})
    artifact = _artifact(c, a["id"])
    assert [i["what"] for i in _shared_items(artifact)] == ["Client to secure DPO sign-off"]
    milestones = [g["milestone"] for p in artifact["programs"] for g in p["groups"]]
    assert "Europe go-live" in milestones
    # the un-promoted INTERNAL commitment is excluded by construction
    assert "INTERNAL: prep board memo" not in str(artifact)
    assert "INTERNAL" not in artifact["markdown"]
    assert artifact["stamp"]["data_current_through"]
    # the responsible party sits on the customer side of the plan, the owner on ours
    item = _shared_items(artifact)[0]
    assert item["customer_owner"] == "Sofie" and item["valence_owner"] == "Sam"


def test_demote_removes_from_map(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/map/promote", json={"object_type": "commitment", "object_id": scene["cm"]["id"], "client_visible": True})
    assert len(_shared_items(_artifact(c, a["id"]))) == 1
    c.post("/api/map/promote", json={"object_type": "commitment", "object_id": scene["cm"]["id"], "client_visible": False})
    assert _shared_items(_artifact(c, a["id"])) == []


def test_client_visible_defaults_off(scene):
    # execution board exposes the flag; new items default to not-on-plan
    board = scene["c"].get(f"/api/programs/{scene['p']['id']}/execution").json()
    assert all(cm["client_visible"] is False for cm in board["commitments"])


def test_unsourced_item_cannot_be_promoted(scene):
    r = scene["c"].post("/api/map/promote", json={
        "object_type": "commitment", "object_id": scene["internal"]["id"], "client_visible": True})
    assert r.status_code == 422 and "source" in r.json()["detail"]
