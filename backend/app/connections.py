"""Connection registry and fail-closed real-data gate (Phase 3 Stage 8).

The application is deliberately useful without any real external connection.  This module is
the runtime counterpart to ``CONNECTIONS.md``: it describes every boundary, reports the active
mode to Operations, and prevents a network-backed mode from being selected accidentally.

A real connection requires both an explicit approval flag and the decision-log reference that
authorized it.  The second value is intentionally not inferred from credentials: possession of
an API key is not data-governance approval.
"""
from __future__ import annotations

import os
from pathlib import Path


REAL_APPROVAL_ENV = "VALENCE_OS_REAL_CONNECTIONS_APPROVED"
REAL_DECISION_ENV = "VALENCE_OS_REAL_CONNECTIONS_DECISION"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


_CONNECTIONS = (
    {
        "id": "recording_source",
        "label": "Recording and transcript intake",
        "current_mode": "local_fixture_or_paste",
        "config_switch": "No runtime switch; /api/ingest/recording accepts a fixture name or pasted text",
        "fixture_glob": "transcripts/*.txt",
        "real_requires": "Approved recording store or upload location, retention policy, deletion path, and service identity",
        "code_owner": "app/adapters.py + app/ingestion.py",
    },
    {
        "id": "transcription_source",
        "label": "Audio transcription",
        "current_mode": "mock_transcript",
        "config_switch": "No real implementation",
        "fixture_glob": "transcripts/*.txt",
        "real_requires": "Approved transcription provider, DPA, region and retention controls, credential storage, and audio deletion contract",
        "code_owner": "app/adapters.py:transcribe",
    },
    {
        "id": "email_provider",
        "label": "Email provider",
        "current_mode": "mock_eml",
        "config_switch": "No real implementation",
        "fixture_glob": "emails/*.eml",
        "real_requires": "Approved Graph/Gmail scope, least-privilege mailbox access, retention rules, webhook or polling design, and secret storage",
        "code_owner": "app/adapters.py:fetch_emails",
    },
    {
        "id": "calendar_provider",
        "label": "Calendar provider",
        "current_mode": "mock_ics_and_local_write",
        "config_switch": "No real implementation",
        "fixture_glob": "calendar/*.ics",
        "real_requires": "Approved read/write calendar scopes, service identity, attendee-data rules, idempotency keys, and rollback behavior",
        "code_owner": "app/adapters.py:fetch_calendar_events + app/stage7.py:write_calendar_event",
    },
    {
        "id": "enrichment_source",
        "label": "Org-change enrichment",
        "current_mode": "mock_json",
        "config_switch": "No real implementation",
        "fixture_glob": "org_changes/*.json",
        "real_requires": "Approved provider and fields, lawful-use review, refresh cadence, provenance, and a deletion/correction path",
        "code_owner": "app/adapters.py:fetch_org_changes",
    },
    {
        "id": "headcount_source",
        "label": "Population headcount source",
        "current_mode": "mock_hris_csv",
        "config_switch": "No real implementation",
        "fixture_glob": "headcount/*.csv",
        "real_requires": "Approved aggregate-only HRIS export, cohort floor, source dating, transfer method, and explicit prohibition on person-level usage data",
        "code_owner": "app/adapters.py:fetch_headcount_observations",
    },
    {
        "id": "metric_source",
        "label": "Data-team metric ingestion",
        "current_mode": "manual_csv_preview_commit",
        "config_switch": "No real implementation; operator uploads CSV through preview/commit",
        "fixture_glob": None,
        "real_requires": "Approved aggregate cohort feed, stable metric and population identifiers, freshness contract, rollback semantics, and cohort-floor enforcement",
        "code_owner": "app/routers/data.py",
    },
    {
        "id": "notification_channel",
        "label": "Notification delivery",
        "current_mode": "in_app_only",
        "config_switch": "No outbound implementation",
        "fixture_glob": None,
        "real_requires": "Approved channel, recipient mapping, least-sensitive payload contract, delivery audit, retries, and unsubscribe or disable control",
        "code_owner": "app/jobs.py + app/routers/ai.py",
    },
    {
        "id": "llm_endpoint",
        "label": "LLM extraction and intake endpoint",
        "current_mode": "dynamic",
        "config_switch": "EXTRACTOR_BACKEND=mock|api; manual paste remains local",
        "fixture_glob": "transcripts/*.txt",
        "real_requires": "Approved model/provider, DPA and region, credential storage, prompt/data retention review, model allow-list, and logged approval decision",
        "code_owner": "app/extractor.py + app/intake.py",
        "real_modes": ("api",),
    },
    {
        "id": "copilot_endpoint",
        "label": "Account Copilot cross-record context endpoint",
        "current_mode": "dynamic_copilot",
        "config_switch": "COPILOT_BACKEND=mock only; real modes have no implementation",
        "fixture_glob": "copilot/*.json",
        "real_requires": "Separate approval for cross-record copilot payload classes, maximum context, provider/model allow-list, processing region, retention/training terms, redacted logging, credential ownership, and rollback decision",
        "code_owner": "app/copilot_model.py + app/copilot_service.py",
        "real_modes": ("api",),
    },
    {
        "id": "company_intel_source",
        "label": "Public company artifact source",
        "current_mode": "mock_json",
        "config_switch": "COMPANY_INTEL_BACKEND=mock only; real modes have no implementation",
        "fixture_glob": "company_intel/*.json",
        "real_requires": "Approved provider terms and content license, API/robots compliance, source allow-list, provenance, retention, correction/takedown, credentials, logging, and rollback",
        "code_owner": "app/adapters.py:fetch_company_intel + app/company_intel.py",
        "real_modes": ("api",),
    },
    {
        "id": "intel_extraction_endpoint",
        "label": "Public artifact to company event extraction",
        "current_mode": "fixture_payload_only",
        "config_switch": "No extraction implementation; fixtures carry proposed events",
        "fixture_glob": "company_intel/*.json",
        "real_requires": "Separate approved model/provider, exact payload field allow-list, licensing review, region and retention, prompt-injection controls, evaluation set, credentials, logging, and rollback",
        "code_owner": "app/company_intel.py (fixture proposals only)",
        "real_modes": ("api",),
    },
    {
        "id": "file_storage",
        "label": "File and generated-artifact storage",
        "current_mode": "local_links_sqlite_and_memory",
        "config_switch": "No real implementation",
        "fixture_glob": None,
        "real_requires": "Approved encrypted object store, tenant/account boundaries, signed-link policy, retention, deletion, backup, and restore test",
        "code_owner": "app/generators.py + app/decks.py + source_references",
    },
    {
        "id": "hosting",
        "label": "Application hosting and database",
        "current_mode": "local_fastapi_sqlite",
        "config_switch": "VALENCE_OS_DB selects a local SQLite path; VALENCE_OS_WORKER enables the in-process worker",
        "fixture_glob": None,
        "real_requires": "Valence-approved hosting, SSO/MFA, encryption, managed secrets, network controls, logging, backups, restore drill, and incident ownership",
        "code_owner": "app/main.py + app/db.py + app/jobs.py",
    },
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "approved"}


