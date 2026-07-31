"""Relationship-intelligence API (Comprehensive Spec Stage 5).

  §3.4 champion pipeline · §3.5 influence paths · §3.8 exec alignment ·
  §3.12 messaging library · §3.13 meeting dynamics · §4.4 pull signals.

Trust boundaries unchanged: professional observations only; the champion pipeline's advocacy
stages are evidence-gated exactly like the coach-vs-champion rule (§3.2)."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import people_analytics, people_core, repo
from ..deps import get_conn
from ..schemas import (
    ChampionCandidateCreate, ChampionCandidatePatch, ExecPairingCreate, ExecPairingPatch,
    MessagingEntryCreate, MessagingEntryPatch, PullSignalCreate,
)

router = APIRouter(prefix="/api", tags=["relationships"])


# --- §3.4 champion development pipeline --------------------------------------

def _guard_stage(conn, person_id: str, stage: str | None):
    """validate/arm/maintain assert real advocacy — require the same evidence as a champion tag."""
    if stage and people_analytics.stage_requires_evidence(stage) and not people_core.has_champion_evidence(conn, person_id):
        raise HTTPException(
            422, f"Stage '{stage}' needs a logged advocacy-without-us event first — "
                 "log a validation event, or keep them at develop/identify.")


@router.post("/champion-candidates", status_code=201)
def create_champion(body: ChampionCandidateCreate, conn: sqlite3.Connection = Depends(get_conn)):
    person = repo.get_row(conn, "persons", body.person_id)
    if not person.get("account_id"):
        raise HTTPException(422, "champions are client stakeholders with an account")
    _guard_stage(conn, body.person_id, body.stage)
    data = body.model_dump()
    data["account_id"] = person["account_id"]
    return repo.insert(conn, "champion_candidates", data, object_type="champion_candidate")


@router.patch("/champion-candidates/{cand_id}")
def patch_champion(cand_id: str, body: ChampionCandidatePatch, conn: sqlite3.Connection = Depends(get_conn)):
    cand = repo.get_row(conn, "champion_candidates", cand_id)
    _guard_stage(conn, cand["person_id"], body.stage)
    return repo.patch(conn, "champion_candidates", cand_id, body.model_dump(), object_type="champion_candidate")


@router.get("/accounts/{account_id}/champion-pipeline")
def champion_pipeline(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return people_analytics.champion_pipeline(conn, account_id)


# --- §3.5 influence paths ---------------------------------------------------

@router.get("/accounts/{account_id}/influence-paths")
def influence_paths(account_id: str, target: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return people_analytics.influence_paths(conn, account_id, target)


# --- §3.8 executive alignment map -------------------------------------------

@router.post("/exec-pairings", status_code=201)
def create_pairing(body: ExecPairingCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "exec_pairings", body.model_dump(), object_type="exec_pairing")


@router.patch("/exec-pairings/{pairing_id}")
def patch_pairing(pairing_id: str, body: ExecPairingPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "exec_pairings", pairing_id, body.model_dump(), object_type="exec_pairing")


@router.get("/accounts/{account_id}/exec-alignment")
def exec_alignment(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", account_id)
    return people_analytics.exec_alignment(conn, account_id)


# --- §3.12 role-based messaging library -------------------------------------

@router.get("/messaging-library")
def list_messaging(layer: str | None = None, role: str | None = None,
                   conn: sqlite3.Connection = Depends(get_conn)):
    where, params = "1=1", []
    if layer:
        where += " AND layer = ?"; params.append(layer)
    if role:
        where += " AND role = ?"; params.append(role)
    where += " ORDER BY layer, role"
    return {"entries": repo.list_rows(conn, "messaging_entries", where=where, params=tuple(params))}


@router.post("/messaging-library", status_code=201)
def create_messaging(body: MessagingEntryCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "messaging_entries", body.model_dump(), object_type="messaging_entry")


@router.patch("/messaging-library/{entry_id}")
def patch_messaging(entry_id: str, body: MessagingEntryPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "messaging_entries", entry_id, body.model_dump(), object_type="messaging_entry")


# --- §3.13 meeting dynamics -------------------------------------------------

@router.get("/programs/{program_id}/meeting-dynamics")
def meeting_dynamics(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", program_id)
    return people_analytics.meeting_dynamics(conn, program_id)


# --- §4.4 pull signals ------------------------------------------------------

@router.get("/accounts/{account_id}/pull-signals")
def list_pull_signals(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return {"signals": repo.list_rows(conn, "pull_signals",
                                      where="account_id = ? ORDER BY created_at DESC", params=(account_id,))}


@router.post("/pull-signals", status_code=201)
def create_pull_signal(body: PullSignalCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "pull_signals", body.model_dump(), object_type="pull_signal")
