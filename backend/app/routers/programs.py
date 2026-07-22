import sqlite3

from fastapi import APIRouter, Depends

from .. import execution_ops, repo
from ..deps import get_conn
from ..schemas import ProgramCreate, ProgramPatch, StakeholderRoleCreate

router = APIRouter(prefix="/api", tags=["programs"])


@router.post("/programs", status_code=201)
def create_program(body: ProgramCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", body.account_id)  # 404 if account missing
    return repo.insert(conn, "programs", body.model_dump(), object_type="program")


@router.get("/programs/{program_id}")
def get_program(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    program = repo.get_row(conn, "programs", program_id)
    program["stakeholders"] = _stakeholders_for(conn, program_id)
    program["interactions"] = repo.list_rows(
        conn, "interactions", where="program_id = ? ORDER BY occurred_on DESC", params=(program_id,)
    )
    program["execution"] = execution_ops.program_execution(conn, program_id)
    return program


@router.patch("/programs/{program_id}")
def patch_program(program_id: str, body: ProgramPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "programs", program_id, body.model_dump(), object_type="program")


@router.post("/programs/{program_id}/archive", status_code=204)
def archive_program(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.archive(conn, "programs", program_id, object_type="program")


# --- Stakeholder roles (Person x Program) live under programs in v0.1 ---

@router.get("/programs/{program_id}/stakeholders")
def list_stakeholders(program_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return _stakeholders_for(conn, program_id)


@router.post("/stakeholder-roles", status_code=201)
def create_stakeholder_role(body: StakeholderRoleCreate, conn: sqlite3.Connection = Depends(get_conn)):
    # Trust-boundary echo of the DB CHECK: a stance requires date + evidence.
    if body.stance and not (body.stance_assessed_on and body.stance_evidence_note):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail="A stance requires stance_assessed_on and stance_evidence_note (Section 2).",
        )
    return repo.insert(conn, "stakeholder_roles", body.model_dump(), object_type="stakeholder_role")


def _stakeholders_for(conn: sqlite3.Connection, program_id: str) -> list[dict]:
    rows = repo.list_rows(
        conn, "stakeholder_roles", where="program_id = ?", params=(program_id,)
    )
    people = {p["id"]: p for p in repo.list_rows(conn, "persons", where="1=1")}
    for r in rows:
        person = people.get(r["person_id"])
        r["person_name"] = person["name"] if person else None
        r["person_title"] = person["title"] if person else None
    return rows
