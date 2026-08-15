"""HTTP boundary for internal asks and factual escalation chains."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import internal_asks as service
from .. import repo
from ..db import now_utc
from ..deps import get_conn
from ..schemas import (EscalationCreate, EscalationDefaultPatch, EscalationEventCreate,
                       InternalAskCreate, InternalAskStatus, InternalSettingsPatch)

router = APIRouter(prefix="/api", tags=["internal-asks"])


@router.get("/internal-functions")
def functions(conn: sqlite3.Connection = Depends(get_conn)):
    return [repo.row_to_dict(r) for r in conn.execute("SELECT * FROM internal_functions WHERE active=1 ORDER BY name")]


@router.get("/escalation-defaults")
def defaults(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.list_rows(conn, "escalation_defaults", where="1=1 ORDER BY ask_type,severity")


@router.patch("/escalation-defaults/{default_id}")
def patch_default(default_id: str, body: EscalationDefaultPatch, conn: sqlite3.Connection = Depends(get_conn)):
    return repo.patch(conn, "escalation_defaults", default_id, body.model_dump(exclude_unset=True),
                      object_type="escalation_default",
                      allow_null={"destination_function_id", "destination_role"})


@router.get("/internal-settings")
def settings(conn: sqlite3.Connection = Depends(get_conn)):
    return repo.row_to_dict(conn.execute("SELECT * FROM internal_operations_settings WHERE id='singleton'").fetchone())


@router.patch("/internal-settings")
def patch_settings(body: InternalSettingsPatch, conn: sqlite3.Connection = Depends(get_conn)):
    values = body.model_dump(exclude_unset=True)
    if values:
        values["updated_at"] = now_utc()
        try:
            with conn:
                conn.execute(f"UPDATE internal_operations_settings SET {','.join(f'{k}=?' for k in values)} WHERE id='singleton'", tuple(values.values()))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(422, str(exc)) from exc
    return repo.row_to_dict(conn.execute("SELECT * FROM internal_operations_settings WHERE id='singleton'").fetchone())


@router.get("/accounts/{account_id}/internal-asks")
def asks(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return service.list_asks(conn, account_id)


@router.post("/accounts/{account_id}/internal-asks", status_code=201)
def create(account_id: str, body: InternalAskCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.create_ask(conn, account_id, body.model_dump())


@router.post("/internal-asks/{ask_id}/status")
def status(ask_id: str, body: InternalAskStatus, conn: sqlite3.Connection = Depends(get_conn)):
    return service.transition(conn, ask_id, body.model_dump())


@router.post("/internal-asks/{ask_id}/escalations", status_code=201)
def escalate(ask_id: str, body: EscalationCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.open_escalation(conn, ask_id, body.severity, body.default_id)


@router.post("/escalations/{escalation_id}/events", status_code=201)
def event(escalation_id: str, body: EscalationEventCreate, conn: sqlite3.Connection = Depends(get_conn)):
    return service.add_escalation_event(conn, escalation_id, body.model_dump())
