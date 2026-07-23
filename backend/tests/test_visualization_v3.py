"""v3 tests — graph assessment guard (date+evidence), graph/edge assembly, the
budget waterfall ordering, and metric observation history."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["ACCOUNT_OS_DB"] = path
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


@pytest.fixture()
def scene(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    champ = client.post("/api/persons", json={"name": "Dana", "account_id": a["id"]}).json()
    boss = client.post("/api/persons", json={"name": "Owen", "account_id": a["id"]}).json()
    role = client.post("/api/stakeholder-roles", json={"program_id": p["id"], "person_id": champ["id"], "role": "champion",
                                                       "stance": "supporter", "stance_assessed_on": "2026-07-01", "stance_evidence_note": "e"}).json()
    client.post("/api/stakeholder-roles", json={"program_id": p["id"], "person_id": boss["id"], "role": "budget_owner",
                                                "stance": "skeptic", "stance_assessed_on": "2026-07-01", "stance_evidence_note": "e"})
    return {"c": client, "a": a, "p": p, "champ": champ, "boss": boss, "role": role}


def test_graph_assessment_requires_date_and_evidence(scene):
    c = scene["c"]
    bad = c.patch(f"/api/stakeholder-roles/{scene['role']['id']}/graph", json={"influence": "high"})
    assert bad.status_code == 422
    ok = c.patch(f"/api/stakeholder-roles/{scene['role']['id']}/graph", json={
        "influence": "high", "relationship_strength": "strong",
        "graph_assessed_on": "2026-07-10", "graph_evidence_note": "board access"})
    assert ok.status_code == 200 and ok.json()["influence"] == "high"


def test_graph_nodes_and_edges(scene):
    c = scene["c"]
    c.patch(f"/api/stakeholder-roles/{scene['role']['id']}/graph", json={
        "influence": "high", "graph_assessed_on": "2026-07-10", "graph_evidence_note": "x"})
    c.post("/api/relationship-edges", json={"account_id": scene["a"]["id"], "from_person_id": scene["boss"]["id"],
                                            "to_person_id": scene["champ"]["id"], "type": "reports_to"})
    g = c.get(f"/api/accounts/{scene['a']['id']}/stakeholder-graph").json()
    dana = next(n for n in g["nodes"] if n["name"] == "Dana")
    assert dana["influence"] == "high" and dana["size"] > 22 and dana["power"] == 3 and dana["interest"] == 3
    assert len(g["edges"]) == 1 and g["edges"][0]["type"] == "reports_to"


def test_waterfall_orders_current_recovered_expansion_total(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/contracts", json={"account_id": a["id"], "version_label": "cur", "price": 900000})
    c.post("/api/recovered-spend", json={"account_id": a["id"], "label": "incumbent", "amount": 300000})
    c.post("/api/expansions", json={"account_id": a["id"], "name": "3k", "expected_value": 1800000})
    w = c.get(f"/api/accounts/{a['id']}/waterfall").json()
    kinds = [s["kind"] for s in w["steps"]]
    assert kinds == ["start", "add", "add", "total"]
    assert w["steps"][0]["amount"] == 900000 and w["steps"][-1]["amount"] == 3000000


def test_observation_history_series(scene):
    c = scene["c"]
    d = c.post("/api/metric-definitions", json={"name": "Activation"}).json()
    for period, val in [("2026-05", 0.6), ("2026-06", 0.68), ("2026-07", 0.72)]:
        c.post("/api/metric-observations", json={"definition_id": d["id"], "period_label": period, "value": val, "current_through": "2026-07-10"})
    h = c.get(f"/api/metric-definitions/{d['id']}/observations").json()
    assert [p["period"] for p in h["series"]] == ["2026-05", "2026-06", "2026-07"]
