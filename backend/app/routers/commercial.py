import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, repo
from ..db import now_utc
from ..deps import get_conn
from ..schemas import (
    ContractCreate, ContractOverlay, ExpansionClose, ExpansionCreate, ExpansionPatch,
)

router = APIRouter(prefix="/api", tags=["commercial"])


# --- Expansion opportunities ---
@router.post("/expansions", status_code=201)
def create_expansion(b: ExpansionCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", b.account_id)
    return repo.insert(conn, "expansion_opportunities", b.model_dump(), object_type="expansion_opportunity")


@router.get("/accounts/{account_id}/expansions")
def list_expansions(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    rows = repo.list_rows(conn, "expansion_opportunities",
                          where="account_id = ? ORDER BY status, created_at DESC", params=(account_id,))
    names = {p["id"]: p["name"] for p in repo.list_rows(conn, "persons", where="1=1")}
    for r in rows:
        r["sponsor_name"] = names.get(r["sponsor_person_id"])
        r["budget_owner_name"] = names.get(r["budget_owner_person_id"])
    return rows


@router.patch("/expansions/{expansion_id}")
def patch_expansion(expansion_id: str, b: ExpansionPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "expansion_opportunities", expansion_id, b.model_dump(),
                      object_type="expansion_opportunity")


@router.post("/expansions/{expansion_id}/close")
def close_expansion(expansion_id: str, b: ExpansionClose, conn: sqlite3.Connection = Depends(get_conn)):
    """Closing requires an outcome (won/lost/deferred/merged/no_decision) and a reason."""
    before = repo.get_row(conn, "expansion_opportunities", expansion_id)
    if before["status"] == "closed":
        raise HTTPException(409, "expansion is already closed")
    with conn:
        conn.execute(
            "UPDATE expansion_opportunities SET status='closed', outcome=?, outcome_reason=?, updated_at=? WHERE id=?",
            (b.outcome, b.outcome_reason, now_utc(), expansion_id),
        )
        after = repo.get_row(conn, "expansion_opportunities", expansion_id)
        audit.record(conn, object_type="expansion_opportunity", object_id=expansion_id,
                     action="close", before=before, after=after)
    return after


# --- Contract versions (canonical synced copy; never overwritten) ---
@router.post("/contracts", status_code=201)
def create_contract(b: ContractCreate, conn: sqlite3.Connection = Depends(get_conn)):
    repo.get_row(conn, "accounts", b.account_id)
    values = b.model_dump()
    supersedes = values.get("supersedes_id")
    row = repo.insert(conn, "contract_versions", values, object_type="contract_version")
    if supersedes:
        old = repo.get_row(conn, "contract_versions", supersedes)
        with conn:
            conn.execute("UPDATE contract_versions SET is_current=0, updated_at=? WHERE id=?",
                         (now_utc(), supersedes))
            after = repo.get_row(conn, "contract_versions", supersedes)
            audit.record(conn, object_type="contract_version", object_id=supersedes,
                         action="update", before=old, after=after)
    return row


@router.get("/accounts/{account_id}/contracts")
def list_contracts(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "contract_versions",
                          where="account_id = ? ORDER BY is_current DESC, created_at DESC",
                          params=(account_id,))


@router.post("/contracts/{contract_id}/overlay")
def set_overlay(contract_id: str, b: ContractOverlay, conn: sqlite3.Connection = Depends(get_conn)):
    """Store an operational overlay on renewal timing WITHOUT overwriting the canonical date."""
    before = repo.get_row(conn, "contract_versions", contract_id)
    with conn:
        conn.execute(
            "UPDATE contract_versions SET overlay_expected_decision_date=?, overlay_rationale=?, "
            "overlay_author=?, overlay_assessed_on=?, updated_at=? WHERE id=?",
            (b.overlay_expected_decision_date, b.overlay_rationale, audit.DEFAULT_ACTOR,
             now_utc()[:10], now_utc(), contract_id),
        )
        after = repo.get_row(conn, "contract_versions", contract_id)
        audit.record(conn, object_type="contract_version", object_id=contract_id,
                     action="update", before=before, after=after)
    return after
