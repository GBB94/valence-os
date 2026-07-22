import sqlite3

from fastapi import APIRouter, Depends

from .. import execution_ops as ops
from .. import repo
from ..deps import get_conn
from ..schemas import (
    CommitmentClose, CommitmentCreate, DecisionCreate, IssueCreate, IssueResolve,
    MilestoneComplete, MilestoneCreate, RiskClose, RiskCreate, TaskClose, TaskCreate,
)

router = APIRouter(prefix="/api", tags=["execution"])


# --- create ---
@router.post("/tasks", status_code=201)
def create_task(b: TaskCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.create(conn, "task", b.model_dump())


@router.post("/commitments", status_code=201)
def create_commitment(b: CommitmentCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.create(conn, "commitment", b.model_dump())


@router.post("/decisions", status_code=201)
def create_decision(b: DecisionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.create(conn, "decision", b.model_dump())


@router.post("/risks", status_code=201)
def create_risk(b: RiskCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.create(conn, "risk", b.model_dump())


@router.post("/issues", status_code=201)
def create_issue(b: IssueCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.create(conn, "issue", b.model_dump())


@router.post("/milestones", status_code=201)
def create_milestone(b: MilestoneCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.create(conn, "milestone", b.model_dump())


# --- transitions (closure rules) ---
@router.post("/commitments/{id}/close")
def close_commitment(id: str, b: CommitmentClose, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.close_commitment(conn, id, **b.model_dump())


@router.post("/tasks/{id}/close")
def close_task(id: str, b: TaskClose, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.close_task(conn, id, **b.model_dump())


@router.post("/risks/{id}/close")
def close_risk(id: str, b: RiskClose, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.close_risk(conn, id, **b.model_dump())


@router.post("/issues/{id}/resolve")
def resolve_issue(id: str, b: IssueResolve, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.resolve_issue(conn, id, **b.model_dump())


@router.post("/milestones/{id}/complete")
def complete_milestone(id: str, b: MilestoneComplete, conn: sqlite3.Connection = Depends(get_conn)):
    return ops.complete_milestone(conn, id, **b.model_dump())


# --- board views ---
@router.get("/programs/{program_id}/execution")
def program_execution(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "programs", program_id)
    return ops.program_execution(conn, program_id)


@router.get("/accounts/{account_id}/execution")
def account_execution(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """Aggregate execution across the account's programs, with names resolved for display."""
    repo.get_row(conn, "accounts", account_id)
    programs = {p["id"]: p for p in repo.list_rows(conn, "programs", where="account_id = ?", params=(account_id,))}
    people = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    merged = {t: [] for t in ("tasks", "commitments", "decisions", "risks", "issues", "milestones")}
    for pid, prog in programs.items():
        for table, rows in ops.program_execution(conn, pid).items():
            for r in rows:
                r["program_name"] = prog["name"]
                for fk, label in (("internal_owner_id", "internal_owner_name"),
                                  ("responsible_party_id", "responsible_party_name")):
                    if r.get(fk):
                        r[label] = people.get(r[fk])
                merged[table].append(r)
    return merged
