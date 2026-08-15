import sqlite3

from fastapi import APIRouter, Depends

from .. import audit, portfolio_absence, queue, repo
from ..db import now_utc
from ..deps import get_conn
from ..schemas import AccountStatusUpdate, QueueResolve, QueueSnooze

router = APIRouter(prefix="/api", tags=["attention"])


@router.get("/queue")
def get_queue(conn: sqlite3.Connection = Depends(get_conn)):
    return queue.build_queue(conn)


@router.get("/portfolio/absence")
def get_absence(days: int = portfolio_absence.DEFAULT_WINDOW_DAYS,
                conn: sqlite3.Connection = Depends(get_conn)):
    """Where we are not looking. Lives beside the queue because it is the same surface's question
    asked in the negative: the queue ranks what exists, this counts what does not."""
    return portfolio_absence.absence_counters(conn, days)


@router.post("/queue/snooze")
def snooze(b: QueueSnooze, conn: sqlite3.Connection = Depends(get_conn)):
    return queue.snooze(conn, item_key=b.item_key, snooze_until=b.snooze_until,
                        resurface_condition=b.resurface_condition)


@router.post("/queue/resolve")
def resolve(b: QueueResolve, conn: sqlite3.Connection = Depends(get_conn)):
    return queue.resolve(conn, item_key=b.item_key,
                         successor_action_type=b.successor_action_type,
                         successor_action_id=b.successor_action_id)


@router.post("/accounts/{account_id}/status")
def set_status(account_id: str, b: AccountStatusUpdate, conn: sqlite3.Connection = Depends(get_conn)):
    """Set one hand-judged status dimension. Assessment is dated; the two dimensions
    are fully independent (no composite score)."""
    before = repo.get_row(conn, "accounts", account_id)
    prefix = b.dimension  # 'delivery' or 'commercial'
    changes = {
        f"{prefix}_status": b.value,
        f"{prefix}_status_rationale": b.rationale,
        f"{prefix}_status_assessed_on": b.assessed_on or now_utc()[:10],
        f"{prefix}_status_change_condition": b.change_condition,
        "updated_at": now_utc(),
    }
    sets = ", ".join(f"{k} = ?" for k in changes)
    with conn:
        conn.execute(f"UPDATE accounts SET {sets} WHERE id = ?", (*changes.values(), account_id))
        after = repo.get_row(conn, "accounts", account_id)
        audit.record(conn, object_type="account", object_id=account_id, action="update",
                     before=before, after=after)
    return after
