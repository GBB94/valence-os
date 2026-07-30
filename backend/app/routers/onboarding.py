"""Onboarding, launch checklists, and org-chart placeholders (PHASE-3-SPEC.md §§1-3)."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import audit, intake, onboarding, repo
from ..db import now_utc
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["onboarding"])


# --- §1 onboarding ----------------------------------------------------------

class OnboardReq(BaseModel):
    kickoff_date: str
    program_id: str | None = None
    program_name: str | None = None
    region: str | None = None
    europe_in_scope: bool = False


@router.post("/accounts/{account_id}/onboard", status_code=201)
def onboard(account_id: str, body: OnboardReq, conn: sqlite3.Connection = Depends(get_conn)):
    return onboarding.seed_onboarding(
        conn, account_id, kickoff_date=body.kickoff_date, program_id=body.program_id,
        program_name=body.program_name, region=body.region, europe_in_scope=body.europe_in_scope,
    )


@router.get("/accounts/{account_id}/onboarding")
def get_onboarding(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return onboarding.onboarding_state(conn, account_id)


@router.get("/accounts/{account_id}/deck-skeleton")
def deck_skeleton(account_id: str, program_id: str | None = None,
                  conn: sqlite3.Connection = Depends(get_conn)):
    return {"markdown": onboarding.deck_skeleton(conn, account_id, program_id)}


# --- §1a intake parse -------------------------------------------------------

class IntakeParseReq(BaseModel):
    text: str


class IntakeAcceptReq(BaseModel):
    account_id: str
    program_id: str | None = None
    proposal: dict


@router.post("/intake/parse")
def intake_parse(body: IntakeParseReq):
    return {"proposals": intake.parse_intake(body.text)}


@router.post("/intake/accept", status_code=201)
def intake_accept(body: IntakeAcceptReq, conn: sqlite3.Connection = Depends(get_conn)):
    return intake.accept_proposal(conn, body.account_id, body.proposal, body.program_id)


# --- §2/§1e checklist items -------------------------------------------------

class NewChecklistItem(BaseModel):
    account_id: str
    program_id: str | None = None
    section: str
    label: str
    detail: str | None = None
    due_date: str | None = None


class PatchChecklistItem(BaseModel):
    status: str | None = None
    answer_note: str | None = None
    due_date: str | None = None
    fill_value: str | None = None  # when set + item has fills_field, patch that target field


@router.get("/checklist-items")
def list_checklist(account_id: str, program_id: str | None = None,
                   section: str | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    where, params = ["account_id = ?"], [account_id]
    if program_id:
        where.append("program_id = ?"); params.append(program_id)
    if section:
        where.append("section = ?"); params.append(section)
    return {"items": repo.list_rows(conn, "checklist_items",
                                    where=" AND ".join(where), params=tuple(params))}


@router.post("/checklist-items", status_code=201)
def add_checklist(body: NewChecklistItem, conn: sqlite3.Connection = Depends(get_conn)):
    if body.section not in ("first_call", "first_two_weeks", "first_30_days", "first_90_days"):
        raise HTTPException(422, f"invalid section: {body.section}")
    return repo.insert(conn, "checklist_items", {
        "account_id": body.account_id, "program_id": body.program_id,
        "section": body.section, "label": body.label, "detail": body.detail,
        "due_date": body.due_date,
    }, object_type="checklist_item")


@router.patch("/checklist-items/{item_id}")
def patch_checklist(item_id: str, body: PatchChecklistItem,
                    conn: sqlite3.Connection = Depends(get_conn)):
    item = repo.get_row(conn, "checklist_items", item_id)
    changes: dict = {}
    if body.status is not None:
        if body.status not in ("open", "done", "na"):
            raise HTTPException(422, f"invalid status: {body.status}")
        changes["status"] = body.status
        changes["done_on"] = now_utc()[:10] if body.status == "done" else None
    if body.answer_note is not None:
        changes["answer_note"] = body.answer_note
    if body.due_date is not None:
        changes["due_date"] = body.due_date
    updated = repo.patch(conn, "checklist_items", item_id,
                         {k: v for k, v in changes.items() if v is not None},
                         object_type="checklist_item")

    # §1e — answering a first-call question can fill the account/program field it points at.
    filled = None
    if body.fill_value and item.get("fills_field"):
        target, _, field = item["fills_field"].partition(".")
        if target == "account":
            repo.patch(conn, "accounts", item["account_id"], {field: body.fill_value},
                       object_type="account")
            filled = item["fills_field"]
        elif target == "program" and item.get("program_id"):
            repo.patch(conn, "programs", item["program_id"], {field: body.fill_value},
                       object_type="program")
            filled = item["fills_field"]
    return {"item": updated, "filled_field": filled}


# --- §3 org-chart placeholders ---------------------------------------------

class NewPlaceholder(BaseModel):
    account_id: str
    program_id: str | None = None
    title: str
    expected_role: str = "other"
    why: str | None = None
    expected_influence: str | None = None
    find_by_date: str | None = None


class ConvertPlaceholder(BaseModel):
    name: str
    title: str | None = None
    email: str | None = None


@router.post("/placeholders", status_code=201)
def create_placeholder(body: NewPlaceholder, conn: sqlite3.Connection = Depends(get_conn)):
    if body.expected_influence and body.expected_influence not in ("low", "medium", "high"):
        raise HTTPException(422, "expected_influence must be low|medium|high")
    person = repo.insert(conn, "persons", {
        "name": f"{body.title} (unknown)", "affiliation": "client",
        "account_id": body.account_id, "title": body.title, "is_placeholder": 1,
        "placeholder_why": body.why, "find_by_date": body.find_by_date,
        "expected_influence": body.expected_influence, "expected_role": body.expected_role,
    }, object_type="person")
    if body.program_id:
        repo.insert(conn, "stakeholder_roles",
                    {"program_id": body.program_id, "person_id": person["id"],
                     "role": body.expected_role},
                    object_type="stakeholder_role")
    return person


@router.post("/placeholders/{person_id}/convert")
def convert_placeholder(person_id: str, body: ConvertPlaceholder,
                        conn: sqlite3.Connection = Depends(get_conn)):
    """Identify a placeholder as a real person. Same id -> edges and roles are preserved."""
    before = repo.get_row(conn, "persons", person_id)
    if not before.get("is_placeholder"):
        raise HTTPException(409, "person is not a placeholder")
    ts = now_utc()
    with conn:
        conn.execute(
            "UPDATE persons SET name=?, title=?, email=?, is_placeholder=0, "
            "placeholder_why=NULL, find_by_date=NULL, expected_influence=NULL, "
            "expected_role=NULL, updated_at=? WHERE id=?",
            (body.name, body.title or before.get("title"), body.email, ts, person_id),
        )
        after = repo.get_row(conn, "persons", person_id)
        audit.record(conn, object_type="person", object_id=person_id,
                     action="convert", before=before, after=after)
    return after
