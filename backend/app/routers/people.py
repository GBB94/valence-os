import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import people_core, repo
from ..deps import get_conn
from ..schemas import (
    AdvocacyEventCreate, PersonCreate, PersonPatch, SourceReferenceCreate,
    SourceReferencePatch, StakeholderRolePatch,
)

router = APIRouter(prefix="/api", tags=["people"])


# --- §3.1/§3.2 taxonomy metadata (drives the frontend selects + layer-lane view) ---
@router.get("/people/taxonomy")
def taxonomy():
    return {
        "roles": people_core.ROLES,
        "layers": people_core.LAYERS,
        "layer_labels": people_core.LAYER_LABELS,
        "default_layer_by_role": people_core.DEFAULT_LAYER_BY_ROLE,
    }


# --- §3.10 person profile card ---
@router.get("/persons/{person_id}/card")
def person_card(person_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    card = people_core.person_card(conn, person_id)
    if not card:
        raise HTTPException(404, f"person not found: {person_id}")
    return card


# --- §3.1/§3.2 edit a stakeholder role (role, layer, stance) ---
@router.patch("/stakeholder-roles/{role_id}")
def patch_stakeholder_role(role_id: str, body: StakeholderRolePatch,
                           conn: sqlite3.Connection = Depends(get_conn)):
    if body.stance is not None and not (body.stance_assessed_on and body.stance_evidence_note):
        raise HTTPException(422, "Setting a stance requires an assessed-on date and an evidence note.")
    return repo.patch(conn, "stakeholder_roles", role_id, body.model_dump(),
                      object_type="stakeholder_role")


# --- §3.2 advocacy evidence (the coach-vs-champion gate; reused by the champion pipeline) ---
@router.post("/advocacy-events", status_code=201)
def create_advocacy_event(body: AdvocacyEventCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "advocacy_events", body.model_dump(), object_type="advocacy_event")


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


@router.patch("/source-references/{ref_id}")
def patch_source_reference(ref_id: str, body: SourceReferencePatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "source_references", ref_id, body.model_dump(), object_type="source_reference")
