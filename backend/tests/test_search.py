"""Global FTS5 search tests (Section 8)."""
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


def test_search_finds_records_across_types(client):
    a = client.post("/api/accounts", json={"name": "Terravance Ag"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Europe Deployment"}).json()
    client.post("/api/interactions", json={"account_id": a["id"], "program_id": p["id"], "type": "call",
                                           "summary": "Works council review pending in Germany"})
    client.post("/api/risks", json={"program_id": p["id"], "description": "Betriebsrat consultation may slip"})

    # matches an interaction summary
    r = client.get("/api/search?q=works council").json()["results"]
    assert any(x["object_type"] == "interaction" for x in r)
    assert r[0]["account_name"] == "Terravance Ag"
    assert "[" in r[0]["snippet"] or r[0]["title"]

    # prefix match: "council" also hits via the summary; "Betri" hits the risk
    assert any(x["object_type"] == "risk" for x in client.get("/api/search?q=betri").json()["results"])

    # account name itself is searchable
    assert any(x["object_type"] == "account" for x in client.get("/api/search?q=terravance").json()["results"])


def test_search_reflects_new_records_without_restart(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    assert client.get("/api/search?q=quantum").json()["results"] == []
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    client.post("/api/tasks", json={"program_id": p["id"], "description": "Investigate the quantum widget"})
    assert any(x["object_type"] == "task" for x in client.get("/api/search?q=quantum").json()["results"])


def test_empty_query_returns_nothing(client):
    client.post("/api/accounts", json={"name": "Acme"})
    assert client.get("/api/search?q=").json()["results"] == []
    assert client.get("/api/search?q=   ").json()["results"] == []


def test_search_indexes_stage4_and_stage55_records(client):
    """The index stopped at the v0-v2 object set, so records built in Stages 4, 5, and 5.5 were
    invisible to global search — findable in their own tab and nowhere else. `reindex` skips
    sources whose table is missing, so a stale source list fails silently rather than loudly;
    this test is the thing that notices."""
    a = client.post("/api/accounts", json={"name": "Terravance"}).json()
    part = client.post("/api/population-partitions", json={
        "account_id": a["id"], "basis": "region", "total_fte": 20000}).json()
    seg = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "Zephyr DACH", "headcount": 6000}).json()
    uc = client.post("/api/use-cases", json={"name": "Change management", "slug": "cm"}).json()
    client.post("/api/whitespace-cells", json={
        "account_id": a["id"], "segment_id": seg["id"], "use_case_id": uc["id"],
        "next_action": "brief the works council"})
    client.post("/api/funding-pools", json={
        "account_id": a["id"], "name": "Quilfeather transformation budget",
        "kind": "transformation_program"})
    client.post("/api/pull-signals", json={
        "account_id": a["id"], "description": "Marrowdale BU asked for access"})

    client.post("/api/search/reindex")
    for q, kind in [("Zephyr", "population_segment"),
                    ("works council", "whitespace_cell"),
                    ("Quilfeather", "funding_pool"),
                    ("Marrowdale", "pull_signal")]:
        hits = client.get(f"/api/search?q={q}").json()["results"]
        assert any(h["object_type"] == kind for h in hits), f"{q!r} did not surface a {kind}"
