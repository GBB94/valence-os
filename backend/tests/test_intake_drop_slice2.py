"""Acceptance tests for ACCOUNT-INTAKE-SPEC.md Slice 2 — a dropped `.eml`.

Slice 1 proved a dropped document cannot overreach. This slice is about the opposite failure: a
dropped message that reaches *too little*. §7.4 is the finding with the longest reach in the spec —
if a dropped `.eml` skipped straight to extraction it would never enter the comms timeline, and
because relationship-health signals are counts over our own correspondence, it would be silently
missing from reciprocity and response-time figures that are supposed to describe all of it. That
failure does not raise; it produces numbers that are quietly wrong. So the tests here mostly assert
that the drop path and the sync path produce the *same* records, and that where they differ the
difference is a stated fact about origin rather than a divergence in reading.

Everything here is synthetic. No real client names, people, or figures (CLAUDE.md).
"""
import base64
import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        c.db_path = path
        yield c
    for suffix in ("", "-wal", "-shm"):
        try: os.unlink(path + suffix)
        except FileNotFoundError: pass


# --- fixtures --------------------------------------------------------------------------------

def _account(c, name="Northwind Synthetic"):
    r = c.post("/api/accounts", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _program(c, account_id, name="Synthetic launch", phase="launch"):
    r = c.post("/api/programs", json={"account_id": account_id, "name": name, "phase": phase})
    assert r.status_code == 201, r.text
    return r.json()


def _drop_eml(c, account_id, raw: bytes, filename="message.eml", **body):
    r = c.post(f"/api/accounts/{account_id}/intake/drops",
               json={"content_b64": base64.b64encode(raw).decode("ascii"),
                     "filename": filename, **body})
    assert r.status_code == 201, r.text
    return r.json()


def _rows(c, sql, params=()):
    conn = sqlite3.connect(c.db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


NEW_MESSAGE = (
    "Thanks — I'll confirm the training room booking by Wednesday.\n"
    "Ada will send the rollout plan by Friday.\n"
    "Risk: the room booking may slip and that would block the launch.\n"
)

QUOTED_BELOW = (
    "\n"
    "On Tue, 4 Aug 2026 at 09:14, Bo Sinclair wrote:\n"
    "> We agreed that the pilot cohort is the northern region.\n"
    "> Ada will send the contract to procurement by Monday.\n"
)


def _eml(*, body=NEW_MESSAGE, subject="Cohort 2 launch window",
         message_id="<msg-001@synthetic.example>", from_addr="ada@northwind-synthetic.example",
         charset="utf-8", content_type=None, extra_headers="") -> bytes:
    """One RFC-822 message as bytes. Built here rather than as a repo fixture because the point of
    several of these tests is a byte sequence the repo should not contain a file of."""
    ctype = content_type or f'text/plain; charset="{charset}"'
    head = (f"From: Ada Sinclair <{from_addr}>\r\n"
            "To: bo@example.test\r\n"
            f"Subject: {subject}\r\n"
            "Date: Wed, 5 Aug 2026 11:02:00 +0000\r\n"
            f"Message-ID: {message_id}\r\n"
            "MIME-Version: 1.0\r\n"
            f"Content-Type: {ctype}\r\n"
            f"{extra_headers}"
            "\r\n")
    return head.encode("ascii") + body.encode(charset)


MULTIPART = (
    b"From: Ada Sinclair <ada@northwind-synthetic.example>\r\n"
    b"To: bo@example.test\r\n"
    b"Subject: Rollout plan attached\r\n"
    b"Date: Wed, 5 Aug 2026 11:02:00 +0000\r\n"
    b"Message-ID: <msg-mp@synthetic.example>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/mixed; boundary="b1"\r\n'
    b"\r\n"
    b"--b1\r\n"
    b'Content-Type: text/plain; charset="utf-8"\r\n'
    b"\r\n"
    b"Ada will send the rollout plan by Friday.\r\n"
    b"\r\n"
    b"--b1\r\n"
    b'Content-Type: application/octet-stream; name="rollout-plan.pdf"\r\n'
    b'Content-Disposition: attachment; filename="rollout-plan.pdf"\r\n'
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n"
    b"SGVsbG8=\r\n"
    b"--b1--\r\n"
)

HTML_ONLY = (
    b"From: Ada Sinclair <ada@northwind-synthetic.example>\r\n"
    b"To: bo@example.test\r\n"
    b"Subject: Newsletter\r\n"
    b"Date: Wed, 5 Aug 2026 11:02:00 +0000\r\n"
    b"Message-ID: <msg-html@synthetic.example>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: text/html; charset="utf-8"\r\n'
    b"\r\n"
    b"<html><body><p>Ada will send the rollout plan by Friday.</p></body></html>\r\n"
)


# --- §7.3: one parser, two callers -------------------------------------------------------------

def test_the_fixture_parser_and_the_bytes_parser_are_the_same_function():
    """A second `.eml` parser for drops is how the sync path and the drop path start disagreeing
    about what a message said. `_parse_eml` must be a thin caller, not a copy."""
    from pathlib import Path

    from app import adapters

    fixtures = sorted(adapters.EMAIL_DIR.glob("*.eml"))
    assert fixtures, "the mock inbox fixtures are what make this comparison meaningful"
    for path in fixtures:
        assert adapters._parse_eml(path) == adapters.parse_eml_bytes(path.read_bytes(), path.name)
        assert adapters._parse_eml(Path(path)) == adapters.parse_eml_bytes(
            path.read_bytes(), path.name)


def test_a_part_is_decoded_with_the_charset_it_declares():
    """§4.1: `.eml` is not held to the UTF-8 gate. A message that declares iso-8859-1 and means it
    must come back byte-accurate — a citation is only worth having if it says what the source said.
    """
    from app import adapters

    body = "Ada will send the rollout plan by Friday. Café closes at 17:00.\n"
    raw = _eml(body=body, charset="iso-8859-1")
    assert b"Caf\xe9" in raw, "the fixture must actually be non-UTF-8 or this proves nothing"
    parsed = adapters.parse_eml_bytes(raw, "message.eml")
    assert "Café" in parsed["body"]
    assert "�" not in parsed["body"]


def test_an_eml_dropped_as_latin1_bytes_survives_to_the_snapshot(client):
    account = _account(client)
    raw = _eml(body="Ada will send the rollout plan by Friday. Café closes at 17:00.\n",
               charset="iso-8859-1")
    drop = _drop_eml(client, account["id"], raw)
    assert drop["outcome"] == "drafted", drop
    assert "Café" in drop["snapshot_text"]


# --- §7.4: the same records as a synced message ------------------------------------------------

def test_a_dropped_eml_creates_a_comm_message_on_the_dropped_account(client):
    """The whole slice. Without this the message is missing from the comms timeline and from the
    correspondence-derived relationship counts, and nothing raises to say so."""
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml())

    assert drop["detected_kind"] == "email_file"
    assert drop["comm_message_id"], drop
    comms = client.get(f"/api/accounts/{account['id']}/comms").json()
    ids = [row["id"] for row in (comms if isinstance(comms, list) else comms.get("comms", []))]
    assert drop["comm_message_id"] in ids, comms


def test_the_comm_message_carries_message_and_thread_identity(client):
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml())
    row = _rows(client, "SELECT * FROM comm_messages WHERE id=?", (drop["comm_message_id"],))[0]
    assert row["message_id"] == "msg-001@synthetic.example"
    assert row["external_id"] == "msg-001@synthetic.example"
    # A message with no In-Reply-To/References starts its own thread and keys on its own id.
    assert row["thread_id"] == "msg-001@synthetic.example"
    assert row["new_text_hash"], "the §14.8 dedupe key must be set or nothing can dedupe on it"


