"""Thin HTTP boundary for the read-only Stage 12 Account Copilot."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from .. import copilot_evaluation, copilot_service
from ..deps import get_conn
from ..schemas import (CopilotConfigurationCreate, CopilotConfigurationEvaluation,
                       CopilotDraftCreate, CopilotEntityAliasCreate,
                       CopilotFeedbackCreate, CopilotFeedbackReviewCreate,
                       CopilotReplayCreate, CopilotRunCreate,
                       WritingStyleProfileCreate)

router = APIRouter(prefix="/api", tags=["copilot"])


@router.post("/copilot/runs", status_code=202)
def create_run(body: CopilotRunCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.create_run(conn, body.model_dump())


@router.get("/copilot/runs")
def list_runs(scope_type: str | None = None, account_id: str | None = None,
              program_id: str | None = None, limit: int = 50,
              conn: sqlite3.Connection = Depends(get_conn)):
    return {"runs": copilot_service.list_runs(
        conn, scope_type=scope_type, account_id=account_id, program_id=program_id, limit=limit)}


@router.get("/copilot/runs/{run_id}")
def get_run(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.detail(conn, run_id)


@router.delete("/copilot/runs/{run_id}", status_code=204)
def archive_run(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    copilot_service.archive_run(conn, run_id)


@router.post("/copilot/runs/{run_id}/feedback", status_code=201)
def feedback(run_id: str, body: CopilotFeedbackCreate,
             conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.add_feedback(conn, run_id, body.model_dump())


@router.post("/copilot/runs/{run_id}/mark-reviewed")
def mark_reviewed(run_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.mark_reviewed(conn, run_id)


@router.post("/copilot/runs/{run_id}/draft", status_code=201)
def draft(run_id: str, body: CopilotDraftCreate,
          conn: sqlite3.Connection = Depends(get_conn)):
    # No audience parameter exists. This endpoint can create one internal kind only.
    return copilot_service.draft_internal_note(conn, run_id, body.title)


@router.post("/copilot/runs/{run_id}/draft-preview")
def draft_preview(run_id: str, body: CopilotDraftCreate,
                  conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.preview_internal_note(conn, run_id, body.title)


@router.get("/copilot/configurations")
def configurations(conn: sqlite3.Connection = Depends(get_conn)):
    return {"configurations": copilot_service.list_configurations(conn)}


@router.post("/copilot/configurations", status_code=201)
def create_configuration(body: CopilotConfigurationCreate,
                         conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.create_configuration(conn, body.model_dump())


@router.post("/copilot/configurations/{configuration_id}/replay", status_code=202)
def replay_configuration(configuration_id: str, body: CopilotReplayCreate,
                         conn: sqlite3.Connection = Depends(get_conn)):
    return {"runs": copilot_service.replay_configuration(conn, configuration_id, body.run_ids)}


@router.post("/copilot/configurations/{configuration_id}/evaluate")
def evaluate_configuration(configuration_id: str, body: CopilotConfigurationEvaluation,
                           conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.evaluate_configuration(conn, configuration_id, body.run_ids_by_case)


@router.post("/copilot/configurations/{configuration_id}/activate")
def activate_configuration(configuration_id: str,
                           conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.activate_configuration(conn, configuration_id)


@router.post("/copilot/configurations/{configuration_id}/rollback")
def rollback_configuration(configuration_id: str,
                           conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.rollback_configuration(conn, configuration_id)


@router.get("/copilot/feedback")
def list_feedback(pending_only: bool = False,
                  conn: sqlite3.Connection = Depends(get_conn)):
    return {"feedback": copilot_service.list_feedback(conn, pending_only=pending_only)}


@router.post("/copilot/feedback/{feedback_id}/review", status_code=201)
def review_feedback(feedback_id: str, body: CopilotFeedbackReviewCreate,
                    conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.review_feedback(conn, feedback_id, body.model_dump())


@router.get("/copilot/entity-aliases")
def aliases(account_id: str | None = None,
            conn: sqlite3.Connection = Depends(get_conn)):
    return {"aliases": copilot_service.list_aliases(conn, account_id)}


@router.post("/copilot/entity-aliases", status_code=201)
def create_alias(body: CopilotEntityAliasCreate,
                 conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.create_alias(conn, body.model_dump())


@router.get("/copilot/styles")
def styles(conn: sqlite3.Connection = Depends(get_conn)):
    return {"profiles": copilot_service.list_styles(conn)}


@router.post("/copilot/styles", status_code=201)
def create_style(body: WritingStyleProfileCreate,
                 conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.create_style(conn, body.model_dump())


@router.get("/copilot/health")
def health(conn: sqlite3.Connection = Depends(get_conn)):
    return copilot_service.health(conn)


@router.get("/copilot/evaluation")
def evaluation_manifest():
    """Expose the fixture/version used by CI without exposing customer-shaped run content."""
    return copilot_evaluation.manifest()
