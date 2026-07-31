"""v0.3 attention tests — acceptance Step 4 (a blocker surfaces in the queue),
the deterministic ranking, snooze/resolve rules, and the two independent statuses.
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
def seeded(client):
    """A small portfolio that fires every v0.3 trigger, clock-independently."""
    acct = client.post("/api/accounts", json={"name": "Acme"}).json()
    prog = client.post("/api/programs", json={"account_id": acct["id"], "name": "Rollout", "phase": "launch"}).json()
    champ = client.post("/api/persons", json={"name": "Dana", "account_id": acct["id"]}).json()
    owner = client.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()
    client.post("/api/stakeholder-roles", json={
        "program_id": prog["id"], "person_id": champ["id"], "role": "champion",
        "stance": "supporter", "stance_assessed_on": "2020-01-01", "stance_evidence_note": "old",
    })
    # a meaningful touch far in the past -> stale stakeholder
    client.post("/api/interactions", json={
        "account_id": acct["id"], "program_id": prog["id"], "type": "call",
        "occurred_on": "2000-01-01", "participant_ids": [champ["id"]],
    })
    client.post("/api/commitments", json={
        "program_id": prog["id"], "description": "overdue commitment",
        "responsible_party_id": owner["id"], "internal_owner_id": owner["id"], "due_date": "2000-01-01",
    })
    client.post("/api/risks", json={"program_id": prog["id"], "description": "blocker risk", "is_blocker": True})
    client.post("/api/milestones", json={"program_id": prog["id"], "name": "Go-live", "at_risk": True})
    client.post("/api/tasks", json={"program_id": prog["id"], "description": "a task"})
    inter = client.post("/api/interactions", json={
        "account_id": acct["id"], "program_id": prog["id"], "type": "call", "inbox_notes": ["triage me"],
    }).json()
    return {"client": client, "acct": acct, "prog": prog, "owner": owner, "inbox_item": inter["inbox_items"][0]}


def _keys_by_trigger(items):
    out = {}
    for it in items:
        out.setdefault(it["trigger_type"], []).append(it)
    return out


def test_queue_fires_every_trigger_with_because(seeded):
    q = seeded["client"].get("/api/queue").json()
    by = _keys_by_trigger(q["items"])
    for trig in ("overdue_commitment", "active_blocker", "at_risk_milestone",
                 "untriaged_inbox", "cadence_overdue", "open_task"):
        assert trig in by, f"missing {trig}"
    assert all(it["because"] for it in q["items"]), "every item must explain itself"
    assert all("next_action" in it and it["next_action"] for it in q["items"])


def test_queue_is_priority_ordered(seeded):
    items = seeded["client"].get("/api/queue").json()["items"]
    priorities = [it["priority"] for it in items]
    assert priorities == sorted(priorities), "items must be ordered by priority band"
    # overdue commitment (band 1) comes before open task (band 6)
    assert items[0]["trigger_type"] == "overdue_commitment"


def test_snooze_requires_date_or_condition(seeded):
    c = seeded["client"]
    key = c.get("/api/queue").json()["items"][0]["key"]
    assert c.post("/api/queue/snooze", json={"item_key": key}).status_code == 422
    ok = c.post("/api/queue/snooze", json={"item_key": key, "snooze_until": "2999-01-01"})
    assert ok.status_code == 200


def test_snooze_hides_item_until_return_date(seeded):
    c = seeded["client"]
    blocker = _keys_by_trigger(c.get("/api/queue").json()["items"])["active_blocker"][0]
    c.post("/api/queue/snooze", json={"item_key": blocker["key"], "snooze_until": "2999-01-01"})
    q = c.get("/api/queue").json()
    assert blocker["key"] not in [i["key"] for i in q["items"]]
    assert blocker["key"] in [i["key"] for i in q["snoozed"]]
    assert q["snoozed_count"] == 1


def test_snooze_with_past_date_resurfaces(seeded):
    c = seeded["client"]
    blocker = _keys_by_trigger(c.get("/api/queue").json()["items"])["active_blocker"][0]
    c.post("/api/queue/snooze", json={"item_key": blocker["key"], "snooze_until": "2000-01-01"})
    q = c.get("/api/queue").json()
    assert blocker["key"] in [i["key"] for i in q["items"]], "past return date must resurface"


def test_resolve_requires_successor_action(seeded):
    c = seeded["client"]
    item = c.get("/api/queue").json()["items"][0]
    # a successor task
    succ = c.post("/api/tasks", json={"program_id": seeded["prog"]["id"], "description": "follow up"}).json()
    ok = c.post("/api/queue/resolve", json={
        "item_key": item["key"], "successor_action_type": "task", "successor_action_id": succ["id"],
    })
    assert ok.status_code == 200
    # resolved item drops out of the active queue
    assert item["key"] not in [i["key"] for i in c.get("/api/queue").json()["items"]]


def test_converting_inbox_note_clears_its_queue_item(seeded):
    c = seeded["client"]
    item_id = seeded["inbox_item"]["id"]
    key = f"untriaged_inbox:capture_inbox_item:{item_id}"
    assert key in [i["key"] for i in c.get("/api/queue").json()["items"]]
    c.post(f"/api/inbox/{item_id}/convert", json={"target_type": "task", "payload": {}})
    assert key not in [i["key"] for i in c.get("/api/queue").json()["items"]]


def test_two_statuses_are_independent(seeded):
    c = seeded["client"]
    aid = seeded["acct"]["id"]
    c.post(f"/api/accounts/{aid}/status", json={"dimension": "delivery", "value": "on_track", "rationale": "adoption to plan"})
    c.post(f"/api/accounts/{aid}/status", json={"dimension": "commercial", "value": "at_risk", "rationale": "expansion unproven"})
    a = c.get(f"/api/accounts/{aid}").json()
    assert a["delivery_status"] == "on_track" and a["commercial_status"] == "at_risk"
    assert a["delivery_status_assessed_on"] and a["commercial_status_assessed_on"]
    # no composite field exists
    assert not any("health" in k or "composite" in k for k in a.keys())
