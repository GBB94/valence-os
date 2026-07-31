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
# metric_definitions, audience_tags, use_cases) are included only for rows this account
# references.
#
# KEEP THIS IN SYNC WITH EVERY MIGRATION THAT ADDS AN ACCOUNT-SCOPED TABLE. It previously
# stopped at migration 0005, which meant a "full" account export silently dropped MAP
# promotion, onboarding checklists, people layers, cadence, ingestion, and all of Stage 5's
# relationship intelligence — the export succeeded and looked complete while losing data.
# `test_export_covers_every_account_scoped_table` fails if a new table is not listed here.
_INSERT_ORDER = [
    # globals first (FK targets)
    "source_references", "metric_definitions", "audience_tags", "use_cases",
    "accounts", "account_settings", "persons", "programs",
    "stakeholder_roles", "interactions", "interaction_participants", "capture_inbox_items",
    "tasks", "commitments", "decisions", "risks", "issues", "milestones",
    "expansion_opportunities", "contract_versions", "phase_gates", "phase_gate_items",
    "deployment_moments", "comms_entries", "compliance_items", "scope_changes",
    "value_stories", "relationship_edges", "recovered_spend",
    # 0012-0016 — onboarding, people intelligence, ingestion, relationships
    "checklist_items", "advocacy_events", "comm_messages", "association_hints",
    "champion_candidates", "exec_pairings", "pull_signals",
    # 0017-0019 — whitespace, value ledger, funding (population objects precede the cells,
    # observations, and targets that reference them)
    "population_partitions", "population_segments", "population_views",
    "population_view_segments", "population_view_tags", "population_headcount_observations",
    "metric_observations", "whitespace_cells", "cell_state_history", "cell_evidence_links",
    "value_targets", "value_target_evidence",
    "funding_pools", "fiscal_maps", "ask_calendars", "ask_calendar_steps", "revenue_events",
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

    # --- 0012-0016: onboarding, people intelligence, ingestion, relationships ---
    t["account_settings"] = _all(conn, "SELECT * FROM account_settings WHERE account_id=?", (account_id,))
    for tbl in ("checklist_items", "comm_messages", "association_hints",
                "champion_candidates", "exec_pairings", "pull_signals"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    # advocacy_events hang off people, not accounts — scope them through this account's persons.
    acct_person_ids = [r["id"] for r in conn.execute("SELECT id FROM persons WHERE account_id=?", (account_id,))]
    apq = ",".join("?" * len(acct_person_ids)) or "''"
    t["advocacy_events"] = _all(
        conn, f"SELECT * FROM advocacy_events WHERE person_id IN ({apq})", acct_person_ids
    ) if acct_person_ids else []

    # --- 0017-0019: whitespace, value ledger, funding ---
    for tbl in ("population_partitions", "population_segments", "population_views",
                "population_headcount_observations", "whitespace_cells", "value_targets",
                "funding_pools", "ask_calendars", "revenue_events"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    t["fiscal_maps"] = _all(conn, "SELECT * FROM fiscal_maps WHERE account_id=?", (account_id,))

    view_ids = [r["id"] for r in t["population_views"]]
    vq = ",".join("?" * len(view_ids)) or "''"
    for tbl, col in (("population_view_segments", "view_id"), ("population_view_tags", "view_id")):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE {col} IN ({vq})", view_ids) if view_ids else []

    cell_ids = [r["id"] for r in t["whitespace_cells"]]
    cq = ",".join("?" * len(cell_ids)) or "''"
    for tbl in ("cell_state_history", "cell_evidence_links"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE cell_id IN ({cq})", cell_ids) if cell_ids else []

    target_ids = [r["id"] for r in t["value_targets"]]
    tq = ",".join("?" * len(target_ids)) or "''"
    t["value_target_evidence"] = _all(
        conn, f"SELECT * FROM value_target_evidence WHERE target_id IN ({tq})", target_ids
    ) if target_ids else []

    cal_ids = [r["id"] for r in t["ask_calendars"]]
    calq = ",".join("?" * len(cal_ids)) or "''"
    t["ask_calendar_steps"] = _all(
        conn, f"SELECT * FROM ask_calendar_steps WHERE calendar_id IN ({calq})", cal_ids
    ) if cal_ids else []

    # Observations reach this account two ways now: through a program, or through a population
    # segment (Stage 5.5's stable identity). Union them, or the ledger's evidence is lost.
    seg_ids = [r["id"] for r in t["population_segments"]]
    sgq = ",".join("?" * len(seg_ids)) or "''"
    obs = {r["id"]: r for r in (
        _all(conn, f"SELECT * FROM metric_observations WHERE program_id IN ({pq})", pids) if pids else [])}
    if seg_ids:
        for r in _all(conn, f"SELECT * FROM metric_observations WHERE population_segment_id IN ({sgq})", seg_ids):
            obs[r["id"]] = r
    if view_ids:
        for r in _all(conn, f"SELECT * FROM metric_observations WHERE population_view_id IN ({vq})", view_ids):
            obs[r["id"]] = r
    t["metric_observations"] = list(obs.values())

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
        # 0013-0019 person references, or a restored bundle hits a missing FK.
        ("advocacy_events", ["person_id"]), ("comm_messages", ["person_id"]),
        ("association_hints", ["person_id"]), ("champion_candidates", ["person_id"]),
        ("exec_pairings", ["client_person_id", "valence_person_id"]),
        ("whitespace_cells", ["sponsor_person_id", "blocker_owner_person_id"]),
        ("value_targets", ["accepted_by_person_id"]),
        ("funding_pools", ["owner_person_id"]),
        ("ask_calendar_steps", ["owner_person_id"]),
    ]:
        for row in t.get(tbl, []):
            for c in cols:
                if row.get(c):
                    person_ids.add(row[c])
    for row in t["interaction_participants"]:
        person_ids.add(row["person_id"])
    pids2 = ",".join("?" * len(person_ids)) or "''"
    t["persons"] = _all(conn, f"SELECT * FROM persons WHERE id IN ({pids2})", tuple(person_ids)) if person_ids else []

    # Every table that can cite a source. A citation whose source_reference is not exported
    # restores as a dangling id, so the claim loses its provenance — which for headcount and
    # value targets is the whole point of the record.
    srcs = {row["source_reference_id"] for tbl in (
        "interactions", "commitments", "decisions", "tasks", "risks", "issues", "milestones",
        "metric_observations", "value_stories", "population_segments",
        "population_headcount_observations", "value_targets", "revenue_events",
    ) for row in t.get(tbl, []) if row.get("source_reference_id")}
    sq = ",".join("?" * len(srcs)) or "''"
    t["source_references"] = _all(conn, f"SELECT * FROM source_references WHERE id IN ({sq})", tuple(srcs)) if srcs else []

    defs = {row["definition_id"] for row in t["metric_observations"] if row.get("definition_id")}
    defs |= {row["definition_id"] for row in t["value_targets"] if row.get("definition_id")}
    dq = ",".join("?" * len(defs)) or "''"
    t["metric_definitions"] = _all(conn, f"SELECT * FROM metric_definitions WHERE id IN ({dq})", tuple(defs)) if defs else []

    # Portfolio-global vocabularies (§1.2): exported for referenced rows only, so restoring one
    # account into a clean install does not import the whole portfolio's taxonomy.
    ucs = {row["use_case_id"] for row in t["whitespace_cells"] if row.get("use_case_id")}
    uq = ",".join("?" * len(ucs)) or "''"
    t["use_cases"] = _all(conn, f"SELECT * FROM use_cases WHERE id IN ({uq})", tuple(ucs)) if ucs else []
    tags = {row["tag_id"] for row in t["population_view_tags"]}
    gq2 = ",".join("?" * len(tags)) or "''"
    t["audience_tags"] = _all(conn, f"SELECT * FROM audience_tags WHERE id IN ({gq2})", tuple(tags)) if tags else []

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
                # Global/shared tables — skip if already present rather than colliding.
                if tbl in ("metric_definitions", "source_references", "audience_tags", "use_cases") and \
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
