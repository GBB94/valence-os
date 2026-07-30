"""Guided account onboarding (PHASE-3-SPEC.md §1) — seeds a launch plan, prep tasks,
time-phased checklists, and org-chart placeholders in one pass, all relative to a kickoff date.

Templates are editable seed files under app/templates/ (§1b/§1e/§2/§3): evolving the standard
launch is a file edit, not a schema change. Pure product — no adapters. Mock-only data.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import HTTPException

from . import repo
from .db import now_utc

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=None)
def _template(name: str) -> dict:
    return yaml.safe_load((TEMPLATES_DIR / name).read_text(encoding="utf-8"))


def _offset(kickoff: str, days: int | None) -> str | None:
    if days is None:
        return None
    return (date.fromisoformat(kickoff[:10]) + timedelta(days=days)).isoformat()


def seed_onboarding(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    kickoff_date: str,
    program_id: str | None = None,
    program_name: str | None = None,
    region: str | None = None,
    europe_in_scope: bool = False,
) -> dict:
    """Create/attach a program and seed the full launch pack. Idempotent per program:
    re-onboarding an already-onboarded program is a 409, not a duplicate seed."""
    repo.get_row(conn, "accounts", account_id)  # 404s on a bad account

    if program_id:
        prog = repo.get_row(conn, "programs", program_id)
        if prog.get("onboarded_at"):
            raise HTTPException(409, f"program already onboarded: {program_id}")
    else:
        prog = repo.insert(conn, "programs", {
            "account_id": account_id,
            "name": program_name or "Launch",
            "phase": "launch",
            "region": region,
        }, object_type="program")
    pid = prog["id"]

    plan = _template("launch_plan.yaml")
    checklist = _template("launch_checklist.yaml")
    org = _template("org_placeholders.yaml")

    counts = {"milestones": 0, "prep_tasks": 0, "checklist_items": 0, "placeholders": 0}

    # §1b — milestones, dates relative to kickoff.
    for m in plan["milestones"]:
        repo.insert(conn, "milestones", {
            "program_id": pid, "name": m["name"],
            "target_date": _offset(kickoff_date, m["offset_days"]),
            "success_criteria": m.get("success_criteria"),
        }, object_type="milestone")
        counts["milestones"] += 1

    # §1c — kickoff prep tasks, back-scheduled from kickoff.
    for t in plan["prep_tasks"]:
        repo.insert(conn, "tasks", {
            "program_id": pid, "description": t["description"],
            "due_date": _offset(kickoff_date, t["offset_days"]),
        }, object_type="task")
        counts["prep_tasks"] += 1

    # §2/§1e — time-phased checklist items (first_call doubles as the question list).
    for section, items in checklist.items():
        for it in items:
            repo.insert(conn, "checklist_items", {
                "account_id": account_id, "program_id": pid,
                "template_key": f"{section}:{it['label']}", "section": section,
                "label": it["label"], "detail": it.get("detail"),
                "fills_field": it.get("fills_field"),
                "due_offset_days": it.get("due_offset_days"),
                "due_date": _offset(kickoff_date, it.get("due_offset_days")),
            }, object_type="checklist_item")
            counts["checklist_items"] += 1

    # §3 — org-chart placeholders (persons is_placeholder=1 + a stakeholder_role so they graph).
    for ph in org["placeholders"]:
        if ph.get("europe_only") and not europe_in_scope:
            continue
        person = repo.insert(conn, "persons", {
            "name": f"{ph['title']} (unknown)", "affiliation": "client",
            "account_id": account_id, "title": ph["title"],
            "is_placeholder": 1, "placeholder_why": ph.get("why"),
            "find_by_date": _offset(kickoff_date, ph.get("find_by_offset_days")),
            "expected_influence": ph.get("expected_influence"),
            "expected_role": ph.get("expected_role"),
        }, object_type="person")
        repo.insert(conn, "stakeholder_roles", {
            "program_id": pid, "person_id": person["id"],
            "role": ph.get("expected_role", "other"),
        }, object_type="stakeholder_role")
        counts["placeholders"] += 1

    # mark the program onboarded (kickoff anchor + idempotency guard)
    repo.patch(conn, "programs", pid,
               {"kickoff_date": kickoff_date, "onboarded_at": now_utc()},
               object_type="program")

    return {"program_id": pid, "kickoff_date": kickoff_date, "seeded": counts}


def onboarding_state(conn: sqlite3.Connection, account_id: str) -> dict:
    """Onboarding status for an account: onboarded programs, checklist progress by section,
    and open placeholder positions."""
    repo.get_row(conn, "accounts", account_id)
    progs = conn.execute(
        "SELECT id, name, kickoff_date, onboarded_at FROM programs "
        "WHERE account_id=? AND archived=0", (account_id,)).fetchall()
    items = conn.execute(
        "SELECT * FROM checklist_items WHERE account_id=? AND archived=0 "
        "ORDER BY section, due_date", (account_id,)).fetchall()
    by_section: dict[str, list] = {}
    for r in items:
        by_section.setdefault(r["section"], []).append(dict(r))
    placeholders = conn.execute(
        "SELECT id, name, title, expected_role, expected_influence, placeholder_why, find_by_date "
        "FROM persons WHERE account_id=? AND is_placeholder=1 AND archived=0",
        (account_id,)).fetchall()
    done = sum(1 for r in items if r["status"] == "done")
    return {
        "account_id": account_id,
        "onboarded": any(p["onboarded_at"] for p in progs),
        "programs": [dict(p) for p in progs],
        "checklist": by_section,
        "checklist_progress": {"done": done, "total": len(items)},
        "placeholders": [dict(p) for p in placeholders],
    }


def deck_skeleton(conn: sqlite3.Connection, account_id: str, program_id: str | None = None) -> str:
    """Render the §1d kickoff deck outline (markdown) from the template + live account data.
    The two account-pulled slots are filled; everything else is the standard framework."""
    account = repo.get_row(conn, "accounts", account_id)
    prog = None
    if program_id:
        prog = repo.get_row(conn, "programs", program_id)
    else:
        row = conn.execute(
            "SELECT * FROM programs WHERE account_id=? AND archived=0 "
            "ORDER BY onboarded_at DESC LIMIT 1", (account_id,)).fetchone()
        prog = dict(row) if row else None

    stakeholders = conn.execute(
        "SELECT pe.name, pe.title, sr.role, pe.is_placeholder FROM stakeholder_roles sr "
        "JOIN persons pe ON pe.id = sr.person_id "
        "WHERE sr.program_id = ? AND sr.archived=0 AND pe.archived=0",
        (prog["id"],)).fetchall() if prog else []
    if stakeholders:
        lines = []
        for s in stakeholders:
            marker = " _(position — not yet identified)_" if s["is_placeholder"] else ""
            title = f" — {s['title']}" if s["title"] else ""
            lines.append(f"- **{s['role'].replace('_', ' ')}**: {s['name']}{title}{marker}")
        stakeholder_list = "\n".join(lines)
    else:
        stakeholder_list = "_No stakeholders identified yet._"

    filled = {
        "account_name": account["name"],
        "program_name": prog["name"] if prog else "Launch",
        "generated_on": now_utc()[:10],
        "deal_context": account.get("short_context") or account.get("incumbent_note")
                        or "_No deal context on file yet._",
        "stakeholder_list": stakeholder_list,
    }
    md = _template_text("kickoff_deck.md")
    md = re.sub(r"<!--.*?-->\s*", "", md, flags=re.DOTALL)  # drop template authoring notes
    for key, val in filled.items():
        md = md.replace("{{" + key + "}}", str(val))
    return md.lstrip()


@lru_cache(maxsize=None)
def _template_text(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")
