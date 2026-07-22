from fastapi import Request
import sqlite3


def get_conn(request: Request) -> sqlite3.Connection:
    return request.app.state.conn
