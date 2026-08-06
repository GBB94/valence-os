"""Evidence drill-through — RELATIONSHIP-READINESS-SPEC.md §5.3/§8.3/§11.5.

RR-1 shipped the evidence *list* and this was the piece it was missing: "evidence opens the native
record or source location" (§8.3), asserted at §11.5 as "evidence links open the correct native
target". Until now `Readiness.jsx` named the records and opened none of them, and the stage-15
verification document claimed otherwise — the correction is recorded in decisions.md.

The tests below are about the two ways a route can lie rather than crash. A target that names a tab
which cannot show the record sends an operator hunting through the wrong panel and blames them for
not finding it; a kind that quietly gets no route at all disappears from the drill-through without
anyone noticing it left. So the map is asserted against the tab and sub-view allowlists the
frontend actually honours, and the unrouted kinds are asserted *by name* — an unrouted kind has to
be a decision someone wrote down, not an omission.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.readiness import _EVIDENCE_TARGET, _ev
from conftest import utc_day


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


# The eight account workspace tabs, and the sub-views each one can actually render. Restated here
# rather than imported because the frontend owns them: if App.jsx drops a tab or renames a People
# panel, this copy stops matching and the mismatch is the point.
_WORKSPACE_TABS = {"overview", "ledger", "people", "plan", "commercial", "evidence", "outputs",
                   "internal"}
_SUBVIEWS = {
    "commercial": {"whitespace", "ledger", "funding", "signals", "company", "growth", "pipeline"},
    "people": {"map", "champions", "influence", "exec", "changes", "messaging"},
}

# Kinds that deliberately have no route. `account_field` and `program_field` name a column on a
# record the pillar has already identified — its id is `table.column`, not a record id — and
# `source_reference` is provenance attached to another record rather than a record with a home.
_UNROUTED = {"account_field", "program_field", "source_reference"}


def _acct(c, name="Northwind Synthetic"):
    return c.post("/api/accounts", json={"name": name}).json()


def _prog(c, account_id, name, phase="programmatic"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _person(c, account_id, name, title=None):
    r = c.post("/api/persons", json={"name": name, "account_id": account_id,
                                     "affiliation": "client", "title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _role(c, program_id, person_id, role, layer=None):
    r = c.post("/api/stakeholder-roles", json={
        "program_id": program_id, "person_id": person_id, "role": role,
        "layer": layer, "stance": "supporter", "influence": "high",
        "stance_assessed_on": utc_day(-3), "stance_evidence_note": "Said so on the kickoff call.",
        "influence_assessed_on": utc_day(-3),
        "influence_evidence_note": "Chaired the budget review."})
    assert r.status_code == 201, r.text
    return r.json()


def _evidence_items(result):
    """Every evidence item in a readiness response, account scope and program scopes alike."""
    out = []
    groups = list(result.get("pillars") or [])
    for entry in result.get("programs") or []:
        groups.extend(entry.get("pillars") or [])
    for pillar in groups:
        for component in pillar.get("components") or []:
            out.extend(component.get("evidence") or [])
    return out


# --- the route map itself --------------------------------------------------------------------

def test_every_routed_kind_names_a_tab_and_sub_view_the_app_can_render():
    """A target the frontend cannot honour is worse than none: it opens the wrong panel silently."""
    for kind, (tab, subview) in _EVIDENCE_TARGET.items():
        assert tab in _WORKSPACE_TABS, f"{kind} routes to unknown tab {tab!r}"
        if subview is None:
            assert tab not in _SUBVIEWS, (
                f"{kind} routes to {tab!r}, which has sub-views, without naming one")
        else:
            assert subview in _SUBVIEWS.get(tab, set()), (
                f"{kind} routes to {tab}/{subview!r}, which that tab does not render")


def test_the_kinds_with_no_native_home_are_named_rather_than_merely_absent():
    """An unrouted kind must be a decision. Absence alone cannot distinguish one from an oversight."""
    for kind in _UNROUTED:
        assert kind not in _EVIDENCE_TARGET
        assert _ev(kind, "acc-1.renewal_date", "Renewal date")["native_target"] is None


def test_a_target_carries_the_record_id_it_was_built_from():
    ev = _ev("stakeholder_role", "role-42", "Priya Raman — economic buyer")
    assert ev["native_target"] == {"tab": "people", "subview": "map",
                                   "record_type": "stakeholder_role", "record_id": "role-42"}


def test_the_key_is_always_present_so_the_view_never_has_to_guess():
    """`null` and "missing" render the same only if the view checks both. It checks one."""
    assert "native_target" in _ev("account_field", "accounts.renewal_date", "Renewal date")


# --- against a live evaluation ----------------------------------------------------------------

def test_live_evidence_routes_to_the_record_it_names(client):
    account = _acct(client)
    program = _prog(client, account["id"], "Field launch")
    priya = _person(client, account["id"], "Priya Raman", title="Director of Operations")
    role = _role(client, program["id"], priya["id"], "budget_owner", layer="economic")

    result = client.get(
        f"/api/accounts/{account['id']}/readiness?program_id={program['id']}").json()
    items = _evidence_items(result)
    assert items, "the fixture produced no evidence to route"

    by_id = {(e["type"], e["id"]): e for e in items}
    assert ("stakeholder_role", role["id"]) in by_id or ("person", priya["id"]) in by_id

    for ev in items:
        target = ev["native_target"]
        if ev["type"] in _UNROUTED:
            assert target is None
            continue
        assert target is not None, f"{ev['type']} evidence shipped with no route"
        # The route points at the record the operator clicked, not at the pillar's scope.
        assert target["record_id"] == ev["id"]
        assert target["record_type"] == ev["type"]
        assert target["tab"] in _WORKSPACE_TABS


def test_no_live_evidence_kind_falls_through_the_map_unannounced(client):
    """The map is a fixed allowlist, so a new evaluator kind must be routed or named, not dropped."""
    account = _acct(client)
    program = _prog(client, account["id"], "Field launch")
    for name, role, layer in [("Priya Raman", "budget_owner", "economic"),
                              ("Tomas Belka", "executive_sponsor", "executive"),
                              ("Ines Duarte", "program_owner", "operational")]:
        person = _person(client, account["id"], name)
        _role(client, program["id"], person["id"], role, layer=layer)

    for scope in (None, program["id"]):
        query = f"?program_id={scope}" if scope else ""
        result = client.get(f"/api/accounts/{account['id']}/readiness{query}").json()
        for ev in _evidence_items(result):
            assert ev["type"] in _EVIDENCE_TARGET or ev["type"] in _UNROUTED, (
                f"{ev['type']} evidence has neither a route nor a recorded reason to lack one")
