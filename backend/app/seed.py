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
        "governance_steering", "governance_rhythm", "next_qbr_date",  # v1
    },
    "stakeholder_roles": {
        "id", "program_id", "person_id", "role", "stance", "stance_assessed_on",
        "stance_evidence_note", "cares_about", "value_for_them",
        "influence", "relationship_strength", "graph_assessed_on", "graph_evidence_note",  # v3
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
    "expansion_opportunities": {
        "id", "account_id", "name", "use_case", "target_seats", "expected_value",
        "sponsor_person_id", "budget_owner_person_id", "funding_source", "supporting_evidence",
        "decision_date", "budget_state", "blockers", "next_action", "status", "outcome",
        "outcome_reason", "source_interaction_id",
    },
    "contract_versions": {
        "id", "account_id", "version_label", "seats", "price", "start_date", "end_date",
        "renewal_date", "notice_period_days", "procurement_lead_days", "amendments",
        "source_system", "source_identifier", "editable_locally", "supersedes_id", "is_current",
        "overlay_expected_decision_date", "overlay_rationale", "overlay_author", "overlay_assessed_on",
    },
    "phase_gates": {"id", "program_id", "name", "gates_phase", "status", "waiver_reason", "waived_by", "passed_on"},
    "phase_gate_items": {"id", "gate_id", "description", "complete", "completed_on"},
    "deployment_moments": {
        "id", "program_id", "name", "type", "client_owner_person_id", "comms_hook",
        "integration_status", "event_date", "outcome",
    },
    "comms_entries": {"id", "program_id", "moment_id", "audience", "message", "sender", "channel", "send_date", "status"},
    "compliance_items": {"id", "program_id", "region", "lane", "status", "owner_person_id", "notes"},
    "scope_changes": {"id", "program_id", "description", "agreed_by_person_id", "changed_on", "source_interaction_id"},
    "metric_definitions": {"id", "name", "meaning", "source_system", "owner", "version", "population", "formula_notes", "stale_after_days"},
    "metric_observations": {"id", "definition_id", "definition_version", "program_id", "cohort_label", "period_label", "value", "unit", "target", "current_through", "source_reference_id", "import_batch_id"},
    "benchmarks": {"id", "name", "value", "unit", "population", "period", "source", "version", "source_reference_id"},
    "value_stories": {"id", "account_id", "program_id", "outcome", "tags", "evidence_tier", "visibility_class", "identifiable", "is_negative", "source_reference_id"},
    "relationship_edges": {"id", "account_id", "from_person_id", "to_person_id", "type", "program_id", "note"},
    "recovered_spend": {"id", "account_id", "label", "amount", "source_note"},
}
# YAML key -> table for v0.2 execution objects.
EXEC_SECTIONS = {
    "tasks": "tasks", "commitments": "commitments", "decisions": "decisions",
    "risks": "risks", "issues": "issues", "milestones": "milestones",
}
# YAML key -> table for v1 objects (account-scoped and program-scoped).
V1_ACCOUNT_SECTIONS = {"expansion_opportunities": "expansion_opportunities",
                       "contract_versions": "contract_versions"}
V1_PROGRAM_SECTIONS = {"deployment_moments": "deployment_moments",
                       "comms_entries": "comms_entries", "compliance_items": "compliance_items",
                       "scope_changes": "scope_changes"}
V2_ACCOUNT_SECTIONS = {"value_stories": "value_stories"}
V3_ACCOUNT_SECTIONS = {"relationship_edges": "relationship_edges", "recovered_spend": "recovered_spend"}


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
    # v1 + v2 + v3 account-scoped objects.
    for key, table in {**V1_ACCOUNT_SECTIONS, **V2_ACCOUNT_SECTIONS, **V3_ACCOUNT_SECTIONS}.items():
        for rec in data.get(key) or []:
            rec.setdefault("account_id", acct_id)
            _insert(conn, table, rec)
    # v1 program-scoped objects.
    for key, table in V1_PROGRAM_SECTIONS.items():
        for rec in data.get(key) or []:
            _insert(conn, table, rec)
    # phase gates with nested items.
    for gate in data.get("phase_gates") or []:
        gitems = gate.pop("items", [])
        _insert(conn, "phase_gates", gate)
        for gi in gitems:
            gi.setdefault("gate_id", gate["id"])
            _insert(conn, "phase_gate_items", gi)


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
        # Global v2 data (metric definitions/observations, benchmarks) — after programs exist.
        metrics = SEED_DIR / "metrics.yaml"
        if metrics.exists():
            mdata = yaml.safe_load(metrics.read_text()) or {}
            for md in mdata.get("metric_definitions", []):
                _insert(conn, "metric_definitions", md)
            for mo in mdata.get("metric_observations", []):
                _insert(conn, "metric_observations", mo)
            for bm in mdata.get("benchmarks", []):
                _insert(conn, "benchmarks", bm)

    counts = {
        t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        for t in ("accounts", "programs", "persons", "stakeholder_roles",
                  "interactions", "capture_inbox_items", "tasks", "commitments",
                  "decisions", "risks", "issues", "milestones",
                  "expansion_opportunities", "contract_versions", "phase_gates",
                  "deployment_moments", "compliance_items", "scope_changes")
    }
    print(f"[seed] loaded: {counts}")
    conn.close()


if __name__ == "__main__":
    main()