def test_the_account_is_the_page_not_the_sender(client):
    """§8. The sender resolves to nobody here, and it must not matter: a human chose this page."""
    account = _account(client)
    other = _account(client, "Southgate Synthetic")
    drop = _drop_eml(client, account["id"], _eml())
    row = _rows(client, "SELECT * FROM comm_messages WHERE id=?", (drop["comm_message_id"],))[0]
    assert row["account_id"] == account["id"]
    assert row["account_id"] != other["id"]
    assert (row["confidence"] or 0) >= 1.0, "an operator's own choice is not a low-confidence guess"


def test_the_selected_program_reaches_the_comm_message_and_the_run(client):
    account = _account(client)
    program = _program(client, account["id"])
    drop = _drop_eml(client, account["id"], _eml(), program_id=program["id"])
    comm = _rows(client, "SELECT * FROM comm_messages WHERE id=?", (drop["comm_message_id"],))[0]
    assert comm["program_id"] == program["id"]
    run = _rows(client, "SELECT * FROM extraction_runs WHERE id=?", (drop["extraction_run_id"],))[0]
    assert run["program_id"] == program["id"]


def test_exactly_one_extraction_run_comes_from_one_dropped_message(client):
    """The drop must take ingestion's run, not persist a second one beside it. Two runs from one
    message is the same commitment in the review queue twice."""
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml())
    runs = _rows(client, "SELECT * FROM extraction_runs WHERE account_id=?", (account["id"],))
    assert len(runs) == 1, runs
    assert runs[0]["id"] == drop["extraction_run_id"]
    comm = _rows(client, "SELECT * FROM comm_messages WHERE id=?", (drop["comm_message_id"],))[0]
    assert comm["extraction_run_id"] == runs[0]["id"], "the comm and the drop point at one run"


