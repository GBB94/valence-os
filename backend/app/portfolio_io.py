"""Account export / restore (Section 7 exportability + success criterion #8).

Exports a full account and all its related records to a structured JSON bundle, and
restores that bundle into a clean installation — no manual DB surgery. Round-trippable
(a test exports from one DB and restores into a fresh one). The tool never traps its
own information.
"""
from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from . import audit
from .db import now_utc

FORMAT = "valence-os-account-export/1"

# Insert order is FK-safe; export walks the same set. Global tables (source_references,
# metric_definitions) are included only for rows this account references.
_INSERT_ORDER = [
    "source_references", "metric_definitions", "accounts", "persons", "programs",
    "stakeholder_roles", "interactions", "interaction_participants", "capture_inbox_items",
    "tasks", "commitments", "decisions", "risks", "issues", "milestones",
    "expansion_opportunities", "contract_versions", "phase_gates", "phase_gate_items",
    "deployment_moments", "comms_entries", "compliance_items", "scope_changes",
    "value_stories", "relationship_edges", "recovered_spend", "metric_observations",
]


def _all(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def export_account(conn: sqlite3.Connection, account_id: str) -> dict:
    acct = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not acct:
        raise HTTPException(404, f"account not found: {account_id}")
    pids = [r["id"] for r in conn.execute("SELECT id FROM programs WHERE account_id=?", (account_id,))]
    pq = ",".join("?" * len(pids)) or "''"
    gids = [r["id"] for r in conn.execute(f"SELECT id FROM phase_gates WHERE program_id IN ({pq})", pids)] if pids else []
    gq = ",".join("?" * len(gids)) or "''"
    iids = [r["id"] for r in conn.execute("SELECT id FROM interactions WHERE account_id=?", (account_id,))]
    iq = ",".join("?" * len(iids)) or "''"

    t = {}
    t["accounts"] = _all(conn, "SELECT * FROM accounts WHERE id=?", (account_id,))
    t["programs"] = _all(conn, "SELECT * FROM programs WHERE account_id=?", (account_id,))
    t["interactions"] = _all(conn, "SELECT * FROM interactions WHERE account_id=?", (account_id,))
    t["interaction_participants"] = _all(conn, f"SELECT * FROM interaction_participants WHERE interaction_id IN ({iq})", iids) if iids else []
    t["capture_inbox_items"] = _all(conn, f"SELECT * FROM capture_inbox_items WHERE interaction_id IN ({iq})", iids) if iids else []
    for tbl in ("stakeholder_roles", "tasks", "commitments", "decisions", "risks", "issues",
                "milestones", "deployment_moments", "comms_entries", "compliance_items", "scope_changes"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE program_id IN ({pq})", pids) if pids else []
    for tbl in ("expansion_opportunities", "contract_versions", "value_stories", "relationship_edges", "recovered_spend"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    t["phase_gates"] = _all(conn, f"SELECT * FROM phase_gates WHERE program_id IN ({pq})", pids) if pids else []
    t["phase_gate_items"] = _all(conn, f"SELECT * FROM phase_gate_items WHERE gate_id IN ({gq})", gids) if gids else []
    t["metric_observations"] = _all(conn, f"SELECT * FROM metric_observations WHERE program_id IN ({pq})", pids) if pids else []

    # Referenced globals: persons (client + any referenced Valence owners), source_references, metric_definitions.
    person_ids = {r["id"] for r in conn.execute("SELECT id FROM persons WHERE account_id=?", (account_id,))}
    for tbl, cols in [
        ("programs", ["sponsor_person_id"]),
        ("stakeholder_roles", ["person_id"]),
        ("commitments", ["responsible_party_id", "internal_owner_id", "acknowledged_by_id"]),
        ("tasks", ["internal_owner_id"]), ("risks", ["internal_owner_id"]), ("issues", ["internal_owner_id"]),
        ("decisions", ["decided_by_id"]), ("deployment_moments", ["client_owner_person_id"]),
        ("compliance_items", ["owner_person_id"]), ("scope_changes", ["agreed_by_person_id"]),
        ("expansion_opportunities", ["sponsor_person_id", "budget_owner_person_id"]),
        ("relationship_edges", ["from_person_id", "to_person_id"]),
    ]:
        for row in t.get(tbl, []):
            for c in cols:
                if row.get(c):
                    person_ids.add(row[c])
    for row in t["interaction_participants"]:
        person_ids.add(row["person_id"])
    pids2 = ",".join("?" * len(person_ids)) or "''"
    t["persons"] = _all(conn, f"SELECT * FROM persons WHERE id IN ({pids2})", tuple(person_ids)) if person_ids else []

    srcs = {row["source_reference_id"] for tbl in ("interactions", "commitments", "decisions", "tasks", "risks", "issues",
            "milestones", "metric_observations") for row in t.get(tbl, []) if row.get("source_reference_id")}
    sq = ",".join("?" * len(srcs)) or "''"
    t["source_references"] = _all(conn, f"SELECT * FROM source_references WHERE id IN ({sq})", tuple(srcs)) if srcs else []

    defs = {row["definition_id"] for row in t["metric_observations"] if row.get("definition_id")}
    dq = ",".join("?" * len(defs)) or "''"
    t["metric_definitions"] = _all(conn, f"SELECT * FROM metric_definitions WHERE id IN ({dq})", tuple(defs)) if defs else []

    return {"format": FORMAT, "exported_at": now_utc(), "account_id": account_id,
            "account_name": acct["name"], "tables": t,
            "counts": {k: len(v) for k, v in t.items() if v}}


def import_account(conn: sqlite3.Connection, bundle: dict) -> dict:
    if bundle.get("format") != FORMAT:
        raise HTTPException(422, f"unrecognized export format: {bundle.get('format')}")
    tables = bundle.get("tables") or {}
    acct_rows = tables.get("accounts") or []
    if not acct_rows:
        raise HTTPException(422, "bundle has no account")
    account_id = acct_rows[0]["id"]
    if conn.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
        raise HTTPException(409, f"account {account_id} already exists; restore is for a clean install")

    inserted = {}
    with conn:
        for tbl in _INSERT_ORDER:
            rows = tables.get(tbl) or []
            for row in rows:
                # metric_definitions / source_references are global — skip if already present (shared)
                if tbl in ("metric_definitions", "source_references") and \
                        conn.execute(f"SELECT 1 FROM {tbl} WHERE id=?", (row["id"],)).fetchone():
                    continue
                cols = list(row.keys())
                conn.execute(
                    f"INSERT INTO {tbl} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                    tuple(row[c] for c in cols),
                )
            if rows:
                inserted[tbl] = len(rows)
        audit.record(conn, object_type="account", object_id=account_id, action="create",
                     after={"restored_from_export": True, "tables": inserted})
    return {"account_id": account_id, "restored": inserted}
