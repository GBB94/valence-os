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
import json
import sys
from pathlib import Path

import yaml

from .db import connect, db_path, new_id, now_utc, run_migrations

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "stage-0" / "seed-data"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# v0.1 columns per table (YAML keys outside these are ignored for now).
COLUMNS = {
    "source_references": {"id", "type", "label", "url", "locator", "tags"},
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
        "client_visible",
    },
    "commitments": {
        "id", "account_id", "program_id", "account_review_id", "commitment_class",
        "description", "responsible_party_id", "internal_owner_id",
        "due_date", "status", "acknowledged_by_id", "closed_on", "closed_by", "close_note",
        "source_interaction_id", "source_reference_id", "client_visible",
    },
    "decisions": {
        "id", "account_id", "program_id", "account_review_id", "description", "decided_on", "decided_by_id", "rationale",
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
        "completed_on", "completed_by", "completion_note", "source_interaction_id", "client_visible",
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
    "recovered_spend": {"id", "account_id", "label", "amount", "currency", "source_note"},
    "play_definitions": {"id", "name", "trigger_kind", "action_template", "active"},
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
            if table in ("commitments", "decisions"):
                rec.setdefault("account_id", acct_id)
            if table == "commitments":
                rec.setdefault("commitment_class", "client")
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


def _seed_messaging_library(conn):
    """§3.12 — load the role-based messaging library from the playbook template (global)."""
    tmpl = TEMPLATE_DIR / "messaging_library.yaml"
    if not tmpl.exists():
        return 0
    data = yaml.safe_load(tmpl.read_text()) or {}
    ts = now_utc()
    n = 0
    for e in data.get("entries", []):
        conn.execute(
            "INSERT INTO messaging_entries (id, layer, role, value_prop, proof_points, objections, "
            "artifacts_note, visibility_class, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (new_id(), e["layer"], e.get("role"), e.get("value_prop"), e.get("proof_points"),
             e.get("objections"), e.get("artifacts_note"), e.get("visibility_class", "internal"), ts, ts))
        n += 1
    return n


def _seed_stage5_demo(conn):
    """Stage-5 demo rows on Terravance so the champion pipeline, influence paths, exec alignment
    and pull signals render against seeded data. Mock only. No-ops if the account isn't present."""
    if not conn.execute("SELECT 1 FROM accounts WHERE id='acc-terravance'").fetchone():
        return
    ts = now_utc()
    # An extra influence edge so the IT lead is reachable via a warm intro (§3.5).
    conn.execute("INSERT OR IGNORE INTO relationship_edges (id, account_id, from_person_id, to_person_id, type, note, created_at, updated_at) "
                 "VALUES ('re-tv-4','acc-terravance','p-tv-budget','p-tv-it','influences','Budget owner leans on IT for the security review.',?,?)", (ts, ts))
    # Dana advocated for us without us in the room -> validates her as a champion (§3.2/§3.4).
    conn.execute("INSERT INTO advocacy_events (id, person_id, program_id, kind, occurred_on, note, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (new_id(), "p-tv-champion", "prog-tv-global", "advocacy_without_us", "2026-06-28",
                  "Opened the June steering forum pushing regional GMs to nominate managers.", ts, ts))
    # Champion pipeline: Dana at maintain (validated), Lucia in develop (not yet validated).
    conn.execute("INSERT INTO champion_candidates (id, person_id, program_id, account_id, stage, developed_note, developed_on, armed_note, armed_on, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (new_id(), "p-tv-champion", "prog-tv-global", "acc-terravance", "maintain",
                  "Gave her the board-ready manager-quality narrative.", "2026-06-10",
                  "Champion enablement kit v2 shared.", "2026-06-20", ts, ts))
    conn.execute("INSERT INTO champion_candidates (id, person_id, program_id, account_id, stage, developed_note, developed_on, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)",
                 (new_id(), "p-tv-progowner", "prog-tv-global", "acc-terravance", "develop",
                  "Making her rollout run smoothly so she looks good upward.", "2026-07-10", ts, ts))
    # Exec alignment: Sam owns Dana; Henrik (high-influence economic exec) left unpaired = exposure.
    conn.execute("INSERT INTO exec_pairings (id, account_id, valence_person_id, client_person_id, next_touch_planned, notes, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (new_id(), "acc-terravance", "p-val-operator", "p-tv-champion", "2026-08-15",
                  "Monthly CHRO check-in.", ts, ts))
    # A logged pull signal (expansion demand) — feeds the Stage-7 expansion play.
    conn.execute("INSERT INTO pull_signals (id, account_id, program_id, signal_kind, requested_by_person_id, "
                 "description, occurred_on, status, source_interaction_id, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (new_id(), "acc-terravance", "prog-tv-expansion", "champion_ask", "p-tv-champion",
                  "Two additional regional GMs asked to be included in the next rollout wave.",
                  "2026-07-18", "open", "int-tv-jul-call", ts, ts))


