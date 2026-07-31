"""Account export / restore round-trip (Section 7 + success criterion #8)."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


def _tmp():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    return path


def _cleanup(path):
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


def test_export_restore_roundtrip_into_clean_db():
    from app.main import app
    db1, db2 = _tmp(), _tmp()
    try:
        # --- source DB: build an account with records, then export ---
        os.environ["VALENCE_OS_DB"] = db1
        with TestClient(app) as c:
            a = c.post("/api/accounts", json={"name": "Terravance"}).json()
            p = c.post("/api/programs", json={"account_id": a["id"], "name": "Europe", "phase": "launch"}).json()
            client_p = c.post("/api/persons", json={"name": "Sofie", "account_id": a["id"]}).json()
            owner = c.post("/api/persons", json={"name": "Sam", "affiliation": "valence"}).json()  # shared/global
            c.post("/api/stakeholder-roles", json={"program_id": p["id"], "person_id": client_p["id"], "role": "legal_dpo",
                                                   "stance": "unconverted", "stance_assessed_on": "2026-07-01", "stance_evidence_note": "e"})
            c.post("/api/interactions", json={"account_id": a["id"], "program_id": p["id"], "type": "call",
                                              "summary": "readiness", "participant_ids": [client_p["id"], owner["id"]]})
            c.post("/api/commitments", json={"program_id": p["id"], "description": "send summary",
                                             "responsible_party_id": client_p["id"], "internal_owner_id": owner["id"], "due_date": "2026-08-15"})
            c.post("/api/risks", json={"program_id": p["id"], "description": "works council may slip", "is_blocker": True})
            c.post("/api/expansions", json={"account_id": a["id"], "name": "3k seats", "target_seats": 3000})
            bundle = c.get(f"/api/accounts/{a['id']}/export").json()

        assert bundle["format"] == "valence-os-account-export/1"
        assert bundle["counts"]["programs"] == 1 and bundle["counts"]["commitments"] == 1
        assert bundle["counts"]["persons"] == 2  # client + referenced Valence owner

        # --- fresh clean DB: account absent, then restore ---
        os.environ["VALENCE_OS_DB"] = db2
        with TestClient(app) as c2:
            assert c2.get(f"/api/accounts/{a['id']}").status_code == 404       # clean install
            res = c2.post("/api/accounts/import", json=bundle)
            assert res.status_code == 201 and res.json()["account_id"] == a["id"]

            restored = c2.get(f"/api/accounts/{a['id']}").json()
            assert restored["name"] == "Terravance" and len(restored["programs"]) == 1
            board = c2.get(f"/api/programs/{p['id']}/execution").json()
            assert len(board["commitments"]) == 1 and len(board["risks"]) == 1
            # the referenced Valence owner came across too, so the commitment resolves its owner name
            acct_exec = c2.get(f"/api/accounts/{a['id']}/execution").json()
            assert acct_exec["commitments"][0]["internal_owner_name"] == "Sam"
            # re-importing the same bundle now conflicts (account exists)
            assert c2.post("/api/accounts/import", json=bundle).status_code == 409
    finally:
        _cleanup(db1); _cleanup(db2)


def test_export_missing_account_404():
    from app.main import app
    db = _tmp()
    try:
        os.environ["VALENCE_OS_DB"] = db
        with TestClient(app) as c:
            assert c.get("/api/accounts/nope/export").status_code == 404
            assert c.post("/api/accounts/import", json={"format": "wrong"}).status_code == 422
    finally:
        _cleanup(db)

def test_export_covers_every_account_scoped_table():
    """The registry guard.

    `_INSERT_ORDER` previously stopped at migration 0005, so a "full" export silently dropped
    MAP promotion, onboarding, people layers, cadence, ingestion, and all of Stage 5 — it
    succeeded and looked complete while losing data. This test fails the moment a migration
    adds an account-scoped table that nobody added to the registry, which is the only way that
    stays true over time.
    """
    from app.main import app
    from app.portfolio_io import _INSERT_ORDER
    db = _tmp()
    try:
        os.environ["VALENCE_OS_DB"] = db
        # Operational infrastructure and append-only logs are deliberately not account data:
        # they describe the installation, not the customer.
        infrastructure = {
            "schema_migrations", "audit_events", "jobs", "notifications", "search_index",
            "attention_state", "import_batches", "extraction_runs", "extraction_proposals",
            "play_definitions", "play_runs", "source_reference_tags", "messaging_entries",
            "cadence_overrides", "onboarding_templates", "checklist_templates",
        }
        account_scoped = set()
        with TestClient(app):
            conn = app.state.conn
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            for t in tables - infrastructure:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
                # Reaches an account directly or through one hop the exporter already walks.
                if cols & {"account_id", "program_id", "person_id", "interaction_id", "cell_id",
                           "target_id", "calendar_id", "view_id", "segment_id", "gate_id",
                           "definition_id", "contract_version_id"}:
                    account_scoped.add(t)

        missing = account_scoped - set(_INSERT_ORDER)
        assert not missing, (
            f"these account-scoped tables are missing from portfolio_io._INSERT_ORDER and would "
            f"be silently dropped from a 'full' account export: {sorted(missing)}")
    finally:
        _cleanup(db)


def test_export_restore_carries_stage55_records():
    """Whitespace cells, value targets, and funding survive a round-trip into a clean install."""
    from app.main import app
    db1, db2 = _tmp(), _tmp()
    try:
        os.environ["VALENCE_OS_DB"] = db1
        with TestClient(app) as c:
            a = c.post("/api/accounts", json={"name": "Terravance"}).json()
            person = c.post("/api/persons", json={"name": "Sofie", "account_id": a["id"]}).json()
            part = c.post("/api/population-partitions", json={
                "account_id": a["id"], "basis": "region", "total_fte": 20000}).json()
            seg = c.post("/api/population-segments", json={
                "partition_id": part["id"], "name": "DACH", "headcount": 6000}).json()
            uc = c.post("/api/use-cases", json={"name": "Performance reviews", "slug": "pr"}).json()
            cell = c.post("/api/whitespace-cells", json={
                "account_id": a["id"], "segment_id": seg["id"], "use_case_id": uc["id"],
                "paid_seats": 900, "sponsor_person_id": person["id"]}).json()
            c.post(f"/api/whitespace-cells/{cell['id']}/set-fact", json={
                "fact": "penetration", "value": "paid", "reason": "signed"})
            d = c.post("/api/metric-definitions", json={"name": "Activation"}).json()
            c.post("/api/value-targets", json={
                "account_id": a["id"], "definition_id": d["id"], "segment_id": seg["id"],
                "target_value": 0.7, "timeframe_end": "2026-12-31"})
            c.post("/api/funding-pools", json={
                "account_id": a["id"], "name": "Central L&D", "kind": "central_ld_budget",
                "owner_person_id": person["id"]})
            c.post("/api/ask-calendars", json={
                "account_id": a["id"], "name": "DACH ask", "target_close_date": "2026-12-01"})
            bundle = c.get(f"/api/accounts/{a['id']}/export").json()

        for tbl in ("population_partitions", "population_segments", "whitespace_cells",
                    "cell_state_history", "value_targets", "funding_pools",
                    "ask_calendars", "ask_calendar_steps", "use_cases"):
            assert bundle["counts"].get(tbl), f"{tbl} missing from the export bundle"

        os.environ["VALENCE_OS_DB"] = db2
        with TestClient(app) as c2:
            assert c2.post("/api/accounts/import", json=bundle).status_code == 201
            m = c2.get(f"/api/accounts/{a['id']}/whitespace").json()
            row = next(r for r in m["segment_rows"] if r["name"] == "DACH")
            assert row["paid_seats"] == 900
            restored_cell = next(x["cell"] for x in row["cells"] if x["cell"])
            assert restored_cell["state"] == "penetrated_unevidenced"   # derived, and it survived
            assert c2.get(f"/api/accounts/{a['id']}/ledger").json()["total"] == 1
            assert c2.get(f"/api/accounts/{a['id']}/funding").json()["funding_pools"]
    finally:
        _cleanup(db1); _cleanup(db2)