def approval_state() -> dict:
    decision = os.environ.get(REAL_DECISION_ENV, "").strip()
    return {
        "approved": _truthy(os.environ.get(REAL_APPROVAL_ENV)) and bool(decision),
        "decision_reference": decision or None,
        "approval_env": REAL_APPROVAL_ENV,
        "decision_env": REAL_DECISION_ENV,
    }


def require_real_connection(connection_id: str, mode: str) -> None:
    """Reject a network-backed mode unless the governance approval is explicit.

    This is a configuration guard, not a substitute for provider-specific security review.  A
    caller still has to implement and validate the real adapter named in CONNECTIONS.md.
    """
    definition = next((row for row in _CONNECTIONS if row["id"] == connection_id), None)
    if definition is None:
        raise RuntimeError(f"unknown connection boundary '{connection_id}'")
    if mode not in definition.get("real_modes", ()):
        return
    state = approval_state()
    if not state["approved"]:
        raise RuntimeError(
            f"Real connection '{connection_id}' mode '{mode}' is blocked by the Stage 8 data-governance gate. "
            f"Record approval in decisions.md, then set {REAL_APPROVAL_ENV}=1 and "
            f"{REAL_DECISION_ENV}=<decision reference>."
        )


def registry_snapshot() -> dict:
    """Return the complete registry for Operations without exposing credentials."""
    state = approval_state()
    rows = []
    for definition in _CONNECTIONS:
        row = dict(definition)
        real_modes = tuple(row.pop("real_modes", ()))
        if row["current_mode"] == "dynamic":
            mode = os.environ.get("EXTRACTOR_BACKEND", "mock").strip().lower()
        elif row["current_mode"] == "dynamic_copilot":
            mode = os.environ.get("COPILOT_BACKEND", "mock").strip().lower()
        else:
            mode = row["current_mode"]
        fixture_glob = row.pop("fixture_glob")
        fixtures = sorted(str(path.relative_to(FIXTURES)) for path in FIXTURES.glob(fixture_glob)) \
            if fixture_glob else []
        selected_real = mode in real_modes
        rows.append({
            **row,
            "current_mode": mode,
            "fixtures": fixtures,
            "real_capable": bool(real_modes),
            "gate_status": "approved" if selected_real and state["approved"] else
                           "blocked" if selected_real else "local",
        })
    return {"policy": "build everything, connect nothing real", "approval": state,
            "connections": rows}