def _seed_stage55_demo(conn):
    """Stage 5.5 demo rows on Terravance: a base partition that reconciles, a whitespace grid
    covering every derived state, value targets in each realization status, funding pools and
    a live ask calendar with late steps. Mock only. No-ops if the account isn't present.

    The grid is built to exercise the discipline rather than to look tidy: one paid-but-
    unevidenced cell drives a value gap, one gated cell outranks its own paid status, one
    declined cell is reopened so the history shows both, and one segment is small enough to
    trip the cohort privacy floor.
    """
    if not conn.execute("SELECT 1 FROM accounts WHERE id='acc-terravance'").fetchone():
        return
    ts, today = now_utc(), now_utc()[:10]
    ex = conn.execute

    ex("INSERT OR IGNORE INTO account_settings (account_id, min_cohort_size, created_at, updated_at) "
       "VALUES ('acc-terravance', 25, ?, ?)", (ts, ts))

    # --- the base partition: MECE over 20,000 FTE with a visible remainder (§1.1) ---
    ex("INSERT OR IGNORE INTO population_partitions "
       "(id, account_id, version, basis, total_fte, fte_source, fte_as_of, status, created_at, updated_at) "
       "VALUES ('part-tv-1','acc-terravance',1,'region x business unit',20000,"
       "'Client HR summary shared at kickoff','2026-05-04','active',?,?)", (ts, ts))
    segs = [
        ("seg-tv-dach",    "DACH manufacturing",   "Manufacturing", "DACH",    6000, 0, 1),
        ("seg-tv-nordics", "Nordics commercial",   "Commercial",    "Nordics", 3200, 0, 2),
        ("seg-tv-uki",     "UK & Ireland ops",     "Operations",    "UKI",     2400, 0, 3),
        ("seg-tv-pilot",   "Innovation lab",       "R&D",           "DACH",      18, 0, 4),
        ("seg-tv-rest",    "Unallocated",          None,             None,     8382, 1, 9),
    ]
    for sid, name, bu, region, hc, unalloc, order in segs:
        ex("INSERT OR IGNORE INTO population_segments (id, partition_id, account_id, name, "
           "business_unit, region, headcount, headcount_source, headcount_as_of, is_unallocated, "
           "display_order, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (sid, "part-tv-1", "acc-terravance", name, bu, region, hc,
            "Client HR summary", "2026-05-04", unalloc, order, ts, ts))

    # Two comparable headcount periods so the land-and-leave detector has a series to read.
    for sid, q1, q2 in (("seg-tv-dach", 5800, 6000), ("seg-tv-nordics", 3200, 3200)):
        for period, hc, on in (("2026-Q1", q1, "2026-03-31"), ("2026-Q2", hc2 := q2, "2026-06-30")):
            ex("INSERT OR IGNORE INTO population_headcount_observations (id, segment_id, account_id, "
               "period_label, headcount, source_kind, observed_on, created_at, updated_at) "
               "VALUES (?,?,?,?,?,?,?,?,?)",
               (new_id(), sid, "acc-terravance", period, hc, "client_stated", on, ts, ts))

    # --- portfolio-global vocabulary (§1.2, §11) ---
    use_cases = [
        ("uc-perf",   "Performance reviews",  "performance-reviews", 1),
        ("uc-change", "Change & transformation", "change-management", 2),
        ("uc-newmgr", "New-manager transitions", "new-manager-transitions", 3),
    ]
    for uid, name, slug, order in use_cases:
        ex("INSERT OR IGNORE INTO use_cases (id, name, slug, account_id, display_order, created_at, updated_at) "
           "VALUES (?,?,?,NULL,?,?,?)", (uid, name, slug, order, ts, ts))
    for tid, name, slug in (("tag-frontline", "Frontline leaders", "frontline-leaders"),
                            ("tag-hrbp", "HRBPs", "hrbps")):
        ex("INSERT OR IGNORE INTO audience_tags (id, name, slug, created_at, updated_at) "
           "VALUES (?,?,?,?,?)", (tid, name, slug, ts, ts))

    # A composite view: overlaps DACH, so it is never an addend.
    ex("INSERT OR IGNORE INTO population_views (id, account_id, name, estimated_headcount, "
       "headcount_source, headcount_as_of, created_at, updated_at) "
       "VALUES ('view-tv-dach-frontline','acc-terravance','DACH frontline managers',1200,"
       "'Operator estimate from the org chart','2026-06-15',?,?)", (ts, ts))
    ex("INSERT OR IGNORE INTO population_view_segments (view_id, segment_id) "
       "VALUES ('view-tv-dach-frontline','seg-tv-dach')")
    ex("INSERT OR IGNORE INTO population_view_tags (view_id, tag_id) "
       "VALUES ('view-tv-dach-frontline','tag-frontline')")

    # --- the grid: every derived state represented (§1.3) ---
    #    (id, segment, use case, penetration, evidence, blocker, pursuit, paid, sponsor)
    cells = [
        ("cell-tv-1", "seg-tv-dach",    "uc-perf",   "paid", "measured",  "clear", "none",     900, "p-tv-champion"),
        # paid but unevidenced -> the churn-risk state, and the value gap below
        ("cell-tv-2", "seg-tv-dach",    "uc-change", "paid", "none",      "clear", "none",     420, "p-tv-champion"),
        ("cell-tv-3", "seg-tv-nordics", "uc-perf",   "pilot","anecdotal", "clear", "none",       0, "p-tv-progowner"),
        # gated: outranks everything, because the next move is the compliance lane
        ("cell-tv-4", "seg-tv-nordics", "uc-change", "none", "none",      "gated", "none",       0, None),
        ("cell-tv-5", "seg-tv-uki",     "uc-perf",   "none", "none",      "clear", "declined",   0, None),
        ("cell-tv-6", "seg-tv-uki",     "uc-newmgr", "none", "none",      "clear", "none",       0, "p-tv-budget"),
        ("cell-tv-7", "seg-tv-dach",    "uc-newmgr", "none", "none",      "clear", "none",       0, None),
        # below the cohort floor -> density suppressed, never zeroed
        ("cell-tv-8", "seg-tv-pilot",   "uc-perf",   "paid", "anecdotal", "clear", "none",      12, None),
        # stays declined, so the grid shows the state as well as the reopen transition
        ("cell-tv-9", "seg-tv-uki",     "uc-change", "none", "none",      "clear", "declined",   0, None),
    ]
    for cid, seg, uc, pen, ev, bl, po, paid, sponsor in cells:
        ex("INSERT OR IGNORE INTO whitespace_cells (id, account_id, segment_id, use_case_id, "
           "penetration, evidence_state, blocker_state, pursuit_outcome, blocker_lane, "
           "blocker_owner_person_id, declined_reason, declined_on, paid_seats, sponsor_person_id, "
           "next_action, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (cid, "acc-terravance", seg, uc, pen, ev, bl, po,
            "works_council" if bl == "gated" else None,
            "p-tv-workscouncil" if bl == "gated" else None,
            "Regional director wanted to see DACH results first." if po == "declined" else None,
            "2026-04-22" if po == "declined" else None,
            paid, sponsor,
            "Package the DACH readout for the Nordics sponsor." if pen == "pilot" else None, ts, ts))

    # Stage 5 captured the request before cells existed; Stage 5.5 resolves it to the exact
    # whitespace cell so Stage 7 can apply its window and customer-pull precedence honestly.
    ex("UPDATE pull_signals SET cell_id='cell-tv-3', updated_at=? WHERE account_id='acc-terravance' "
       "AND signal_kind='champion_ask' AND cell_id IS NULL", (ts,))

    # A cell on the composite view: 300 of DACH's own paid seats seen through the frontline
    # lens. It must NOT add to the rollup — those people are already counted in seg-tv-dach.
    ex("INSERT OR IGNORE INTO whitespace_cells (id, account_id, view_id, use_case_id, penetration, "
       "evidence_state, blocker_state, pursuit_outcome, paid_seats, created_at, updated_at) "
       "VALUES ('cell-tv-v1','acc-terravance','view-tv-dach-frontline','uc-perf','paid',"
       "'measured','clear','none',300,?,?)", (ts, ts))

    # A declined cell whose reason later changed — the transition, with both halves in history.
    ex("UPDATE whitespace_cells SET pursuit_outcome='none', reopened_on='2026-07-20', "
       "reopened_reason='DACH results published; the regional director asked to revisit.' "
       "WHERE id='cell-tv-5' AND reopened_on IS NULL")
    for cid, fact, before, after, reason, on, state_before, state_after in (
        ("cell-tv-1", "evidence_state", "none", "anecdotal", "Pilot stories cleared the proof bar.", "2026-01-20", "target", "proven"),
        ("cell-tv-1", "penetration",    "pilot", "paid",     "Three-year DACH agreement signed.", "2026-02-10", "proven", "penetrated_unevidenced"),
        ("cell-tv-1", "evidence_state", "anecdotal", "measured", "Q2 manager-quality readout landed.", "2026-06-30", "penetrated_unevidenced", "penetrated"),
        ("cell-tv-2", "penetration",    "none",  "paid",     "Change cohort added to the DACH order.", "2026-05-18", "target", "penetrated_unevidenced"),
        ("cell-tv-5", "pursuit_outcome","none",  "declined", "Regional director wanted DACH results first.", "2026-04-22", "white", "declined"),
        ("cell-tv-5", "reopened",       "declined", "none",  "DACH results published; asked to revisit.", "2026-07-20", "declined", "white"),
    ):
        ex("INSERT OR IGNORE INTO cell_state_history (id, cell_id, fact, before_value, after_value, "
           "reason, changed_on, actor, created_at, derived_state_before, derived_state_after) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (f"csh-{cid}-{fact}-{on}", cid, fact, before, after, reason, on, "operator", ts,
            state_before, state_after))

    # Stage 9 seed learning: one won shape and one lost shape, both tied to a dated transition.
    for entry in (
        ("pbe-tv-1", "cell-tv-1", "csh-cell-tv-1-evidence_state-2026-01-20", "uc-perf",
         "target", "proven", "2026-01-20", "Sponsor-led manager pilot",
         "Pilot stories plus the agreed scorecard", "Start with the live review moment",
         "operational", "2025-12-15", 36, "Sponsor carried the readout without us",
         "Start procurement before the evidence review"),
        ("pbe-tv-2", "cell-tv-5", "csh-cell-tv-5-pursuit_outcome-2026-04-22", "uc-perf",
         "white", "declined", "2026-04-22", "Regional proof-first outreach",
         "DACH evidence was not ready", None, None, "2026-03-20", 33,
         "The objection was made explicit", "Wait for adjacent proof before the ask"),
    ):
        ex("INSERT OR IGNORE INTO playbook_entries (id,account_id,cell_id,transition_history_id,"
           "use_case_id,transition_from,transition_to,transitioned_on,motion_run,evidence_summary,"
           "message_summary,message_layer,motion_started_on,duration_days,what_worked,what_differently,"
           "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (entry[0], "acc-terravance", *entry[1:], ts, ts))

    # --- the value ledger (§2) ---
    md = conn.execute("SELECT id FROM metric_definitions ORDER BY name LIMIT 1").fetchone()
    if md:
        did = md["id"]
        ex("INSERT OR IGNORE INTO value_targets (id, account_id, definition_id, segment_id, "
           "target_value, direction, timeframe_end, accepted_by_person_id, accepted_on, "
           "client_accepted, origin, version, status, created_at, updated_at) "
           "VALUES ('vt-tv-1','acc-terravance',?, 'seg-tv-dach', 0.70,'at_least','2026-09-30',"
           "'p-tv-champion','2026-05-04',1,'scorecard',1,'active',?,?)", (did, ts, ts))
        ex("INSERT OR IGNORE INTO value_targets (id, account_id, definition_id, segment_id, "
           "target_value, direction, timeframe_end, client_accepted, origin, version, status, "
           "created_at, updated_at) "
           "VALUES ('vt-tv-2','acc-terravance',?, 'seg-tv-nordics', 0.65,'at_least','2026-06-30',"
           "0,'business_case',1,'active',?,?)", (did, ts, ts))
        # A fresh, population-scoped observation so the DACH bar reads as realized.
        ex("INSERT OR IGNORE INTO metric_observations (id, definition_id, definition_version, "
           "program_id, population_segment_id, period_label, value, target, current_through, "
           "source_reference_id, created_at, updated_at) VALUES ('obs-tv-dach','" + did +
           "','1','prog-tv-global','seg-tv-dach','2026-07',0.78,0.70,?,"
           "'src-tv-steerdeck',?,?)", (today, ts, ts))
        ex("UPDATE value_targets SET client_visible=1, source_reference_id='src-tv-steerdeck' "
           "WHERE id='vt-tv-1'")
        ex("INSERT OR IGNORE INTO value_target_evidence (id,target_id,object_type,object_id,note,"
           "created_at,updated_at) VALUES ('vte-tv-1','vt-tv-1','metric_observation',"
           "'obs-tv-dach','July scorecard observation',?,?)", (ts, ts))

    # --- funding intelligence (§4) ---
    for pid, name, kind, owner, status, amount in (
        ("fp-tv-1", "Group L&D pool", "central_ld_budget", "p-tv-budget", "confirmed", 480000),
        ("fp-tv-2", "Recovered incumbent spend", "recovered_vendor_spend", "p-tv-budget", "potential", 260000),
        ("fp-tv-3", "Transformation programme", "transformation_program", None, "potential", 150000),
    ):
        ex("INSERT OR IGNORE INTO funding_pools (id, account_id, name, kind, owner_person_id, "
           "status, amount, currency, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'EUR',?,?)",
           (pid, "acc-terravance", name, kind, owner, status, amount, ts, ts))
    ex("UPDATE funding_pools SET client_visible=1, source_reference_id='src-tv-steerdeck' "
       "WHERE id='fp-tv-1'")
    ex("UPDATE whitespace_cells SET client_visible=1, source_reference_id='src-tv-steerdeck' "
       "WHERE id='cell-tv-3'")

    ex("INSERT OR IGNORE INTO fiscal_maps (account_id, fiscal_year_end, planning_window_start, "
       "planning_window_end, budget_request_deadline, works_council_lead_days, confirmed_on, "
       "confirmed_by, created_at, updated_at) VALUES ('acc-terravance','12-31','09-01','10-31',"
       "'10-15',45,'2026-01-20','operator',?,?)", (ts, ts))

    # An ask already in flight, with its earliest steps overdue so escalation is visible.
    ex("INSERT OR IGNORE INTO ask_calendars (id, account_id, name, target_close_date, status, "
       "created_at, updated_at) VALUES ('askcal-tv-1','acc-terravance',"
       "'Nordics wave 2 — 800 seats','2026-11-28','active',?,?)", (ts, ts))
    for i, (kind, label, due) in enumerate([
        ("business_case_delivered", "Business case delivered", "2026-06-15"),
        ("budget_owner_sponsorship", "Budget owner sponsorship secured", "2026-07-10"),
        ("budget_window", "Budget request submitted in planning window", "2026-09-30"),
        ("procurement", "Procurement process started", "2026-10-05"),
        ("works_council", "Works council consultation", "2026-10-14"),
        ("signature", "Signature", "2026-11-28"),
    ]):
        ex("INSERT OR IGNORE INTO ask_calendar_steps (id, calendar_id, kind, label, due_date, "
           "status, display_order, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
           (f"askstep-tv-{i}", "askcal-tv-1", kind, label, due,
            "done" if kind == "business_case_delivered" else "pending", i, ts, ts))

    # --- revenue semantics (§10) ---
    cv = conn.execute("SELECT id, price FROM contract_versions WHERE account_id='acc-terravance' "
                      "AND is_current=1 LIMIT 1").fetchone()
    if cv:
        price = cv["price"] or 0
        ex("UPDATE contract_versions SET currency='EUR', price_basis='arr', term_months=36, "
           "derived_arr=? WHERE id=?", (price, cv["id"]))
        ex("INSERT OR IGNORE INTO revenue_events (id, account_id, contract_version_id, kind, "
           "amount, currency, seats_delta, effective_on, reason, created_at, updated_at) "
           "VALUES ('rev-tv-1','acc-terravance',?,'expansion',180000,'EUR',300,'2026-05-18',"
           "'DACH change cohort added.',?,?)", (cv["id"], ts, ts))


def _seed_stage6_demo(conn):
    """Stage 6 demo rows: an ROI model and one externally-referenceable story, so the champion
    kit has something it is actually safe to hand over. Mock only."""
    if not conn.execute("SELECT 1 FROM accounts WHERE id='acc-terravance'").fetchone():
        return
    ts = now_utc()
    # The strictest visibility class — this is the one a champion presents without us there.
    conn.execute(
        "INSERT OR IGNORE INTO value_stories (id, account_id, program_id, outcome, tags, "
        "evidence_tier, visibility_class, identifiable, is_negative, source_reference_id, "
        "created_at, updated_at) "
        "VALUES ('vs-tv-ext','acc-terravance','prog-tv-global',"
        "'Manager 1:1 consistency rose across the DACH rollout cohort in the first two quarters.',"
        "'manager-quality,dach','measured_operational','externally_referenceable',0,0,"
        "'src-tv-steerdeck',?,?)", (ts, ts))
    # ROI inputs are assumptions and carry an author and a date, or the CHECK rejects them.
    rs = conn.execute("SELECT id FROM recovered_spend WHERE account_id='acc-terravance' LIMIT 1").fetchone()
    conn.execute(
        "INSERT OR IGNORE INTO roi_models (account_id, seat_price, seat_price_currency, "
        "seat_price_basis, retention_uplift_pct, retention_note, recovered_spend_id, "
        "assumptions_note, author, assessed_on, created_at, updated_at) "
        "VALUES ('acc-terravance', 42.0, 'EUR', 'list price, pre-volume-discount', 3.5, "
        "'Operator estimate from the DACH cohort; not a measured figure.', ?, "
        "'Every figure here is an assumption for discussion, not a measurement.', "
        "'operator', '2026-07-15', ?, ?)", (rs["id"] if rs else None, ts, ts))


def _seed_stage75_demo(conn):
    """Stage 7.5 mock thesis: one qualified motion, one earned agreement, and named lines."""
    if not conn.execute("SELECT 1 FROM accounts WHERE id='acc-terravance'").fetchone():
        return
    ts = now_utc()
    contract = conn.execute("SELECT id FROM contract_versions WHERE account_id='acc-terravance' "
                            "AND is_current=1 LIMIT 1").fetchone()
    if not contract or not conn.execute("SELECT 1 FROM value_targets WHERE id='vt-tv-1'").fetchone():
        return
    conn.execute("UPDATE ask_calendars SET opportunity_id='xo-tv-3k' WHERE id='askcal-tv-1'")
    conn.execute("UPDATE expansion_opportunities SET qualification_value_target_id='vt-tv-1',"
                 "qualification_ask_calendar_id='askcal-tv-1',"
                 "qualification_champion_person_id='p-tv-champion',"
                 "qualification_program_id='prog-tv-global',funding_pool_id='fp-tv-1' "
                 "WHERE id='xo-tv-3k'")
    conn.execute(
        "INSERT OR IGNORE INTO operational_agreements "
        "(id,account_id,contract_version_id,name,source_kind,source_reference_id,value_target_id,"
        "effective_on,expires_on,seat_band_min,seat_band_max,unit_price,currency,agreed_process,"
        "budget_owner_person_id,action_window_days,status,client_visible,created_at,updated_at) "
        "VALUES ('oa-tv-1','acc-terravance',?,'DACH proof unlocks Nordics wave','signed_paper',"
        "'src-tv-steerdeck','vt-tv-1','2026-06-01','2026-12-31',500,800,42,'EUR',"
        "'Notify the budget owner and issue the pre-priced Nordics order form.',"
        "'p-tv-budget',14,'active',1,?,?)", (contract["id"], ts, ts))
    conn.execute(
        "INSERT OR IGNORE INTO account_growth_plans "
        "(id,account_id,name,target_seats,target_date,status,notes,created_at,updated_at) "
        "VALUES ('gp-tv-1','acc-terravance','FY27 account growth thesis',3000,'2026-12-15',"
        "'active','Named base-population lines only; no use-case seat summing.',?,?)", (ts, ts))
    for line in (
        ("gpl-tv-1", "Nordics wave 2", "seg-tv-nordics", "cell-tv-3", 800, 0.70, "committed", "2026-09-30", None),
        ("gpl-tv-2", "UKI manager rollout", "seg-tv-uki", "cell-tv-6", 700, 0.45, "planned", "2026-10-15", None),
        ("gpl-tv-3", "DACH evidence-led expansion", "seg-tv-dach", "cell-tv-1", 300, 1.0, "funded", "2026-02-10", "2026-02-10"),
    ):
        conn.execute(
            "INSERT OR IGNORE INTO growth_plan_lines "
            "(id,plan_id,account_id,name,segment_id,cell_id,opportunity_id,budget_owner_person_id,"
            "funding_pool_id,ask_calendar_id,seat_count,seat_price_low,seat_price_high,seat_price_currency,"
            "seat_price_basis,probability,"
            "probability_author,probability_assessed_on,ask_date,status,funded_on,client_visible,"
            "source_reference_id,created_at,updated_at) "
            "VALUES (?,'gp-tv-1','acc-terravance',?,?,?,'xo-tv-3k','p-tv-budget','fp-tv-1',"
            "'askcal-tv-1',?,38,42,'EUR','annual_recurring',?,'operator','2026-07-31',?,?,?,1,'src-tv-steerdeck',?,?)",
            (line[0], line[1], line[2], line[3], line[4], line[5], line[7], line[6], line[8], ts, ts))


def _seed_internal_ops_demo(conn):
    """Five-account Stage 10 proof: periods, chain, coverage, and feedback aggregation."""
    ts = now_utc()
    # Complete the intentionally small book with two synthetic accounts.
    for aid, name, pid, person in (
        ("acc-harbor", "Harborline Manufacturing", "p-harbor-sponsor", "Morgan Hale"),
        ("acc-summit", "Summit Retail Group", "p-summit-sponsor", "Avery Chen"),
    ):
        conn.execute("INSERT OR IGNORE INTO accounts(id,name,created_at,updated_at) VALUES (?,?,?,?)", (aid, name, ts, ts))
        conn.execute("INSERT OR IGNORE INTO persons(id,name,affiliation,account_id,title,created_at,updated_at) VALUES (?,?, 'client',?,'Executive sponsor',?,?)", (pid, person, aid, ts, ts))
        conn.execute("INSERT OR IGNORE INTO programs(id,account_id,name,phase,created_at,updated_at) VALUES (?,?,?,'foundation',?,?)", (f"prog-{aid[4:]}", aid, "Enterprise rollout", ts, ts))
        conn.execute("INSERT OR IGNORE INTO interactions(id,account_id,program_id,occurred_on,type,summary,meaningful_touch,created_at,updated_at) VALUES (?,?,?,?, 'meeting','Internal Ops synthetic review touch',1,?,?)", (f"int-{aid[4:]}", aid, f"prog-{aid[4:]}", "2026-07-25", ts, ts))
        conn.execute("INSERT OR IGNORE INTO interaction_participants(interaction_id,person_id) VALUES (?,?)", (f"int-{aid[4:]}", pid))
        conn.execute("INSERT OR IGNORE INTO interaction_participants(interaction_id,person_id) VALUES (?,?)", (f"int-{aid[4:]}", "p-val-operator"))

    # Roster coverage across all five accounts; interaction participation remains touch truth.
    for aid in ("acc-terravance", "acc-northwind", "acc-bluepeak", "acc-harbor", "acc-summit"):
        conn.execute("INSERT OR IGNORE INTO account_internal_roster(id,account_id,person_id,role,standing_responsibilities,coverage_type,active_from,expected_touch_cadence_days,created_at,updated_at) VALUES (?,?,?,'account_lead','Own account operating rhythm','primary','2026-07-01',21,?,?)", (f"roster-{aid}-lead", aid, "p-val-operator", ts, ts))
        conn.execute("INSERT OR IGNORE INTO account_internal_roster(id,account_id,person_id,role,standing_responsibilities,coverage_type,active_from,created_at,updated_at) VALUES (?,?,?,'supporting_em','Provide two-week backup coverage','backup','2026-07-01',?,?)", (f"roster-{aid}-backup", aid, "p-val-cs", ts, ts))

    interaction = conn.execute("SELECT id FROM interactions WHERE account_id='acc-terravance' ORDER BY occurred_on DESC LIMIT 1").fetchone()
    northwind_interaction = conn.execute("SELECT id FROM interactions WHERE account_id='acc-northwind' ORDER BY occurred_on DESC LIMIT 1").fetchone()
    if interaction:
        conn.execute("INSERT OR IGNORE INTO account_reviews(id,account_id,review_type,scheduled_on,held_on,chair_person_id,source_interaction_id,status,created_at,updated_at) VALUES ('review-tv-q3','acc-terravance','quarterly','2026-07-24','2026-07-24','p-val-operator',?,'held',?,?)", (interaction["id"], ts, ts))
        conn.execute("INSERT OR IGNORE INTO account_review_participants(review_id,person_id,role) VALUES ('review-tv-q3','p-val-operator','chair')")
        conn.execute("INSERT OR IGNORE INTO operator_views(id,account_id,body,author,assessed_on,created_at,updated_at) VALUES ('pov-tv-1','acc-terravance','Expansion is defensible only if the evidence gap and Data dependency close before the budget window.','operator','2026-07-31',?,?)", (ts, ts))
        conn.execute("INSERT OR IGNORE INTO commitments(id,account_id,account_review_id,commitment_class,description,responsible_party_id,internal_owner_id,due_date,status,source_interaction_id,client_visible,created_at,updated_at) VALUES ('commit-leadership-tv','acc-terravance','review-tv-q3','leadership_to_operator','Fund the executive sponsor touch','p-val-cs','p-val-operator','2026-07-20','open',?,0,?,?)", (interaction["id"], ts, ts))

    # Two closed periods provide small-sample calibration without manufactured percentages.
    for period_id, name, start, end in (
        ("forecast-fy26-q1", "FY26 Q1", "2026-01-01", "2026-03-31"),
        ("forecast-fy26-q2", "FY26 Q2", "2026-04-01", "2026-06-30"),
    ):
        conn.execute("INSERT OR IGNORE INTO forecast_periods(id,name,starts_on,ends_on,cadence,scenario_type,timezone,status,locked_at,locked_by,closed_at,closed_by,created_at,updated_at) VALUES (?,?,?,?,'quarterly','operating','America/New_York','closed',?,'operator',?,'operator',?,?)", (period_id, name, start, end, f"{start}T14:00:00+00:00", f"{end}T21:00:00+00:00", ts, ts))
        conn.execute("INSERT OR IGNORE INTO forecast_opening_snapshots(id,period_id,locked_at,locked_by,created_at) VALUES (?,?,?,?,?)", (f"snapshot-{period_id}", period_id, f"{start}T14:00:00+00:00", "operator", ts))

    for idx, (period_id, aid, category, amount, won) in enumerate((
        ("forecast-fy26-q1", "acc-harbor", "commit", 80000, True),
        ("forecast-fy26-q1", "acc-summit", "best_case", 50000, False),
        ("forecast-fy26-q2", "acc-harbor", "best_case", 90000, True),
        ("forecast-fy26-q2", "acc-summit", "commit", 60000, False),
    ), 1):
        opp_id, entry_id = f"internal-opp-{idx}", f"forecast-entry-{idx}"
        outcome = "won" if won else "deferred"
        conn.execute("INSERT OR IGNORE INTO expansion_opportunities(id,account_id,name,budget_state,status,outcome,outcome_reason,created_at,updated_at) VALUES (?,?,?,'formally_allocated','closed',?,?,?,?)", (opp_id, aid, f"Internal Ops motion {idx}", outcome, "Synthetic calibration outcome", ts, ts))
        conn.execute("INSERT OR IGNORE INTO forecast_entries(id,period_id,account_id,opportunity_id,category,amount,currency,price_basis,probability,probability_rationale,author,assessed_on,created_at,updated_at) VALUES (?,?,?,?,?,?,'USD','arr',0.6,'Synthetic operator assumption','operator',?,?,?)", (entry_id, period_id, aid, opp_id, category, amount, "2026-01-01" if "q1" in period_id else "2026-04-01", ts, ts))
        conn.execute("INSERT OR IGNORE INTO forecast_opening_lines(id,snapshot_id,entry_id,account_id,target_type,target_id,category,amount,currency,price_basis,probability,source_manifest_json,created_at) VALUES (?,?,?,?, 'opportunity',?,?,?,'USD','arr',0.6,'[]',?)", (f"opening-line-{idx}", f"snapshot-{period_id}", entry_id, aid, opp_id, category, amount, ts))
        if won:
            effective = "2026-03-15" if "q1" in period_id else "2026-06-15"
            conn.execute("INSERT OR IGNORE INTO revenue_events(id,account_id,opportunity_id,kind,amount,currency,price_basis,effective_on,reason,created_at,updated_at) VALUES (?,?,?,'expansion',?,'USD','arr',?,'Synthetic dated actual',?,?)", (f"rev-internal-{idx}", aid, opp_id, amount, effective, ts, ts))

    if interaction:
        conn.execute("INSERT OR IGNORE INTO internal_asks(id,account_id,need,success_condition,ask_type,requested_by_person_id,requested_from_function_id,current_owner_person_id,needed_by,status,source_interaction_id,created_at,updated_at) VALUES ('ask-tv-data','acc-terravance','Produce QBR cohort cut','Attach the sourced cohort table','data_request','p-val-operator','function-data','p-val-data','2026-07-20','in_progress',?,?,?)", (interaction["id"], ts, ts))
        conn.execute("INSERT OR IGNORE INTO internal_ask_events(id,ask_id,event_type,status_after,reason,actor,occurred_at,created_at) VALUES ('ask-tv-created','ask-tv-data','created','raised','Ask raised','operator','2026-07-15T14:00:00+00:00',?)", (ts,))
        conn.execute("INSERT OR IGNORE INTO internal_ask_events(id,ask_id,event_type,status_before,status_after,reason,actor,occurred_at,created_at) VALUES ('ask-tv-started','ask-tv-data','started','raised','in_progress','Data acknowledged','operator','2026-07-16T14:00:00+00:00',?)", (ts,))
        conn.execute("INSERT OR IGNORE INTO escalation_instances(id,ask_id,default_id,severity,path_type,threshold_business_hours,destination_function_id,expected_response_hours,next_step,opened_at,opened_by,status,created_at,updated_at) VALUES ('esc-tv-data','ask-tv-data','esc-data-high','high','functional',8,'function-data',4,'Escalate to Data leadership and restate the blocked deliverable.','2026-07-21T14:00:00+00:00','operator','open',?,?)", (ts, ts))
        conn.execute("INSERT OR IGNORE INTO escalation_events(id,escalation_id,event_type,destination_function_id,threshold_reason,actor,occurred_at,created_at) VALUES ('esc-tv-raised','esc-tv-data','raised','function-data','Past snapshotted business-time threshold','operator','2026-07-21T14:00:00+00:00',?)", (ts,))

    if interaction and northwind_interaction:
        tv_person = conn.execute("SELECT id FROM persons WHERE account_id='acc-terravance' ORDER BY created_at LIMIT 1").fetchone()
        nw_person = conn.execute("SELECT id FROM persons WHERE account_id='acc-northwind' ORDER BY created_at LIMIT 1").fetchone()
        if tv_person and nw_person:
            conn.execute("INSERT OR IGNORE INTO product_feedback_items(id,title,problem_statement,feedback_type,owner_function_id,status,status_rationale,created_at,updated_at) VALUES ('feedback-localized-nudges','Localized manager nudges','Managers need nudges in local languages','localization','function-product','roadmapped','Accepted for roadmap',?,?)", (ts, ts))
            for oid, aid, person_id, iid, span in (("feedback-tv","acc-terravance",tv_person["id"],interaction["id"],"German manager nudges"),("feedback-nw","acc-northwind",nw_person["id"],northwind_interaction["id"],"French manager nudges")):
                conn.execute("INSERT OR IGNORE INTO product_feedback_occurrences(id,feedback_item_id,account_id,stakeholder_person_id,source_interaction_id,source_span,impact,captured_by,captured_on,created_at,updated_at) VALUES (?,'feedback-localized-nudges',?,?,?,?,?,'operator','2026-07-25',?,?)", (oid, aid, person_id, iid, span, "Adoption risk", ts, ts))


def _seed_stage11_demo(conn):
    """Stage 11 demo: one ACTIVE campaign mid-flight and one COMPLETED campaign, on Terravance.

    The active one is deliberately signal-triggered with a `pre_post` design, because that is the
    combination the §5.2 caution exists for — the demo should show the regression-to-the-mean
    warning rendering, not hide it. The completed one uses a comparator against Nordics (disjoint
    from the treated DACH cohort) and lands on `improved_not_met`, so the screen shows an honest
    partial result rather than a success story. Mock only.
    """
    if not conn.execute("SELECT 1 FROM accounts WHERE id='acc-terravance'").fetchone():
        return
    ts, today = now_utc(), now_utc()[:10]
    ex = conn.execute

    def day(n):
        return (_dt.date.fromisoformat(today) + _dt.timedelta(days=n)).isoformat()

    src = ex("SELECT id FROM source_references LIMIT 1").fetchone()
    src_id = src["id"] if src else None
    definition = ex("SELECT id FROM metric_definitions ORDER BY name LIMIT 1").fetchone()
    if not definition:
        return
    did = definition["id"]

    # A prior series so the locked baseline has a trajectory to sit in (§5.1). Without these the
    # campaign would render the "no prior trajectory" caution, which is honest but not the demo.
    for i, (value, ago) in enumerate(((0.38, 120), (0.44, 90), (0.49, 60))):
        ex("INSERT OR IGNORE INTO metric_observations (id, definition_id, definition_version, "
           "program_id, population_segment_id, period_label, value, target, current_through, "
           "created_at, updated_at) VALUES (?,?,'1','prog-tv-global','seg-tv-dach',?,?,0.70,?,?,?)",
           (f"obs-tv-camp-{i}", did, f"2026-M{i}", value, day(-ago), ts, ts))

    # The campaign's own bar, deliberately above the current reading so the demo shows a
    # campaign genuinely in flight rather than one whose goal was already met.
    ex("INSERT OR IGNORE INTO value_targets (id, account_id, definition_id, segment_id, "
       "target_value, direction, timeframe_end, accepted_by_person_id, accepted_on, "
       "client_accepted, origin, version, status, created_at, updated_at) "
       "VALUES ('vt-tv-camp','acc-terravance',?, 'seg-tv-dach', 0.85,'at_least',?,"
       "'p-tv-champion',?,1,'scorecard',1,'active',?,?)", (did, day(40), day(-36), ts, ts))

    # Terravance ships no seeded task, so create the one the campaign embeds. Plan links point at
    # canonical execution records — the campaign never invents its own to-do.
    ex("INSERT OR IGNORE INTO tasks (id, program_id, description, internal_owner_id, due_date, "
       "status, created_at, updated_at) VALUES ('tk-tv-embed','prog-tv-global',"
       "'Embed the review prompt in the manager workflow','p-val-operator',?,'done',?,?)",
       (day(-20), ts, ts))
    ex("INSERT OR IGNORE INTO tasks (id, program_id, description, internal_owner_id, due_date, "
       "status, created_at, updated_at) VALUES ('tk-tv-clinic','prog-tv-global',"
       "'Run the change-conversation clinic for DACH managers','p-val-operator',?,'done',?,?)",
       (day(-170), ts, ts))

    # The signal that proposed the active campaign — selection on a declining reading.
    ex("INSERT OR IGNORE INTO signal_episodes (id, account_id, program_id, kind, condition_key, "
       "source_kind, explanation, freshness_as_of, opened_at, last_evaluated_at, created_at, updated_at) "
       "VALUES ('sig-tv-stalled','acc-terravance','prog-tv-global','stalled_cohort',"
       "'stalled:vt-tv-1','usage','Cohort stalled across fresh observations: 0.52 -> 0.49.',?,?,?,?,?)",
       (today, ts, ts, ts, ts))

    # --- the active campaign -------------------------------------------------------------------
    ex("INSERT OR IGNORE INTO adoption_campaigns (id, account_id, program_id, segment_id, "
       "use_case_id, name, target_behavior, hypothesis, planned_start_on, planned_end_on, "
       "evaluation_on, internal_owner_person_id, client_sponsor_person_id, lead_champion_person_id, "
       "evaluation_design, status, sponsor_gap_reason, created_from_signal_episode_id, "
       "diagnosis_source_reference_id, created_at, updated_at) "
       "VALUES ('camp-tv-active','acc-terravance','prog-tv-global','seg-tv-dach','uc-perf',"
       "'DACH review-cycle adoption',"
       "'DACH people managers hold a documented review conversation each cycle',"
       "'If the prompt sits inside the review workflow at cycle open, managers will use it, "
       "because the barrier is workflow placement rather than willingness',"
       "?,?,?, 'p-val-operator','p-tv-champion','p-tv-champion','pre_post','active',NULL,"
       "'sig-tv-stalled',?,?,?)",
       (day(-35), day(25), day(40), src_id, ts, ts))

    # The episode points back at the campaign it produced. Without this the UI would offer to
    # propose a second campaign from a signal that already has one (§7.2).
    ex("UPDATE signal_episodes SET status='attached', adoption_campaign_id='camp-tv-active', "
       "updated_at=? WHERE id='sig-tv-stalled'", (ts,))

    for status_from, status_to, reason, when in (
        (None, "draft", "Converted from the stalled-cohort signal.", day(-40)),
        ("draft", "ready", "Barrier diagnosed, plan agreed, baseline locked.", day(-36)),
        ("ready", "active", "Cycle opened; prompt shipped into the review flow.", day(-35)),
    ):
        ex("INSERT OR IGNORE INTO adoption_campaign_state_history (id, campaign_id, from_status, "
           "to_status, reason, actor, changed_on, created_at) VALUES (?,?,?,?,?,'operator',?,?)",
           (f"cshist-{status_to}", "camp-tv-active", status_from, status_to, reason, when, ts))

    ex("INSERT OR IGNORE INTO adoption_campaign_barriers (id, campaign_id, category, description, "
       "confidence, observed_on, source_reference_id, is_primary, state, created_at, updated_at) "
       "VALUES ('camp-bar-1','camp-tv-active','opportunity',"
       "'The prompt lives in a separate tool, so managers meet it only if they go looking.',"
       "'observed',?,?,1,'addressed',?,?)", (day(-45), src_id, ts, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_barriers (id, campaign_id, category, description, "
       "confidence, observed_on, source_reference_id, is_primary, state, created_at, updated_at) "
       "VALUES ('camp-bar-2','camp-tv-active','motivation',"
       "'Regional GMs describe the conversation as a form-filling exercise rather than useful.',"
       "'reported',?,?,0,'open',?,?)", (day(-45), src_id, ts, ts))

    ex("INSERT OR IGNORE INTO adoption_campaign_targets (id, campaign_id, value_target_id, role, "
       "baseline_observation_id, baseline_locked_on, baseline_trajectory_json, created_at, updated_at) "
       "VALUES ('camp-tgt-1','camp-tv-active','vt-tv-camp','primary','obs-tv-camp-2',?,?,?,?)",
       (day(-36),
        '[{"observation_id":"obs-tv-camp-0","value":0.38,"current_through":"' + day(-120) + '"},'
        '{"observation_id":"obs-tv-camp-1","value":0.44,"current_through":"' + day(-90) + '"}]',
        ts, ts))

    # Plan links point at records that already exist; nothing is cloned.
    moment = ex("SELECT id FROM deployment_moments WHERE program_id='prog-tv-global' LIMIT 1").fetchone()
    ex("INSERT OR IGNORE INTO adoption_campaign_plan_links (id, campaign_id, sequence, "
       "intervention_kind, intended_barrier_id, purpose, cue, is_reinforcement, task_id, "
       "created_at, updated_at) VALUES ('camp-plan-1','camp-tv-active',1,'workflow_embed',"
       "'camp-bar-1','Put the prompt where the work already happens.',"
       "'Review cycle opens',0,'tk-tv-embed',?,?)", (ts, ts))
    if moment:
        ex("INSERT OR IGNORE INTO adoption_campaign_plan_links (id, campaign_id, sequence, "
           "intervention_kind, intended_barrier_id, purpose, cue, is_reinforcement, "
           "deployment_moment_id, created_at, updated_at) VALUES ('camp-plan-2','camp-tv-active',2,"
           "'reinforcement','camp-bar-2','Champion shares two real examples at the mid-cycle check.',"
           "'Mid-cycle GM forum',1,?,?,?)", (moment["id"], ts, ts))

    ex("INSERT OR IGNORE INTO adoption_campaign_checkpoints (id, campaign_id, scheduled_on, held_on, "
       "observations_reviewed_json, assessment, decision, reason, next_evidence_on, created_at, updated_at) "
       "VALUES ('camp-cp-1','camp-tv-active',?,?,'[\"obs-tv-dach\"]','on_track','continue',"
       "'Uptake rising but the motivation barrier is unaddressed; adding the champion examples.',?,?,?)",
       (day(-10), day(-10), day(15), ts, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_checkpoints (id, campaign_id, scheduled_on, "
       "next_evidence_on, created_at, updated_at) VALUES ('camp-cp-2','camp-tv-active',?,?,?,?)",
       (day(15), day(25), ts, ts))

    # --- the completed campaign ------------------------------------------------------------------
    # Comparator design against Nordics, which shares no base segment with DACH (§5.2).
    ex("INSERT OR IGNORE INTO adoption_campaigns (id, account_id, program_id, segment_id, "
       "use_case_id, name, target_behavior, hypothesis, planned_start_on, planned_end_on, "
       "evaluation_on, internal_owner_person_id, client_sponsor_person_id, evaluation_design, "
       "status, completion_outcome, completion_reviewed_on, completion_note, sponsor_gap_reason, "
       "diagnosis_source_reference_id, created_at, updated_at) "
       "VALUES ('camp-tv-done','acc-terravance','prog-tv-global','seg-tv-dach','uc-change',"
       "'DACH change-conversation pilot',"
       "'Managers in the change cohort run a structured conversation during restructure',"
       "'If we give managers a one-page guide plus a live clinic, they will hold the conversation, "
       "because the barrier is confidence rather than access',"
       "?,?,?, 'p-val-operator','p-tv-champion','comparator','completed','improved_not_met',?,"
       "'Uptake rose and stayed above the pre-campaign trajectory, but short of the agreed bar. "
       "The comparator cohort moved less over the same window; this is association, not proof.',"
       "NULL,?,?,?)",
       (day(-180), day(-120), day(-110), day(-105), src_id, ts, ts))
    for status_from, status_to, reason, when in (
        (None, "draft", "Opened after the restructure was confirmed.", day(-190)),
        ("draft", "ready", "Guide drafted, clinic scheduled, baseline locked.", day(-185)),
        ("ready", "active", "Restructure announced; clinic ran.", day(-180)),
        ("active", "completed", "Evaluation window closed and reviewed with the sponsor.", day(-105)),
    ):
        ex("INSERT OR IGNORE INTO adoption_campaign_state_history (id, campaign_id, from_status, "
           "to_status, reason, actor, changed_on, created_at) VALUES (?,?,?,?,?,'operator',?,?)",
           (f"cshist-done-{status_to}", "camp-tv-done", status_from, status_to, reason, when, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_barriers (id, campaign_id, category, description, "
       "confidence, observed_on, source_reference_id, is_primary, state, resolution_note, "
       "created_at, updated_at) VALUES ('camp-bar-3','camp-tv-done','capability',"
       "'Managers had not run a change conversation before and asked for a worked example.',"
       "'observed',?,?,1,'addressed','The clinic closed this; the residual gap was motivation.',?,?)",
       (day(-190), src_id, ts, ts))

    # Comparator target: Nordics shares no base segment with DACH, so it is a legitimate control
    # under §5.2. Observations for both cohorts over the same window let the readout show the
    # treated delta beside an untreated one.
    ex("INSERT OR IGNORE INTO value_targets (id, account_id, definition_id, segment_id, "
       "target_value, direction, timeframe_end, accepted_by_person_id, accepted_on, "
       "client_accepted, origin, version, status, created_at, updated_at) "
       "VALUES ('vt-tv-done','acc-terravance',?, 'seg-tv-dach', 0.60,'at_least',?,"
       "'p-tv-champion',?,1,'business_case',1,'active',?,?)", (did, day(-110), day(-185), ts, ts))
    for ident, seg, value, ago in (
        ("obs-tv-done-base", "seg-tv-dach", 0.31, 185),
        ("obs-tv-done-post", "seg-tv-dach", 0.52, 110),
        ("obs-tv-comp-base", "seg-tv-nordics", 0.29, 185),
        ("obs-tv-comp-post", "seg-tv-nordics", 0.33, 110),
    ):
        ex("INSERT OR IGNORE INTO metric_observations (id, definition_id, definition_version, "
           "program_id, population_segment_id, period_label, value, current_through, "
           "created_at, updated_at) VALUES (?,?,'1','prog-tv-global',?,?,?,?,?,?)",
           (ident, did, seg, ident[-4:], value, day(-ago), ts, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_targets (id, campaign_id, value_target_id, role, "
       "baseline_observation_id, baseline_locked_on, baseline_trajectory_json, "
       "comparator_segment_id, created_at, updated_at) "
       "VALUES ('camp-tgt-2','camp-tv-done','vt-tv-done','primary','obs-tv-done-base',?,'[]',"
       "'seg-tv-nordics',?,?)", (day(-185), ts, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_plan_links (id, campaign_id, sequence, "
       "intervention_kind, intended_barrier_id, purpose, cue, is_reinforcement, task_id, "
       "created_at, updated_at) VALUES ('camp-plan-3','camp-tv-done',1,'enablement',"
       "'camp-bar-3','A worked example plus a live clinic before the restructure lands.',"
       "'Restructure announced',0,'tk-tv-clinic',?,?)", (ts, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_checkpoints (id, campaign_id, scheduled_on, "
       "held_on, observations_reviewed_json, assessment, decision, reason, created_at, updated_at) "
       "VALUES ('camp-cp-3','camp-tv-done',?,?,'[\"obs-tv-done-post\"]','at_risk','complete',"
       "'Uptake improved but plateaued below the bar; closing rather than extending.',?,?)",
       (day(-115), day(-110), ts, ts))

    # --- Stage 11.2: the completion retrospective (§8) --------------------------------------------
    # Deliberately an honest one. The diagnosed barrier was capability; what was actually in the way
    # was opportunity, and the demo is more useful showing that gap than showing a clean success.
    ex("INSERT OR IGNORE INTO adoption_campaign_retrospectives (id, campaign_id, "
       "barrier_actually_present, barrier_note, what_to_reuse, what_to_change, follow_on, "
       "follow_on_note, shape_json, reviewed_on, author, created_at, updated_at) "
       "VALUES ('camp-retro-1','camp-tv-done','opportunity',"
       "'We diagnosed a capability gap and built a worked example. Managers understood it fine; "
       "there was no slot in the Nordics review cycle to use it.',"
       "'The worked example itself — it was reused verbatim by the DACH campaign.',"
       "'Check the cohort has a recurring moment to attach to before building enablement.',"
       "'different_intervention',"
       "'Re-run against the same cohort once the Q3 review cycle opens, embedding in the workflow "
       "rather than training ahead of it.',?,?,'operator',?,?)",
       (json.dumps({"use_case_id": "uc-perf", "use_case": "Performance reviews",
                    "cross_account_eligible": True, "population_kind": "segment",
                    "audience_tag_ids": [], "audience_tags": []}, sort_keys=True),
        day(-110), ts, ts))
    ex("INSERT OR IGNORE INTO adoption_campaign_retrospective_interventions (id, retrospective_id, "
       "plan_link_id, verdict, note, created_at, updated_at) "
       "VALUES ('camp-retro-int-1','camp-retro-1','camp-plan-3','appeared_not_to_help',"
       "'The clinic was well attended and changed nothing measurable — the constraint was not "
       "knowledge.',?,?)", (ts, ts))


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
            for pl in mdata.get("play_definitions", []):
                _insert(conn, "play_definitions", pl)
        # Stage 5 — role-based messaging library (§3.12) + relationship-intelligence demo rows.
        msg_n = _seed_messaging_library(conn)
        _seed_stage5_demo(conn)
        # Stage 5.5 — whitespace map, value ledger, funding intelligence.
        _seed_stage55_demo(conn)
        # Stage 6 — ROI model + externally-referenceable evidence for the champion kit.
        _seed_stage6_demo(conn)
        # Stage 11 — one active and one completed adoption campaign.
        _seed_stage11_demo(conn)
        # Stage 7.5 — qualification, operational agreement, renewal, and growth thesis.
        _seed_stage75_demo(conn)
        # Stage 10 — five-account internal operating proof.
        _seed_internal_ops_demo(conn)
        # Stage 12 — explicit, versioned operator writing rules. Runs are created through the
        # normal job path so the seed never pretends a model answer already happened.
        ts = now_utc()
        conn.execute(
            "INSERT OR IGNORE INTO writing_style_profiles "
            "(id,name,audience,version,rules_json,effective_on,author,is_active,created_at,updated_at) "
            "VALUES ('style-internal-v1','Operator concise internal','internal',1,?,?,'operator',1,?,?)",
            (json.dumps({"no_em_dash": False, "max_characters": 6000,
                         "max_headings": 6, "banned_phrases": ["model confidence"]},
                        sort_keys=True), now_utc()[:10], ts, ts))
        print(f"[seed] messaging library entries: {msg_n}")

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