def test_the_run_names_the_drop_as_its_provider_not_the_mock_inbox(client):
    """§6.6. Two providers can hand back the same Message-ID and mean different material, so a run
    drafted from a file off the operator's machine must not claim inbox provenance."""
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml())
    run = _rows(client, "SELECT * FROM extraction_runs WHERE id=?", (drop["extraction_run_id"],))[0]
    assert run["provider"] == "account_drop"
    assert run["source_kind"] == "email", "it is an email however it arrived"
    assert run["external_id"] == "msg-001@synthetic.example"


def test_a_dropped_message_keeps_no_file_url(client):
    """§5 keeps no bytes, so there is no location to point at. A `fixture://` url would name a file
    that was never written."""
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml())
    comm = _rows(client, "SELECT * FROM comm_messages WHERE id=?", (drop["comm_message_id"],))[0]
    src = _rows(client, "SELECT * FROM source_references WHERE id=?",
                (comm["source_reference_id"],))[0]
    assert src["url"] is None, src
    assert src["locator"] == "msg-001@synthetic.example"
    assert "dropped" in src["label"].lower()


# --- deduplication against synced mail ----------------------------------------------------------

def test_dropping_a_message_that_already_synced_is_a_duplicate_not_a_second_record(client):
    """The reason §7.4 insists on the shared path: dedupe only works if both paths write the same
    identity into the same table."""
    account = _account(client)
    raw = _eml()
    first = _drop_eml(client, account["id"], raw)
    assert first["outcome"] == "drafted"

    second = _drop_eml(client, account["id"], raw)
    assert second["outcome"] == "duplicate", second
    assert second["comm_message_id"] == first["comm_message_id"]
    assert second["extraction_run_id"] is None
    assert "already" in (second["outcome_reason"] or "").lower()

    comms = _rows(client, "SELECT * FROM comm_messages WHERE external_id=?",
                  ("msg-001@synthetic.example",))
    assert len(comms) == 1, comms
    runs = _rows(client, "SELECT * FROM extraction_runs WHERE account_id=?", (account["id"],))
    assert len(runs) == 1, "the second drop must not draft the same commitments again"


def test_a_message_recorded_on_another_account_is_reported_and_not_linked(client):
    """§8 rule 3's discipline. Reporting it is honest; holding a handle on another client's record
    from this account's receipt is not, and re-scoping is the operator's act rather than ours."""
    first_account = _account(client)
    second_account = _account(client, "Southgate Synthetic")
    raw = _eml()
    _drop_eml(client, first_account["id"], raw)

    drop = _drop_eml(client, second_account["id"], raw)
    assert drop["outcome"] == "duplicate"
    assert drop["comm_message_id"] is None, "no cross-account handle on the receipt"
    assert "different account" in (drop["outcome_reason"] or "")


