import sqlite3

from fastapi import APIRouter, Depends

from .. import repo
from ..deps import get_conn
from ..schemas import AccountCreate, AccountPatch

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("")
def list_accounts(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "accounts", where="1=1 ORDER BY name")


@router.post("", status_code=201)
def create_account(body: AccountCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.insert(conn, "accounts", body.model_dump(), object_type="account")


@router.get("/{account_id}")
def get_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    account = repo.get_row(conn, "accounts", account_id)
    account["programs"] = repo.list_rows(
        conn, "programs", where="account_id = ? ORDER BY name", params=(account_id,)
    )
    account["people"] = repo.list_rows(
        conn, "persons", where="account_id = ? ORDER BY name", params=(account_id,)
    )
    account["interactions"] = repo.list_rows(
        conn, "interactions", where="account_id = ? ORDER BY occurred_on DESC", params=(account_id,)
    )
    return account


@router.patch("/{account_id}")
def patch_account(account_id: str, body: AccountPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "accounts", account_id, body.model_dump(), object_type="account")


@router.post("/{account_id}/archive", status_code=204)
def archive_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.archive(conn, "accounts", account_id, object_type="account")
