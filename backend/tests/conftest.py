"""Shared test helpers.

The only thing here is the date clock, and it exists because getting it wrong has broken
this suite three separate times.

Every date the application writes or compares comes from `app.db.now_utc()` — the standing
UTC rule in CLAUDE.md — and SQLite's `date('now')` is UTC too. A fixture that builds dates
from `date.today()` uses the *local* clock instead, so between 20:00 and midnight in US time
zones the fixture is one day behind the code under test. Tests written with a day or two of
margin survive that; tests that pin an exact boundary ("needed by today") fail every evening
and pass every morning, which reads as flakiness rather than as the clock mismatch it is.

Derive fixture dates from `utc_day()` so the fixture and the system under test share a clock.
"""
from __future__ import annotations

from datetime import date, timedelta


def utc_day(offset: int = 0) -> str:
    """The application's own current date, shifted by `offset` days (ISO-8601)."""
    from app.db import now_utc

    return (date.fromisoformat(now_utc()[:10]) + timedelta(days=offset)).isoformat()
