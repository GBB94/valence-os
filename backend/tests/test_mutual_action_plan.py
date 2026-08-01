"""Mutual Action Plan (Section 5N) — promotion flag + by-construction client-facing view."""
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


def test_map_empty_until_items_promoted(scene):
    c, a = scene["c"], scene["a"]
    m = c.get(f"/api/accounts/{a['id']}/map").json()
    assert m["items"] == [] and "No items have been shared" in m["markdown"]


def test_promote_puts_item_on_map_by_construction(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/map/promote", json={"object_type": "commitment", "object_id": scene["cm"]["id"], "client_visible": True})
    c.post("/api/map/promote", json={"object_type": "milestone", "object_id": scene["ms"]["id"], "client_visible": True})
    m = c.get(f"/api/accounts/{a['id']}/map").json()
    whats = [i["what"] for i in m["items"]]
    assert "Client to secure DPO sign-off" in whats and "Europe go-live" in whats
    # the un-promoted INTERNAL commitment is excluded by construction
    assert "INTERNAL: prep board memo" not in whats
    assert "INTERNAL" not in m["markdown"]
    # promoted commitment shows the responsible party (client), stamped
    assert m["stamp"]["data_current_through"]
    assert any(i["owner"] == "Sofie" for i in m["items"] if i["type"] == "commitment")


def test_demote_removes_from_map(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/map/promote", json={"object_type": "commitment", "object_id": scene["cm"]["id"], "client_visible": True})
    assert len(c.get(f"/api/accounts/{a['id']}/map").json()["items"]) == 1
    c.post("/api/map/promote", json={"object_type": "commitment", "object_id": scene["cm"]["id"], "client_visible": False})
    assert c.get(f"/api/accounts/{a['id']}/map").json()["items"] == []


def test_client_visible_defaults_off(scene):
    # execution board exposes the flag; new items default to not-on-plan
    board = scene["c"].get(f"/api/programs/{scene['p']['id']}/execution").json()
    assert all(cm["client_visible"] is False for cm in board["commitments"])


def test_unsourced_item_cannot_be_promoted(scene):
    r = scene["c"].post("/api/map/promote", json={
        "object_type": "commitment", "object_id": scene["internal"]["id"], "client_visible": True})
    assert r.status_code == 422 and "source" in r.json()["detail"]
