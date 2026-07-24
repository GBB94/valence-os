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
