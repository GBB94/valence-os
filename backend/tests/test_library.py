"""Files & context library (Section 5O) — link-first, searchable, with citations."""
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


def test_library_lists_sources_with_citations(client):
    a = client.post("/api/accounts", json={"name": "Terravance"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Europe"}).json()
    src = client.post("/api/source-references", json={"type": "file", "label": "Steering deck", "url": "https://x.test/deck"}).json()
    # cite it from an interaction and a commitment
    client.post("/api/interactions", json={"account_id": a["id"], "program_id": p["id"], "type": "meeting",
                                           "summary": "Steering forum", "source_reference_id": src["id"]})
    who = client.post("/api/persons", json={"name": "Sofie", "account_id": a["id"]}).json()["id"]
    own = client.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()["id"]
    client.post("/api/commitments", json={"program_id": p["id"], "description": "share deck",
                                          "responsible_party_id": who, "internal_owner_id": own,
                                          "due_date": "2026-08-01", "source_reference_id": src["id"]})

    lib = client.get("/api/library").json()
    row = next(s for s in lib["sources"] if s["id"] == src["id"])
    assert row["label"] == "Steering deck" and row["citation_count"] == 2
    kinds = {c["object_type"] for c in row["citations"]}
    assert kinds == {"interaction", "commitment"}
    assert "Terravance" in row["accounts"]


def test_library_filters_by_type_search_and_account(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "P"}).json()
    deck = client.post("/api/source-references", json={"type": "file", "label": "Q3 deck"}).json()
    tx = client.post("/api/source-references", json={"type": "transcript_span", "label": "call transcript"}).json()
    client.post("/api/interactions", json={"account_id": a["id"], "program_id": p["id"], "type": "call", "source_reference_id": tx["id"]})

    assert len(client.get("/api/library?type=file").json()["sources"]) == 1
    assert client.get("/api/library?q=transcript").json()["sources"][0]["id"] == tx["id"]
    # account filter uses citations; the deck is uncited so it's excluded when filtering by account
    by_acct = client.get(f"/api/library?account_id={a['id']}").json()["sources"]
    assert {s["id"] for s in by_acct} == {tx["id"]}


def test_library_tags_create_edit_filter_and_search(client):
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    tagged = client.post("/api/source-references", json={
        "type": "file", "label": "Steering deck", "tags": "steering, governance"}).json()
    plain = client.post("/api/source-references", json={"type": "file", "label": "Random deck"}).json()

    lib = client.get("/api/library").json()
    row = next(s for s in lib["sources"] if s["id"] == tagged["id"])
    assert row["tag_list"] == ["steering", "governance"]
    assert lib["all_tags"] == ["governance", "steering"]  # distinct, sorted

    # filter by tag returns only the tagged deck
    assert {s["id"] for s in client.get("/api/library?tag=steering").json()["sources"]} == {tagged["id"]}
    # search matches on tag text
    assert {s["id"] for s in client.get("/api/library?q=governance").json()["sources"]} == {tagged["id"]}

    # edit tags via PATCH: retag the plain deck, clear the tagged one
    client.patch(f"/api/source-references/{plain['id']}", json={"tags": "steering"})
    client.patch(f"/api/source-references/{tagged['id']}", json={"tags": ""})
    assert {s["id"] for s in client.get("/api/library?tag=steering").json()["sources"]} == {plain["id"]}
    assert client.get("/api/library").json()["all_tags"] == ["steering"]


def test_population_only_metric_observation_keeps_its_source_citation(client):
    """Stable population identity can scope an observation without a program; the source
    library must not silently drop that citation by inner-joining only through programs."""
    a = client.post("/api/accounts", json={"name": "Acme"}).json()
    part = client.post("/api/population-partitions", json={
        "account_id": a["id"], "total_fte": 1000}).json()
    seg = client.post("/api/population-segments", json={
        "partition_id": part["id"], "name": "Core", "headcount": 900}).json()
    definition = client.post("/api/metric-definitions", json={"name": "Activation"}).json()
    source = client.post("/api/source-references", json={
        "type": "data_report", "label": "Aggregate cohort report"}).json()
    observation = client.post("/api/metric-observations", json={
        "definition_id": definition["id"], "population_segment_id": seg["id"],
        "value": 0.8, "current_through": "2026-07-30", "source_reference_id": source["id"]}).json()

    row = next(s for s in client.get(f"/api/library?account_id={a['id']}").json()["sources"]
               if s["id"] == source["id"])
    citation = next(c for c in row["citations"] if c["object_type"] == "metric_observation")
    assert citation["object_id"] == observation["id"] and citation["account_id"] == a["id"]
