"""Architecture regression tests — dependency direction and single-write-path invariants.

These test the *shape* of the codebase, not its behavior: which direction imports may point and
which module is allowed to write which table. They exist because every one of these rules was
broken at least once while the code still passed its behavioral suite — domain modules importing a
private router function, a second Interaction writer inside ingestion, two copies of the phase
graph. Green behavior tests protect what the code does; these protect where the next feature will
be written.

They are deliberately AST-based rather than filename-trivia: a rule fails only when an import
statement or a SQL string actually crosses a boundary.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# Modules that are not domain code. `main` wires routers by design; `deps` is FastAPI plumbing;
# `seed` assembles demo fixtures (it must still not import routers — that is asserted below —
# but it may write tables directly because it builds scenes, not records).
_NON_DOMAIN = {"main", "deps"}

# The measurement side (SURFACE-USAGE-SPEC §17.1, D-320): these may read domain tables; domain
# modules may never import them. `surfaces` is the registry and is importable (it declares, it
# does not measure); `measure`/`telemetry` write the event stream.
_MEASUREMENT_MODULES = {"telemetry", "surface_usage", "surface_triggers", "surface_retirement"}


def _module_imports(path: Path) -> set[str]:
    """Every module name this file imports, at top level or inside a function."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Relative imports: `from .routers.ai import x` → "routers.ai"; `from . import x`
            # names its targets, so record those too.
            if node.level and not module:
                found.update(alias.name for alias in node.names)
            else:
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def _domain_modules() -> list[Path]:
    return [p for p in sorted(APP.glob("*.py"))
            if p.stem not in _NON_DOMAIN and not p.stem.startswith("_")]


def test_no_domain_module_imports_from_routers():
    """The dependency arrow points down: routers call domain services, never the reverse.

    This is the regression test for the `_persist_run` inversion — `coaching`, `intake_drop`,
    `ingestion`, and the seed all imported a private function off the AI router before proposal
    persistence moved into `extraction_runs`.
    """
    offenders = {}
    for path in _domain_modules():
        crossing = {name for name in _module_imports(path)
                    if name == "routers" or name.startswith(("routers.", "app.routers"))}
        if crossing:
            offenders[path.name] = sorted(crossing)
    assert not offenders, f"domain modules importing from app.routers: {offenders}"


def test_no_domain_module_imports_measurement():
    """§17.1's one-directional boundary: measurement reads domain, domain never imports it."""
    offenders = {}
    for path in _domain_modules():
        if path.stem in _MEASUREMENT_MODULES or path.stem == "surfaces":
            continue
        crossing = set()
        for name in _module_imports(path):
            leaf = name.split(".")[-1]
            root = name.split(".")[0]
            if leaf in _MEASUREMENT_MODULES or root in _MEASUREMENT_MODULES:
                crossing.add(name)
        if crossing:
            offenders[path.name] = sorted(crossing)
    assert not offenders, f"domain modules importing measurement: {offenders}"


def _files_writing(table: str, *, verb: str = "INSERT INTO") -> set[str]:
    pattern = re.compile(rf"{verb}\s+{table}\b", re.IGNORECASE)
    hits = set()
    for path in sorted(APP.rglob("*.py")):
        if pattern.search(path.read_text()):
            hits.add(str(path.relative_to(APP)))
    return hits


def test_one_extraction_run_writer():
    """There is one proposal store and `extraction_runs.py` is its only writer (RR-2).

    A second INSERT site is how an input adapter grows a private proposal path whose review
    semantics quietly differ. The seed goes through the same service.
    """
    assert _files_writing("extraction_runs") == {"extraction_runs.py"}
    assert _files_writing("extraction_proposals") == {"extraction_runs.py"}


def test_one_interaction_writer():
    """`interaction_ops.create` is the only code that inserts an Interaction.

    QuickEntry, Call Coach, and recording ingestion all create the same account record; a second
    writer is how one of them becomes subtly weaker (no audit, no participant scope check). The
    seed assembles fixture rows directly and is the single named exemption.
    """
    writers = _files_writing("interactions")
    assert writers <= {"interaction_ops.py", "seed.py"}, writers
    assert "interaction_ops.py" in writers
    # repo.insert reaches tables generically; assert no module hands it the interactions table.
    generic = re.compile(r"repo\.insert\(\s*conn\s*,\s*[\"']interactions[\"']")
    offenders = [str(p.relative_to(APP)) for p in APP.rglob("*.py") if generic.search(p.read_text())]
    assert not offenders, f"repo.insert('interactions') outside interaction_ops: {offenders}"


def test_phase_vocabulary_has_one_authority():
    """`program_phases` owns the lifecycle; ranking, readiness, and the API schema agree with it.

    `schemas.Phase` is a pydantic Literal and must be spelled out, so it is asserted equal rather
    than derived. If this fails, a phase was added in one place and not the others — which is the
    exact disagreement the module exists to prevent.
    """
    from app import execution_path, phase_readiness, program_phases, schemas
    from typing import get_args

    assert execution_path.PHASE_ORDER is program_phases.PHASE_ORDER
    assert phase_readiness.PHASE_ORDER is program_phases.PHASE_ORDER
    assert execution_path.PHASE_LABELS is program_phases.PHASE_LABELS
    assert phase_readiness.PHASE_LABELS is program_phases.PHASE_LABELS
    assert tuple(get_args(schemas.Phase)) == program_phases.PHASE_ORDER
    assert set(program_phases.PHASE_LABELS) == set(program_phases.PHASE_ORDER)
    # The graph is linear with a terminal end.
    assert program_phases.next_phase("closed") is None
    assert program_phases.next_phase("foundation") == "launch"
    assert program_phases.next_phase("not-a-phase") is None


def test_command_center_family_shares_the_scope_check():
    """Activity, the command center, Prepare, and Leadership validate scope in one place.

    Asserted structurally: none of the three consumers restates the ownership SQL, and the one
    shared message exists only in `account_activity`.
    """
    consumers = ["account_command_center.py", "account_prepare.py", "account_leadership.py"]
    for name in consumers:
        text = (APP / name).read_text()
        assert "does not belong to account" not in text, name
        assert "validate_scope" in text, name
    assert "does not belong to account" in (APP / "account_activity.py").read_text()
