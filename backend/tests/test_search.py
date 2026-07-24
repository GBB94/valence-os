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
