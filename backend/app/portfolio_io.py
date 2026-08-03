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
    "messaging_entries", "play_definitions", "internal_functions", "status_criteria_versions",
    "escalation_defaults", "report_templates", "document_kinds", "writing_style_profiles",
    "copilot_configurations", "company_event_kinds", "company_entities", "company_identifiers",
    "intel_documents", "intel_document_spans",
    "accounts", "account_settings", "account_company_links", "company_watch_profiles", "persons", "programs",
    # 0034 — read-only copilot runs and immutable claim support
    "copilot_runs", "copilot_run_sources", "copilot_claims", "copilot_claim_sources",
    "copilot_feedback", "copilot_feedback_reviews",
    "account_change_checkpoints",
    "stakeholder_roles", "interactions", "interaction_participants", "capture_inbox_items",
    "account_reviews", "account_review_participants", "operator_views",
    "tasks", "commitments", "decisions", "risks", "issues", "milestones",
    "expansion_opportunities", "contract_versions", "phase_gates", "phase_gate_items",
    "deployment_moments", "compliance_items", "scope_changes",
    "value_stories", "relationship_edges", "recovered_spend",
    # 0012-0016 — onboarding, people intelligence, ingestion, relationships
    "checklist_items", "advocacy_events", "comm_messages", "association_hints",
    "champion_candidates", "exec_pairings",
    # 0017-0019 — whitespace, value ledger, funding (population objects precede the cells,
    # observations, and targets that reference them)
    "population_partitions", "population_segments", "population_views",
    "copilot_entity_aliases",
    "population_view_segments", "population_view_tags", "population_headcount_observations",
    # 0035 — sequences precede their canonical comms waves; population precedes audience FKs.
    "comms_sequences", "comms_entries",
    "metric_observations", "whitespace_cells", "pull_signals", "cell_state_history", "cell_evidence_links",
    "value_targets", "value_target_evidence",
    "funding_pools", "fiscal_maps", "ask_calendars", "ask_calendar_steps", "revenue_events",
    # 0020 — generated artifacts and the ROI assumptions behind the champion kit
    "roi_models", "generated_documents",
    # 0031 — adoption campaigns. Campaign first: barriers, targets, plan links and checkpoints
    # all reference it, and plan links reference barriers.
    "adoption_campaigns", "adoption_campaign_state_history", "adoption_campaign_barriers",
    "adoption_campaign_targets", "adoption_campaign_plan_links", "adoption_campaign_checkpoints",
    "adoption_campaign_retrospectives", "adoption_campaign_retrospective_interventions",
    "generated_document_people",
    # 0022 — recurring signals, mock calendar, and confirmed org change
    "calendar_events", "calendar_event_attendees", "org_change_flags", "succession_records",
    # 0036-0037 — company events precede convergence; signal composition follows episodes.
    "company_events", "company_event_evidence", "company_link_keywords", "company_event_links",
    "hiring_postings", "hiring_observations", "company_convergences", "company_convergence_events",
    "signal_episodes", "signal_episode_company_events",
    # 0023 — Stage 7.5 qualification links, operational triggers, and growth plans
    "operational_agreements", "operational_agreement_events",
    "account_growth_plans", "growth_plan_lines",
    # 0027-0028 — internal operating layer
    "forecast_periods", "forecast_entries", "forecast_entry_sources", "forecast_change_events",
    "forecast_opening_snapshots", "forecast_opening_lines", "renewal_outcome_events",
    "product_feedback_items", "product_feedback_occurrences", "product_feedback_events",
    "product_feedback_touches", "account_internal_roster",
    "internal_asks", "internal_ask_events", "internal_ask_documents", "account_status_assessments",
    "escalation_instances", "escalation_events",
    "generated_document_sources", "forecast_submissions", "forecast_submission_lines",
    # 0025 — Stage 9 learning records (after cells/history, before tag joins)
    "playbook_entries", "playbook_entry_tags",
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
    for tbl in ("stakeholder_roles", "tasks", "risks", "issues",
                "milestones", "deployment_moments", "comms_entries", "compliance_items", "scope_changes"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE program_id IN ({pq})", pids) if pids else []
    t["comms_sequences"] = _all(
        conn, f"SELECT * FROM comms_sequences WHERE program_id IN ({pq})", pids) if pids else []
    # Direct account scope is authoritative for these generalized ledgers; program-only
    # filtering silently dropped internal review commitments and decisions.
    for tbl in ("commitments", "decisions"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    for tbl in ("expansion_opportunities", "contract_versions", "value_stories", "relationship_edges", "recovered_spend"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    t["phase_gates"] = _all(conn, f"SELECT * FROM phase_gates WHERE program_id IN ({pq})", pids) if pids else []
    t["phase_gate_items"] = _all(conn, f"SELECT * FROM phase_gate_items WHERE gate_id IN ({gq})", gids) if gids else []

    # --- 0012-0016: onboarding, people intelligence, ingestion, relationships ---
    t["account_settings"] = _all(conn, "SELECT * FROM account_settings WHERE account_id=?", (account_id,))
    # --- 0036-0038: canonical company identity, exact evidence, and persisted convergence ---
    t["account_company_links"] = _all(conn, "SELECT * FROM account_company_links WHERE account_id=?", (account_id,))
    t["company_watch_profiles"] = _all(conn, "SELECT * FROM company_watch_profiles WHERE account_id=?", (account_id,))
    t["company_event_kinds"] = _all(conn, "SELECT * FROM company_event_kinds WHERE archived=0")
    entity_ids = [row["company_entity_id"] for row in t["account_company_links"]]
    eq = ",".join("?" * len(entity_ids)) or "''"
    t["company_entities"] = _all(conn, f"SELECT * FROM company_entities WHERE id IN ({eq})", entity_ids) if entity_ids else []
    t["company_identifiers"] = _all(conn, f"SELECT * FROM company_identifiers WHERE company_entity_id IN ({eq})", entity_ids) if entity_ids else []
    t["intel_documents"] = _all(conn, f"SELECT * FROM intel_documents WHERE company_entity_id IN ({eq})", entity_ids) if entity_ids else []
    doc_ids = [row["id"] for row in t["intel_documents"]]
    diq = ",".join("?" * len(doc_ids)) or "''"
    t["intel_document_spans"] = _all(conn, f"SELECT * FROM intel_document_spans WHERE document_id IN ({diq})", doc_ids) if doc_ids else []
    t["company_events"] = _all(conn, "SELECT * FROM company_events WHERE account_id=?", (account_id,))
    event_ids = [row["id"] for row in t["company_events"]]
    eiq = ",".join("?" * len(event_ids)) or "''"
    t["company_event_evidence"] = _all(conn, f"SELECT * FROM company_event_evidence WHERE event_id IN ({eiq})", event_ids) if event_ids else []
    t["company_link_keywords"] = _all(conn, "SELECT * FROM company_link_keywords WHERE account_id=?", (account_id,))
    t["company_event_links"] = _all(conn, f"SELECT * FROM company_event_links WHERE event_id IN ({eiq})", event_ids) if event_ids else []
    t["hiring_postings"] = _all(conn, "SELECT * FROM hiring_postings WHERE account_id=?", (account_id,))
    t["hiring_observations"] = _all(conn, "SELECT * FROM hiring_observations WHERE account_id=?", (account_id,))
    t["company_convergences"] = _all(conn, "SELECT * FROM company_convergences WHERE account_id=?", (account_id,))
    convergence_ids = [row["id"] for row in t["company_convergences"]]
    coq = ",".join("?" * len(convergence_ids)) or "''"
    t["company_convergence_events"] = _all(conn, f"SELECT * FROM company_convergence_events WHERE convergence_id IN ({coq})", convergence_ids) if convergence_ids else []
    t["signal_episode_company_events"] = []  # populated after signal_episodes below
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
    t["roi_models"] = _all(conn, "SELECT * FROM roi_models WHERE account_id=?", (account_id,))

    # --- 0031: adoption campaigns ---
    t["adoption_campaigns"] = _all(
        conn, "SELECT * FROM adoption_campaigns WHERE account_id=?", (account_id,))
    campaign_ids = [r["id"] for r in t["adoption_campaigns"]]
    cmq = ",".join("?" * len(campaign_ids)) or "''"
    for tbl in ("adoption_campaign_state_history", "adoption_campaign_barriers",
                "adoption_campaign_targets", "adoption_campaign_plan_links",
                "adoption_campaign_checkpoints", "adoption_campaign_retrospectives"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE campaign_id IN ({cmq})",
                      campaign_ids) if campaign_ids else []
    # Intervention verdicts hang off the retrospective, not the campaign. NOTE: neither this table
    # nor `adoption_campaign_retrospectives` carries a column the registry guard's heuristic looks
    # for (they reach an account through `campaign_id`), so the guard cannot catch an omission here
    # — the same shape of gap that silently dropped account-level commitments before D-103.
    retro_ids = [r["id"] for r in t["adoption_campaign_retrospectives"]]
    rq = ",".join("?" * len(retro_ids)) or "''"
    t["adoption_campaign_retrospective_interventions"] = _all(
        conn, f"SELECT * FROM adoption_campaign_retrospective_interventions "
              f"WHERE retrospective_id IN ({rq})", retro_ids) if retro_ids else []
    # Portfolio-wide documents (the team update) have no account_id and belong to no single
    # account, so they stay out of an account bundle by design.
    t["generated_documents"] = _all(
        conn, "SELECT * FROM generated_documents WHERE account_id=?", (account_id,))
    doc_ids = [r["id"] for r in t["generated_documents"]]
    dgq = ",".join("?" * len(doc_ids)) or "''"
    t["generated_document_people"] = _all(
        conn, f"SELECT * FROM generated_document_people WHERE document_id IN ({dgq})", doc_ids
    ) if doc_ids else []

    # --- 0034: account-scoped copilot graph ---------------------------------
    t["copilot_runs"] = _all(
        conn, "SELECT * FROM copilot_runs WHERE scope_type IN ('account','program') AND account_id=?",
        (account_id,))
    run_ids = [r["id"] for r in t["copilot_runs"]]
    crq = ",".join("?" * len(run_ids)) or "''"
    t["copilot_run_sources"] = _all(
        conn, f"SELECT * FROM copilot_run_sources WHERE run_id IN ({crq})", run_ids
    ) if run_ids else []
    t["copilot_claims"] = _all(
        conn, f"SELECT * FROM copilot_claims WHERE run_id IN ({crq})", run_ids
    ) if run_ids else []
    claim_ids = [r["id"] for r in t["copilot_claims"]]
    clq = ",".join("?" * len(claim_ids)) or "''"
    t["copilot_claim_sources"] = _all(
        conn, f"SELECT * FROM copilot_claim_sources WHERE claim_id IN ({clq})", claim_ids
    ) if claim_ids else []
    t["copilot_feedback"] = _all(
        conn, f"SELECT * FROM copilot_feedback WHERE run_id IN ({crq})", run_ids
    ) if run_ids else []
    feedback_ids = [r["id"] for r in t["copilot_feedback"]]
    cfq = ",".join("?" * len(feedback_ids)) or "''"
    t["copilot_feedback_reviews"] = _all(
        conn, f"SELECT * FROM copilot_feedback_reviews WHERE feedback_id IN ({cfq})", feedback_ids
    ) if feedback_ids else []
    t["copilot_entity_aliases"] = _all(
        conn, "SELECT * FROM copilot_entity_aliases WHERE account_id=?", (account_id,))
    config_ids = {r["configuration_id"] for r in t["copilot_runs"]}
    # Preserve the rollback chain as well as the exact configuration each frozen run used.
    pending_config_ids = set(config_ids)
    configs: dict[str, dict] = {}
    while pending_config_ids:
        config_id = pending_config_ids.pop()
        row = conn.execute("SELECT * FROM copilot_configurations WHERE id=?", (config_id,)).fetchone()
        if not row:
            continue
        item = dict(row)
        configs[config_id] = item
        if item.get("previous_config_id") and item["previous_config_id"] not in configs:
            pending_config_ids.add(item["previous_config_id"])
    # The previous version must be inserted before an active version that references it.
    t["copilot_configurations"] = sorted(configs.values(), key=lambda row: row["created_at"])
    style_ids = {r["writing_style_profile_id"] for r in t["generated_documents"]
                 if r.get("writing_style_profile_id")}
    stq = ",".join("?" * len(style_ids)) or "''"
    t["writing_style_profiles"] = _all(
        conn, f"SELECT * FROM writing_style_profiles WHERE id IN ({stq})", tuple(style_ids)
    ) if style_ids else []
    t["document_kinds"] = _all(conn, "SELECT * FROM document_kinds")

    # --- 0026-0028: internal operating layer ---------------------------------
    for tbl in ("account_reviews", "operator_views", "account_status_assessments",
                "account_internal_roster", "renewal_outcome_events"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    t["account_change_checkpoints"] = _all(
        conn, "SELECT * FROM account_change_checkpoints WHERE account_id=?", (account_id,))
    review_ids = [r["id"] for r in t["account_reviews"]]
    rq = ",".join("?" * len(review_ids)) or "''"
    t["account_review_participants"] = _all(conn, f"SELECT * FROM account_review_participants WHERE review_id IN ({rq})", review_ids) if review_ids else []
    t["forecast_entries"] = _all(conn, "SELECT * FROM forecast_entries WHERE account_id=?", (account_id,))
    forecast_ids = [r["id"] for r in t["forecast_entries"]]
    fq = ",".join("?" * len(forecast_ids)) or "''"
    period_ids = {r["period_id"] for r in t["forecast_entries"]}
    fpq = ",".join("?" * len(period_ids)) or "''"
    t["forecast_periods"] = _all(conn, f"SELECT * FROM forecast_periods WHERE id IN ({fpq})", tuple(period_ids)) if period_ids else []
    t["forecast_entry_sources"] = _all(conn, f"SELECT * FROM forecast_entry_sources WHERE entry_id IN ({fq})", forecast_ids) if forecast_ids else []
    t["forecast_change_events"] = _all(conn, f"SELECT * FROM forecast_change_events WHERE entry_id IN ({fq})", forecast_ids) if forecast_ids else []
    t["forecast_opening_snapshots"] = _all(conn, f"SELECT * FROM forecast_opening_snapshots WHERE period_id IN ({fpq})", tuple(period_ids)) if period_ids else []
    snapshot_ids = [r["id"] for r in t["forecast_opening_snapshots"]]
    fsq = ",".join("?" * len(snapshot_ids)) or "''"
    t["forecast_opening_lines"] = _all(conn, f"SELECT * FROM forecast_opening_lines WHERE snapshot_id IN ({fsq}) AND account_id=?", (*snapshot_ids, account_id)) if snapshot_ids else []
    occurrence_rows = _all(conn, "SELECT * FROM product_feedback_occurrences WHERE account_id=?", (account_id,))
    t["product_feedback_occurrences"] = occurrence_rows
    occurrence_ids = [r["id"] for r in occurrence_rows]; oq = ",".join("?" * len(occurrence_ids)) or "''"
    item_ids = {r["feedback_item_id"] for r in occurrence_rows}; fiq = ",".join("?" * len(item_ids)) or "''"
    t["product_feedback_items"] = _all(conn, f"SELECT * FROM product_feedback_items WHERE id IN ({fiq})", tuple(item_ids)) if item_ids else []
    # Themes are portfolio-global but occurrence movement is account-scoped. Export shared
    # theme status events plus only this account's occurrence events, otherwise a valid
    # single-account bundle can contain a dangling occurrence_id from another account.
    t["product_feedback_events"] = _all(
        conn,
        f"SELECT * FROM product_feedback_events WHERE feedback_item_id IN ({fiq}) "
        f"AND (occurrence_id IS NULL OR occurrence_id IN ({oq}))",
        (*item_ids, *occurrence_ids),
    ) if item_ids else []
    t["product_feedback_touches"] = _all(conn, f"SELECT * FROM product_feedback_touches WHERE occurrence_id IN ({oq})", occurrence_ids) if occurrence_ids else []
    t["internal_asks"] = _all(conn, "SELECT * FROM internal_asks WHERE account_id=?", (account_id,))
    ask_ids = [r["id"] for r in t["internal_asks"]]; iaq = ",".join("?" * len(ask_ids)) or "''"
    t["internal_ask_events"] = _all(conn, f"SELECT * FROM internal_ask_events WHERE ask_id IN ({iaq})", ask_ids) if ask_ids else []
    t["internal_ask_documents"] = _all(conn, f"SELECT * FROM internal_ask_documents WHERE ask_id IN ({iaq})", ask_ids) if ask_ids else []
    t["escalation_instances"] = _all(conn, f"SELECT * FROM escalation_instances WHERE ask_id IN ({iaq})", ask_ids) if ask_ids else []
    escalation_ids = [r["id"] for r in t["escalation_instances"]]; esq = ",".join("?" * len(escalation_ids)) or "''"
    t["escalation_events"] = _all(conn, f"SELECT * FROM escalation_events WHERE escalation_id IN ({esq})", escalation_ids) if escalation_ids else []
    t["generated_document_sources"] = _all(conn, f"SELECT * FROM generated_document_sources WHERE document_id IN ({dgq})", doc_ids) if doc_ids else []
    t["forecast_submissions"] = _all(conn, f"SELECT * FROM forecast_submissions WHERE period_id IN ({fpq}) AND document_id IN ({dgq})", (*period_ids, *doc_ids)) if period_ids and doc_ids else []
    submission_ids = [r["id"] for r in t["forecast_submissions"]]; subq = ",".join("?" * len(submission_ids)) or "''"
    t["forecast_submission_lines"] = _all(conn, f"SELECT * FROM forecast_submission_lines WHERE submission_id IN ({subq}) AND account_id=?", (*submission_ids, account_id)) if submission_ids else []
    # Portfolio vocabularies are safe to include because restore skips existing rows.
    for tbl in ("internal_functions", "status_criteria_versions", "escalation_defaults", "report_templates"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl}")

    # --- 0022: Stage 7 --------------------------------------------------------
    t["calendar_events"] = _all(conn, "SELECT * FROM calendar_events WHERE account_id=?", (account_id,))
    event_ids = [r["id"] for r in t["calendar_events"]]
    eq = ",".join("?" * len(event_ids)) or "''"
    t["calendar_event_attendees"] = _all(
        conn, f"SELECT * FROM calendar_event_attendees WHERE event_id IN ({eq})", event_ids
    ) if event_ids else []
    for tbl in ("org_change_flags", "succession_records", "signal_episodes"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))
    signal_ids = [row["id"] for row in t["signal_episodes"]]
    siq = ",".join("?" * len(signal_ids)) or "''"
    t["signal_episode_company_events"] = _all(
        conn, f"SELECT * FROM signal_episode_company_events WHERE signal_episode_id IN ({siq})", signal_ids
    ) if signal_ids else []

    # --- 0023: Stage 7.5 ------------------------------------------------------
    for tbl in ("operational_agreements", "operational_agreement_events",
                "account_growth_plans", "growth_plan_lines", "playbook_entries"):
        t[tbl] = _all(conn, f"SELECT * FROM {tbl} WHERE account_id=?", (account_id,))

    playbook_ids = [r["id"] for r in t["playbook_entries"]]
    pbq = ",".join("?" * len(playbook_ids)) or "''"
    t["playbook_entry_tags"] = _all(
        conn, f"SELECT * FROM playbook_entry_tags WHERE entry_id IN ({pbq})", playbook_ids
    ) if playbook_ids else []
    play_ids = {r["play_definition_id"] for r in t["playbook_entries"] if r.get("play_definition_id")}
    plq = ",".join("?" * len(play_ids)) or "''"
    t["play_definitions"] = _all(
        conn, f"SELECT * FROM play_definitions WHERE id IN ({plq})", tuple(play_ids)
    ) if play_ids else []
    message_ids = {r["messaging_entry_id"] for r in t["playbook_entries"] if r.get("messaging_entry_id")}
    meq = ",".join("?" * len(message_ids)) or "''"
    t["messaging_entries"] = _all(
        conn, f"SELECT * FROM messaging_entries WHERE id IN ({meq})", tuple(message_ids)
    ) if message_ids else []

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
        ("expansion_opportunities", ["sponsor_person_id", "budget_owner_person_id",
                                     "qualification_champion_person_id"]),
        ("relationship_edges", ["from_person_id", "to_person_id"]),
        # 0013-0019 person references, or a restored bundle hits a missing FK.
        ("advocacy_events", ["person_id"]), ("comm_messages", ["person_id"]),
        ("association_hints", ["person_id"]), ("champion_candidates", ["person_id"]),
        ("exec_pairings", ["client_person_id", "valence_person_id"]),
        ("whitespace_cells", ["sponsor_person_id", "blocker_owner_person_id"]),
        ("value_targets", ["accepted_by_person_id"]),
        ("funding_pools", ["owner_person_id"]),
        ("ask_calendar_steps", ["owner_person_id"]),
        ("adoption_campaigns", ["internal_owner_person_id", "client_sponsor_person_id",
                                "lead_champion_person_id"]),
        ("generated_document_people", ["person_id"]),
        ("calendar_event_attendees", ["person_id"]),
        ("org_change_flags", ["person_id"]),
        ("succession_records", ["departed_person_id", "successor_person_id",
                                "successor_placeholder_id"]),
        ("operational_agreements", ["budget_owner_person_id"]),
        ("growth_plan_lines", ["budget_owner_person_id"]),
        ("account_reviews", ["chair_person_id"]),
        ("account_review_participants", ["person_id"]),
        ("account_status_assessments", ["recovery_owner_person_id"]),
        ("account_internal_roster", ["person_id"]),
        ("forecast_entries", ["renewal_budget_owner_person_id"]),
        ("internal_asks", ["requested_by_person_id", "requested_from_person_id", "current_owner_person_id"]),
        ("product_feedback_occurrences", ["stakeholder_person_id"]),
        ("product_feedback_items", ["owner_person_id"]),
        ("escalation_events", ["destination_person_id"]),
        ("company_event_links", ["person_id"]),
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
        "metric_observations", "value_stories", "population_segments", "whitespace_cells",
        "funding_pools",
        "population_headcount_observations", "value_targets", "revenue_events",
        "calendar_events", "org_change_flags", "operational_agreements", "growth_plan_lines",
        "internal_asks", "product_feedback_occurrences", "renewal_outcome_events",
        # Stage 11: a campaign's diagnosis and each barrier cite their evidence, and a bundle
        # missing those references cannot restore the rows that point at them.
        "adoption_campaigns", "adoption_campaign_barriers", "adoption_campaign_checkpoints",
        "intel_documents",
    ) for row in t.get(tbl, []) if row.get("source_reference_id")}
    srcs |= {row["diagnosis_source_reference_id"] for row in t.get("adoption_campaigns", [])
             if row.get("diagnosis_source_reference_id")}
    sq = ",".join("?" * len(srcs)) or "''"
    t["source_references"] = _all(conn, f"SELECT * FROM source_references WHERE id IN ({sq})", tuple(srcs)) if srcs else []

    defs = {row["definition_id"] for row in t["metric_observations"] if row.get("definition_id")}
    defs |= {row["definition_id"] for row in t["value_targets"] if row.get("definition_id")}
    dq = ",".join("?" * len(defs)) or "''"
    t["metric_definitions"] = _all(conn, f"SELECT * FROM metric_definitions WHERE id IN ({dq})", tuple(defs)) if defs else []

    # Portfolio-global vocabularies (§1.2): exported for referenced rows only, so restoring one
    # account into a clean install does not import the whole portfolio's taxonomy.
    # Campaigns name a use case directly and often one no whitespace cell references, so gathering
    # only from cells produced a bundle whose campaign row could not be restored (FK on use_case_id).
    ucs = {row["use_case_id"] for row in t["whitespace_cells"] if row.get("use_case_id")}
    ucs |= {row["use_case_id"] for row in t["adoption_campaigns"] if row.get("use_case_id")}
    ucs |= {row["use_case_id"] for row in t.get("company_event_links", []) if row.get("use_case_id")}
    uq = ",".join("?" * len(ucs)) or "''"
    t["use_cases"] = _all(conn, f"SELECT * FROM use_cases WHERE id IN ({uq})", tuple(ucs)) if ucs else []
    tags = {row["tag_id"] for row in t["population_view_tags"]}
    tags |= {row["tag_id"] for row in t["playbook_entry_tags"]}
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
    post_updates = []
    with conn:
        # Stage 7.5 introduces an intentional cycle: an opportunity can point at its ask
        # calendar while the calendar points back at the opportunity. Defer FK checks until
        # the complete account graph has been restored, then SQLite validates it atomically.
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for tbl in _INSERT_ORDER:
            rows = tables.get(tbl) or []
            for row in rows:
                # Global/shared tables — skip if already present rather than colliding.
                if tbl in ("metric_definitions", "source_references", "audience_tags", "use_cases",
                           "messaging_entries", "play_definitions", "internal_functions",
                           "status_criteria_versions", "escalation_defaults",
                           "report_templates", "document_kinds", "writing_style_profiles",
                           "copilot_configurations", "company_event_kinds", "company_entities",
                           "company_identifiers", "intel_documents", "intel_document_spans") and \
                        conn.execute(f"SELECT 1 FROM {tbl} WHERE id=?", (row["id"],)).fetchone():
                    continue
                row = dict(row)
                if tbl == "copilot_configurations" and row.get("status") == "active":
                    conn.execute(
                        "UPDATE copilot_configurations SET status='retired',updated_at=? "
                        "WHERE status='active' AND id<>?", (now_utc(), row["id"]))
                # Break the opportunity ↔ ask-calendar cycle and links to Stage 5.5 records
                # inserted later. Restore them after the complete graph exists so the scope
                # triggers can validate real targets rather than accepting dangling ids.
                if tbl == "expansion_opportunities":
                    late = {k: row.get(k) for k in (
                        "qualification_value_target_id", "qualification_ask_calendar_id",
                        "funding_pool_id") if row.get(k)}
                    if late:
                        post_updates.append((row["id"], late))
                        for key in late:
                            row[key] = None
                cols = list(row.keys())
                conn.execute(
                    f"INSERT INTO {tbl} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                    tuple(row[c] for c in cols),
                )
            if rows:
                inserted[tbl] = len(rows)
        for opportunity_id, changes in post_updates:
            conn.execute("UPDATE expansion_opportunities SET " +
                         ",".join(f"{k}=?" for k in changes) + " WHERE id=?",
                         (*changes.values(), opportunity_id))
        audit.record(conn, object_type="account", object_id=account_id, action="create",
                     after={"restored_from_export": True, "tables": inserted})
    return {"account_id": account_id, "restored": inserted}