# --- §14.8: only new text is read ---------------------------------------------------------------

def test_quoted_history_in_a_dropped_eml_is_counted_and_not_read(client):
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml(body=NEW_MESSAGE + QUOTED_BELOW))
    assert drop["outcome"] == "drafted"
    assert drop["quoted_chars"] > 0

    reasons = {e["reason"]: e for e in drop["coverage"]["skipped"]}
    assert "quoted_history" in reasons
    # `no_message_id` is a paste's reason. An .eml has one — that is the point of the slice.
    assert "no_message_id" not in reasons

    spans = " ".join(
        p["source_span"] or "" for p in
        _rows(client, "SELECT * FROM extraction_proposals WHERE run_id=?",
              (drop["extraction_run_id"],)))
    assert "rollout plan" in spans
    assert "procurement" not in spans, "the quoted message was drafted from once already"


def test_read_the_whole_thread_is_refused_for_an_eml_and_says_so(client):
    """It is right for a paste and wrong here. An .eml's quoted history is made of messages that
    carry their own ids, so each is already a record or will be — reading them again drafts the
    same commitments twice. A refusal that changed behaviour silently would be the worse half."""
    account = _account(client)
    drop = _drop_eml(client, account["id"], _eml(body=NEW_MESSAGE + QUOTED_BELOW),
                     read_whole_thread=True)
    coverage = drop["coverage"]
    assert coverage["read_whole_thread"] is False
    refused = {e["what"]: e["why"] for e in coverage["refused"]}
    assert "Read the whole thread" in refused
    assert refused["Read the whole thread"].strip(), "a refusal with no reason is not a refusal"

    spans = " ".join(
        p["source_span"] or "" for p in
        _rows(client, "SELECT * FROM extraction_proposals WHERE run_id=?",
              (drop["extraction_run_id"],)))
    assert "procurement" not in spans, "refused means refused, not merely labelled"


# --- attachments and unreadable bodies ----------------------------------------------------------

def test_attachments_are_named_never_opened(client):
    account = _account(client)
    drop = _drop_eml(client, account["id"], MULTIPART, filename="with-attachment.eml")
    assert drop["outcome"] == "drafted"
    reasons = {e["reason"] for e in drop["coverage"]["skipped"]}
    assert "attachments" in reasons
    comm = _rows(client, "SELECT * FROM comm_messages WHERE id=?", (drop["comm_message_id"],))[0]
    assert "rollout-plan.pdf" in (comm["attachments"] or "")
    assert "rollout-plan.pdf" not in (drop["snapshot_text"] or ""), \
        "the name is a reference; the file was not read into the snapshot"


def test_an_html_only_message_is_still_correspondence_even_though_it_is_not_read(client):
    """Declining to read markup is a choice about our parser, not about whether the message
    happened. Dropping it from the comms record would make reciprocity counts wrong."""
    account = _account(client)
    drop = _drop_eml(client, account["id"], HTML_ONLY, filename="newsletter.eml")
    assert drop["outcome"] == "no_proposals", drop
    assert drop["comm_message_id"], "it is still correspondence"
    assert drop["extraction_run_id"] is None
    assert "html" in (drop["outcome_reason"] or "").lower()


def test_a_file_named_eml_that_holds_no_message_fails_to_parse(client):
    account = _account(client)
    drop = _drop_eml(client, account["id"], b"just some words, not a message at all\n",
                     filename="notes.eml")
    assert drop["outcome"] == "parse_failed", drop
    assert drop["comm_message_id"] is None
    assert drop["extraction_run_id"] is None


# --- what the operator is told ------------------------------------------------------------------

def test_eml_is_accepted_and_msg_is_refused_with_its_own_reason(client):
    """`.msg` used to share `.eml`'s refusal. It cannot now: `.eml` is read, and a `.msg` is a
    Microsoft compound binary rather than a variant of RFC-822, so the old sentence would be false
    as well as unhelpful."""
    limits = client.get("/api/intake/limits").json()
    assert ".eml" in limits["accepted_extensions"]
    assert ".eml" not in limits["refusals"]
    assert ".eml" in limits["accepted_summary"]

    msg_reason = limits["refusals"][".msg"]
    assert ".msg" in msg_reason or "msg" in msg_reason.lower()
    assert ".eml" in msg_reason, "a refusal must offer the working path"


