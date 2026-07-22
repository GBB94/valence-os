import sqlite3

from fastapi import APIRouter, Depends

from .. import repo
from ..deps import get_conn
from ..schemas import PersonCreate, PersonPatch, SourceReferenceCreate

router = APIRouter(prefix="/api", tags=["people"])


@router.get("/persons")
def list_persons(
    account_id: str | None = None,
    include_valence: bool = True,
    conn: sqlite3.Connection = Depends(get_conn),
):
    if account_id and include_valence:
        return repo.list_rows(
            conn, "persons",
            where="(account_id = ? OR affiliation = 'valence') ORDER BY affiliation, name",
            params=(account_id,),
        )
    if account_id:
        return repo.list_rows(
            conn, "persons", where="account_id = ? ORDER BY name", params=(account_id,)
        )
    return repo.list_rows(conn, "persons", where="1=1 ORDER BY affiliation, name")


@router.post("/persons", status_code=201)
def create_person(body: PersonCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "persons", body.model_dump(), object_type="person")


@router.patch("/persons/{person_id}")
def patch_person(person_id: str, body: PersonPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "persons", person_id, body.model_dump(), object_type="person")


# Source references (link-first) — used by interactions in v0.1.
@router.get("/source-references")
def list_source_references(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "source_references", where="1=1 ORDER BY created_at DESC")


@router.post("/source-references", status_code=201)
def create_source_reference(body: SourceReferenceCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "source_references", body.model_dump(), object_type="source_reference")
