"""Dev reset/seed command (CLAUDE.md).

Loads the Stage-0 mock accounts into the DB, preserving their YAML ids so the
cross-references resolve. Only v0.1 objects are loaded; execution objects
(commitments, risks, milestones, tasks) belong to v0.2 tables that don't exist
yet and are skipped with a count, so nothing is silently dropped.

Usage:
    python -m app.seed --reset      # wipe DB, migrate, load seed
    python -m app.seed              # load seed into existing DB
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import yaml

from .db import connect, db_path, now_utc, run_migrations

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "stage-0" / "seed-data"

# v0.1 columns per table (YAML keys outside these are ignored for now).
COLUMNS = {
    "source_references": {"id", "type", "label", "url", "locator"},
    "accounts": {
        "id", "name", "short_context", "incumbent_note",
        "delivery_status", "delivery_status_rationale", "delivery_status_assessed_on",
        "delivery_status_change_condition", "commercial_status", "commercial_status_rationale",
        "commercial_status_assessed_on", "commercial_status_change_condition",
    },
    "persons": {"id", "name", "affiliation", "account_id", "title", "email"},
    "programs": {
        "id", "account_id", "name", "phase", "region", "audience", "use_case",
        "problem_statement", "in_scope_population", "out_of_scope_population",
        "launch_definition", "success_criteria", "expansion_hypothesis",
        "explicit_exclusions", "sponsor_person_id",
    },
    "stakeholder_roles": {
        "id", "program_id", "person_id", "role", "stance", "stance_assessed_on",
        "stance_evidence_note", "cares_about", "value_for_them",
    },
    "interactions": {
        "id", "account_id", "program_id", "occurred_on", "occurred_at_time", "type",
        "summary", "raw_notes", "source_reference_id", "follow_up", "meaningful_touch",
    },
    "capture_inbox_items": {
        "id", "interaction_id", "raw_text", "status", "converted_to_type",
        "converted_to_id", "resolved_on", "resolved_by",
    },
    "tasks": {
        "id", "program_id", "description", "internal_owner_id", "due_date", "status",
        "closed_on", "closed_by", "close_note", "source_interaction_id", "source_reference_id",
    },
    "commitments": {
        "id", "program_id", "description", "responsible_party_id", "internal_owner_id",
        "due_date", "status", "acknowledged_by_id", "closed_on", "closed_by", "close_note",
        "source_interaction_id", "source_reference_id",
    },
    "decisions": {
        "id", "program_id", "description", "decided_on", "decided_by_id", "rationale",
        "supersedes_id", "status", "source_interaction_id", "source_reference_id",
    },
    "risks": {
        "id", "program_id", "description", "severity", "is_blocker", "mitigation", "status",
        "close_reason", "closed_on", "closed_by", "close_note", "internal_owner_id",
        "source_interaction_id", "source_reference_id",
    },
    "issues": {
        "id", "program_id", "description", "is_blocker", "status", "resolution_type",
        "resolved_on", "resolved_by", "resolution_note", "internal_owner_id",
        "source_interaction_id", "source_reference_id",
    },
    "milestones": {
        "id", "program_id", "name", "target_date", "success_criteria", "at_risk", "status",
        "completed_on", "completed_by", "completion_note", "source_interaction_id",
    },
}
# YAML key -> table for v0.2 execution objects.
EXEC_SECTIONS = {
    "tasks": "tasks", "commitments": "commitments", "decisions": "decisions",
    "risks": "risks", "issues": "issues", "milestones": "milestones",
}


def _iso(v):
    # YAML turns unquoted dates into date/datetime objects; store them as TEXT.
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    return v


def _insert(conn, table, record):
    ts = now_utc()
    row = {k: _iso(v) for k, v in record.items() if k in COLUMNS[table]}
    row.setdefault("created_at", ts)
    row.setdefault("updated_at", ts)
    if table == "interactions":
        row["meaningful_touch"] = 1 if record.get("meaningful_touch", True) else 0
        row["account_id"] = record["account_id"]
    cols = ", ".join(row.keys())
    conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' for _ in row)})",
        tuple(row.values()),
    )


def load_file(conn, path: Path, skipped: dict[str, int]):
    data = yaml.safe_load(path.read_text())
    if not data:
        return
    # Standalone people file (valence team).
    for person in data.get("people", []) if "account" not in data else []:
        _insert(conn, "persons", person)
    if "account" not in data:
        return

    acct_id = data["account"]["id"]
    _insert(conn, "accounts", data["account"])
    for person in data.get("people", []):
        person.setdefault("account_id", acct_id)
        _insert(conn, "persons", person)
    for program in data.get("programs", []):
        _insert(conn, "programs", program)
    for sr in data.get("source_references", []):
        _insert(conn, "source_references", sr)
    for role in data.get("stakeholder_roles", []):
        _insert(conn, "stakeholder_roles", role)
    for inter in data.get("interactions", []):
        inter.setdefault("account_id", acct_id)
        parts = inter.pop("participants", [])
        _insert(conn, "interactions", inter)
        for pid in parts:
            conn.execute(
                "INSERT OR IGNORE INTO interaction_participants (interaction_id, person_id) VALUES (?,?)",
                (inter["id"], pid),
            )
    for item in data.get("capture_inbox_items", []):
        _insert(conn, "capture_inbox_items", item)
    # v0.2 execution objects (tables now exist).
    for key, table in EXEC_SECTIONS.items():
        for rec in data.get(key) or []:
            _insert(conn, table, rec)


def main():
    reset = "--reset" in sys.argv
    if reset:
        p = db_path()
        for suffix in ("", "-wal", "-shm"):
            f = Path(str(p) + suffix)
            if f.exists():
                f.unlink()
        print(f"[seed] reset: removed {p.name}")

    conn = connect()
    run_migrations(conn)

    skipped: dict[str, int] = {}
    with conn:
        # Load the internal Valence team first (referenced as owners later).
        team = SEED_DIR / "valence-team.yaml"
        if team.exists():
            load_file(conn, team, skipped)
        for name in ("terravance.yaml", "northwind.yaml", "bluepeak.yaml"):
            load_file(conn, SEED_DIR / name, skipped)

    counts = {
        t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        for t in ("accounts", "programs", "persons", "stakeholder_roles",
                  "interactions", "capture_inbox_items", "tasks", "commitments",
                  "decisions", "risks", "issues", "milestones")
    }
    print(f"[seed] loaded: {counts}")
    conn.close()


if __name__ == "__main__":
    main()