def test_kind_detection_routes_eml_by_extension():
    """An `.eml` names a container, not a content shape, so structure has nothing to decide. The
    rule exists so a `.eml` reaching the text path is never read as notes — which would hand its
    raw MIME headers to the extractor as prose."""
    from app import intake_kind

    assert intake_kind.detect_kind("anything at all", "message.eml") == "email_file"
    assert intake_kind.detect_kind("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n",
                                   "message.eml") == "email_file"
    assert "email_file" in intake_kind.KINDS


def test_the_content_hash_separates_two_different_non_utf8_files(client):
    """`utf-8` with `errors="replace"` collapses every undecodable byte to one character, so two
    different messages would hash the same and the second would be reported as a duplicate of the
    first. That is a live case exactly here, where non-UTF-8 bytes arrive."""
    from app import intake_drop

    assert intake_drop._hash_bytes(b"\xe9\xe9") != intake_drop._hash_bytes(b"\xfc\xfc")
    # And identical bytes still hash identically, or duplicate detection stops working.
    assert intake_drop._hash_bytes(b"\xe9\xe9") == intake_drop._hash_bytes(b"\xe9\xe9")


# --- the schema rules, still --------------------------------------------------------------------

def test_migration_0053_keeps_every_rule_0052_stated(client):
    """A table rebuild is where a forbidden column gets reintroduced by accident, so the same
    introspection that guarded 0052 runs again against the rebuilt table."""
    cols = {c["name"]: c for c in _rows(client, "PRAGMA table_info(intake_drops)")}
    forbidden = {"state", "met", "freshness", "coverage", "applicability", "score", "weight"}
    for name in cols:
        assert name not in forbidden, name
        assert not any(name.endswith("_" + f) for f in forbidden), name
    assert "outcome" in cols, "the single named exemption must still be there"
    assert "comm_message_id" in cols
    assert "coverage_json" not in cols, "coverage lives on the run, in one place"

    indexes = {r["name"] for r in _rows(client, "PRAGMA index_list(intake_drops)")}
    assert any("account" in n for n in indexes)
    assert any("hash" in n for n in indexes)

    fks = {r["table"] for r in _rows(client, "PRAGMA foreign_key_list(intake_drops)")}
    assert {"accounts", "programs", "extraction_runs", "comm_messages"} <= fks, fks


def test_the_drop_router_still_has_no_route_that_resolves_a_proposal(client):
    """Slice 2 added a path through ingestion. It must not have added a second acceptance surface
    along with it — `ProposalReview` stays the one place a drafted proposal becomes a decision."""
    from app.main import app

    paths = [r.path for r in app.routes if "intake" in getattr(r, "path", "")]
    banned = ("accept", "reject", "resolve", "supersede", "apply", "confirm")
    for path in paths:
        assert not any(word in path for word in banned), path


def test_program_selection_never_crosses_an_account(client):
    """A matched person can hold a stakeholder role in another account's program. Before the drop
    supplied the account independently of the people, that could not surface; now it can."""
    from app import association

    account = _account(client)
    other = _account(client, "Southgate Synthetic")
    other_program = _program(client, other["id"], name="Southgate launch")
    person = client.post("/api/persons", json={
        "name": "Ada Sinclair", "account_id": other["id"],
        "email": "ada@northwind-synthetic.example"})
    assert person.status_code == 201, person.text
    role = client.post("/api/stakeholder-roles", json={
        "person_id": person.json()["id"], "program_id": other_program["id"], "role": "champion"})
    assert role.status_code == 201, role.text

    conn = sqlite3.connect(client.db_path)
    conn.row_factory = sqlite3.Row
    try:
        picked = association.pick_program(conn, account["id"], [person.json()["id"]])
    finally:
        conn.close()
    assert picked != other_program["id"], "a program from another account is never the answer"
