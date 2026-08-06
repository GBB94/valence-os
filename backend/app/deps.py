from fastapi import Request
import sqlite3
from collections.abc import Iterator

def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Serialize access to the local-mode SQLite connection across worker threads.

    The application intentionally owns one local connection so multi-step handlers and the in-process
    job path share a transaction boundary. ``check_same_thread=False`` permits thread handoff but does
    not make concurrent cursor/transaction use safe, so the request dependency carries the lock.
    """
    with request.app.state.conn_lock:
        yield request.app.state.conn
