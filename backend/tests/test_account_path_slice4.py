"""Account Path Slice 4 — transcript/email proposals (ACCOUNT-PATH-SPEC.md §14.8, §14.5, §14.7).

The §14.5 review commands (accept, edit-and-accept, reject, use existing, supersede) already had
backend coverage from RR-2; what is new here is the *email* path into them and the boundaries
§14.8 puts in front of it:

  * quoted history is not new material, so it neither re-flags nor re-proposes;
  * a thread is identified by headers, never by subject;
  * a low-confidence association proposes nothing at all, because writing a proposal names an
    account, and the operator confirming the association is what releases the extractor;
  * a proposal is not work until it is accepted.

The dedupe rule is asserted at material selection rather than on fingerprints on purpose: two
readings of the same sentence in two different messages carry different source references and
legitimately fingerprint apart, so a fingerprint can never be what stops thread history repeating.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app import email_thread


@pytest.fixture()
def client():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.environ["VALENCE_OS_DB"] = path
    os.environ["VALENCE_OS_WORKER"] = "0"
    from app.main import app
    with TestClient(app) as c:
        yield c
    for s in ("", "-wal", "-shm"):
        try: os.unlink(path + s)
        except FileNotFoundError: pass


@pytest.fixture()
def scene(client):
    """An account whose people match the .eml fixtures' addresses."""
    a = client.post("/api/accounts", json={"name": "Bluepeak"}).json()
    p = client.post("/api/programs", json={"account_id": a["id"], "name": "Launch",
                                           "phase": "launch"}).json()
    aisha = client.post("/api/persons", json={"name": "Aisha Kone", "account_id": a["id"],
                                              "email": "aisha.kone@example-bluepeak.test"}).json()
    client.post("/api/stakeholder-roles",
                json={"program_id": p["id"], "person_id": aisha["id"], "role": "champion"})
    # Deliberately no email address: our own follow-up owner is a recipient on every fixture, and
    # giving him a matchable address would resolve every inbound message by the person WE cc'd.
    sam = client.post("/api/persons", json={"name": "Sam Rivera", "account_id": a["id"]}).json()
    return {"c": client, "a": a, "p": p, "aisha": aisha, "sam": sam}


def _comm(client, account_id, message_id):
    comms = client.get(f"/api/accounts/{account_id}/comms").json()["comms"]
    return next((m for m in comms if m["message_id"] == message_id), None)


def _proposals(client, account_id):
    body = client.get(f"/api/accounts/{account_id}/proposed-updates").json()
    return [p for g in body["groups"] for t in g["targets"] for p in t["proposals"]]


# --- §14.8 quoted-text boundaries (unit) ------------------------------------

def test_a_gmail_style_reply_keeps_only_what_the_sender_added():
    new, quoted = email_thread.split_quoted(
        "Confirmed for Thursday.\n\n"
        "On Mon, 27 Jul 2026 at 09:14, Aisha Kone <aisha.kone@example-bluepeak.test> wrote:\n\n"
        "> Can you confirm whether the April cohort date still holds?\n")
    assert new == "Confirmed for Thursday."
    assert "April cohort date" in quoted


def test_a_wrapped_attribution_line_is_still_a_boundary():
    # Long attributions wrap, putting `wrote:` on its own line. Matching only the single-line form
    # would let the whole quoted thread through as new text.
    new, quoted = email_thread.split_quoted(
        "Sounds good.\n\n"
        "On Mon, 27 Jul 2026 at 09:14, Programme Office\n"
        "<pmo@example-bluepeak.test> wrote:\n\n"
        "> The rollout dates are attached.\n")
    assert new == "Sounds good."
    assert "rollout dates" in quoted


def test_an_outlook_original_message_banner_is_a_boundary():
    new, quoted = email_thread.split_quoted(
        "Approved.\n\n-----Original Message-----\n"
        "From: Procurement Desk <procurement@example-bluepeak.test>\n"
        "Sent: Tuesday, 28 July 2026 15:40\n"
        "Subject: Renewal paperwork\n\nPlease send the order form.\n")
    assert new == "Approved."
    assert "order form" in quoted


def test_a_from_line_in_prose_is_not_a_quote_boundary():
    # `From:` opens a quoted header block only when more headers follow it. Treating every
    # `From:` as a boundary would silently discard the rest of an ordinary sentence.
    body = ("From: what I can tell, the April date still holds.\n"
            "I will confirm with the programme office on Thursday.")
    new, quoted = email_thread.split_quoted(body)
    assert new == body.strip()
    assert quoted == ""


def test_a_bare_forward_adds_nothing():
    new, quoted = email_thread.split_quoted(
        "---------- Forwarded message ---------\n"
        "From: Aisha Kone <aisha.kone@example-bluepeak.test>\n"
        "Date: Mon, 27 Jul 2026\n\n"
        "> I will send the comms plan by Friday.\n")
    assert new == "", "a forward with no covering note has no new material"
    assert "comms plan" in quoted


def test_subject_is_not_thread_identity():
    # Two unrelated messages can share "Re: Quick question". Subject normalization exists for
    # display; using it as identity would merge two conversations into one.
    assert email_thread.normalize_subject("Re: FW: Quick question") == "Quick question"
    a = email_thread.thread_key(message_id="a@example-bluepeak.test")
    b = email_thread.thread_key(message_id="b@example-bluepeak.test")
    assert a != b


def test_thread_key_prefers_the_references_root():
    # In-Reply-To alone chains each message to its parent, which splits one conversation into a
    # run of two-message threads. The References root is the id every message in the thread carries.
    key = email_thread.thread_key(
        message_id="d@example-bluepeak.test", in_reply_to="<c@example-bluepeak.test>",
        references="<a@example-bluepeak.test> <b@example-bluepeak.test> <c@example-bluepeak.test>")
    assert key == "a@example-bluepeak.test"
    assert email_thread.thread_key(message_id="b@example-bluepeak.test",
                                   in_reply_to="<a@example-bluepeak.test>") == "a@example-bluepeak.test"


# --- §14.8 threading and dedupe (ingested) ----------------------------------

def test_a_reply_threads_onto_its_parent(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/ingest/emails/sync")
    parent = _comm(c, a["id"], "fixture-001@example-bluepeak.test")
    reply = _comm(c, a["id"], "fixture-004@example-bluepeak.test")
    assert parent and reply
    assert reply["thread_id"] == parent["thread_id"] == parent["message_id"]
    assert reply["in_reply_to"] == "<fixture-001@example-bluepeak.test>"
    assert reply["quoted_chars"] > 0 and parent["quoted_chars"] == 0


def test_extraction_reads_only_what_the_reply_added(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/ingest/emails/sync")
    reply = _comm(c, a["id"], "fixture-004@example-bluepeak.test")
    assert reply["extraction_run_id"], "the reply's new sentence should have drafted a proposal"
    run = c.get(f"/api/extraction/runs/{reply['extraction_run_id']}").json()
    assert run["source_kind"] == "email"
    assert run["provider"] == "mock-inbox"
    assert run["external_id"] == "fixture-004@example-bluepeak.test"
    spans = " ".join(p["normalized"]["source"]["span"] or "" for p in run["proposals"])
    assert "comms plan by Friday" in spans
    assert "cohort date still holds" not in spans, "quoted history reached the extractor"
    assert "\\u" not in spans, "the source span was mangled by the adapter's decoding"


def test_the_quoted_parent_question_is_not_re_flagged(scene):
    c, a = scene["c"], scene["a"]
    c.post("/api/ingest/emails/sync")
    parent = _comm(c, a["id"], "fixture-001@example-bluepeak.test")
    reply = _comm(c, a["id"], "fixture-004@example-bluepeak.test")
    assert parent["needs_response"] == 1, "the question was flagged when it actually arrived"
    assert reply["needs_response"] == 0, \
        "the reply asks nothing; the '?' it carries belongs to quoted history"


def test_the_same_new_text_arriving_twice_in_a_thread_is_skipped(scene):
    # Somebody replies-all to their own message: a different Message-ID, the same contribution.
    # The external_id dedupe cannot see this one — only the thread + new-text hash can.
    c, a = scene["c"], scene["a"]
    c.post("/api/ingest/emails/sync")
    before = len(_proposals(c, a["id"]))
    from app import ingestion
    conn = c.app.state.conn
    row = ingestion.ingest_email_message(conn, {
        "external_id": "fixture-004-resend@example-bluepeak.test",
        "message_id": "fixture-004-resend@example-bluepeak.test",
        "in_reply_to": "<fixture-001@example-bluepeak.test>",
        "references": "<fixture-001@example-bluepeak.test>",
        "from_name": "Aisha Kone", "from_addr": "aisha.kone@example-bluepeak.test",
        "to_addrs": ["sam@valence.test"], "cc_addrs": [],
        "subject": "Re: Quick question on the April cohort date",
        "date_iso": "2026-07-28T09:00:00+00:00",
        "body": "One more thing before Thursday — I will send the updated comms plan by Friday.",
        "attachments": [], "fixture": None,
    })
    assert row is None, "the same contribution was ingested twice into one thread"
    assert len(_proposals(c, a["id"])) == before, "the resend re-proposed already-reviewed material"


def test_sync_is_idempotent_and_drafts_no_second_run(scene):
    c, a = scene["c"], scene["a"]
    first = c.post("/api/ingest/emails/sync").json()["result"]
    before = len(_proposals(c, a["id"]))
    again = c.post("/api/ingest/emails/sync").json()["result"]
    assert first["created"] >= 4 and again["created"] == 0
    assert again["extracted"] == 0
    assert len(_proposals(c, a["id"])) == before


def test_an_attachment_is_referenced_by_name_and_never_read(scene):
    c, a, p = scene["c"], scene["a"], scene["p"]
    c.post("/api/ingest/emails/sync")
    unresolved = c.get("/api/comms/unresolved").json()["comms"]
    pmo = next(m for m in unresolved if m["message_id"] == "fixture-005@example-bluepeak.test")
    assert pmo["attachments"] == "rollout-dates.csv"
    src = next(r for r in c.get("/api/source-references").json()
               if r["id"] == pmo["source_reference_id"])
    assert src["url"].endswith("005-unknown-sender-attachment.eml")
    assert src["locator"] == "fixture-005@example-bluepeak.test"
    assert "cohort,start_date" not in (pmo["summary"] or ""), "attachment bytes leaked into the record"


# --- §14.8 the association gate ---------------------------------------------

def test_an_unresolved_email_proposes_nothing(scene):
    c, a = scene["c"], scene["a"]
    res = c.post("/api/ingest/emails/sync").json()["result"]
    pmo = next(m for m in c.get("/api/comms/unresolved").json()["comms"]
               if m["message_id"] == "fixture-005@example-bluepeak.test")
    assert pmo["account_id"] is None and pmo["extraction_run_id"] is None
    # its new text carries a commitment cue — it is held back by the gate, not by having nothing
    assert "we will send the signed order form" in pmo["summary"] or res["created"] >= 4
    spans = " ".join(p["source"]["span"] or "" for p in _proposals(c, a["id"]))
    assert "signed order form" not in spans, \
        "an unplaced email proposed against an account it was never confirmed to belong to"


def test_confirming_the_association_releases_the_extraction(scene):
    c, a, p = scene["c"], scene["a"], scene["p"]
    c.post("/api/ingest/emails/sync")
    pmo = next(m for m in c.get("/api/comms/unresolved").json()["comms"]
               if m["message_id"] == "fixture-005@example-bluepeak.test")
    r = c.post(f"/api/comms/{pmo['id']}/associate",
               json={"account_id": a["id"], "program_id": p["id"]})
    assert r.status_code == 200, r.text
    confirmed = r.json()
    assert confirmed["extraction_run_id"], "confirming the account did not release the extractor"
    assert confirmed["association_confirmed_at"] and confirmed["association_confirmed_by"]
    spans = " ".join(pr["source"]["span"] or "" for pr in _proposals(c, a["id"]))
    assert "signed order form" in spans
    # ...and confirming twice does not draft the same material a second time
    before = len(_proposals(c, a["id"]))
    c.post(f"/api/comms/{pmo['id']}/associate", json={"account_id": a["id"], "program_id": p["id"]})
    assert len(_proposals(c, a["id"])) == before


def test_confirming_against_a_program_from_another_account_is_refused(scene):
    c, a = scene["c"], scene["a"]
    other = c.post("/api/accounts", json={"name": "Northgate"}).json()
    other_p = c.post("/api/programs", json={"account_id": other["id"], "name": "Pilot",
                                            "phase": "foundation"}).json()
    c.post("/api/ingest/emails/sync")
    pmo = next(m for m in c.get("/api/comms/unresolved").json()["comms"]
               if m["message_id"] == "fixture-005@example-bluepeak.test")
    r = c.post(f"/api/comms/{pmo['id']}/associate",
               json={"account_id": a["id"], "program_id": other_p["id"]})
    assert r.status_code == 422, "a program from another account was accepted as the placement"
    assert _comm(c, a["id"], "fixture-005@example-bluepeak.test") is None


# --- §14.5 / §14.7 review commands and placement ----------------------------

def _email_commitment(scene):
    """Sync, and return the drafted commitment proposal from the threaded reply."""
    c, a = scene["c"], scene["a"]
    c.post("/api/ingest/emails/sync")
    return next(p for p in _proposals(c, a["id"])
                if p["target_type"] == "commitment" and "comms plan" in (p["source"]["span"] or ""))


def test_an_email_proposal_is_not_work_until_it_is_accepted(scene):
    c, a, p = scene["c"], scene["a"], scene["p"]
    prop = _email_commitment(scene)
    assert prop["status"] == "proposed"
    board = c.get(f"/api/programs/{p['id']}/execution").json()
    assert sum(len(v) for v in board.values()) == 0, "an unaccepted proposal wrote a canonical record"
    path = c.get(f"/api/accounts/{a['id']}/execution-path").json()
    items = path["work"]["you_own"] + path["work"]["waiting_on_customer"]
    assert prop["id"] not in [i["source_id"] for i in items], \
        "an unaccepted proposal was ranked as execution work"
    assert "extraction_proposal" not in {i["source_type"] for i in items}
    assert (path["next_move"] or {}).get("source_id") != prop["id"], \
        "a proposal was offered as the next best move before anyone accepted it"


def test_accepting_an_email_proposal_creates_the_commitment_and_leaves_the_preview(scene):
    c, a, p, aisha, sam = scene["c"], scene["a"], scene["p"], scene["aisha"], scene["sam"]
    prop = _email_commitment(scene)
    r = c.post(f"/api/extraction/proposals/{prop['id']}/accept", json={"overrides": {
        "responsible_party_id": aisha["id"], "internal_owner_id": sam["id"],
        "due_date": "2026-07-31"}})
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["created_type"] == "commitment"
    assert "comms plan" in created["created"]["description"]
    assert created["created"]["program_id"] == p["id"]

    board = c.get(f"/api/programs/{p['id']}/execution").json()
    assert any(x["id"] == created["created"]["id"] for x in board["commitments"])
    # §14.7: once accepted it IS work — it lands in the path as the native record, not as a proposal
    path = c.get(f"/api/accounts/{a['id']}/execution-path", params={"program_id": p["id"]}).json()
    placed = [i for i in path["work"]["you_own"] + path["work"]["waiting_on_customer"]
              if i["source_id"] == created["created"]["id"]]
    assert placed, "the accepted commitment never entered the Account Path"
    assert placed[0]["source_type"] == "commitment"
    # it leaves the review queue ...
    assert prop["id"] not in [x["id"] for x in _proposals(c, a["id"])]
    # ... but the decision stays on the record
    review = c.get(f"/api/extraction/proposals/{prop['id']}/review").json()
    assert review["proposal"]["status"] == "accepted"
    assert review["proposal"]["resolved_target"]["id"] == created["created"]["id"]


def test_edit_and_accept_applies_the_edited_text_not_the_drafted_one(scene):
    c, a, aisha, sam = scene["c"], scene["a"], scene["aisha"], scene["sam"]
    prop = _email_commitment(scene)
    r = c.post(f"/api/extraction/proposals/{prop['id']}/accept", json={"overrides": {
        "description": "Aisha to send the updated comms plan", "responsible_party_id": aisha["id"],
        "internal_owner_id": sam["id"], "due_date": "2026-07-31"}})
    assert r.status_code == 200, r.text
    assert r.json()["created"]["description"] == "Aisha to send the updated comms plan"
    # the span still points at what the email actually said
    review = c.get(f"/api/extraction/proposals/{prop['id']}/review").json()
    assert "comms plan by Friday" in review["proposal"]["source"]["span"]


def test_rejecting_an_email_proposal_keeps_the_reason(scene):
    c, a = scene["c"], scene["a"]
    prop = _email_commitment(scene)
    r = c.post(f"/api/extraction/proposals/{prop['id']}/reject",
               json={"reason": "Already tracked on the existing comms task."})
    assert r.status_code == 200, r.text
    assert prop["id"] not in [x["id"] for x in _proposals(c, a["id"])]
    review = c.get(f"/api/extraction/proposals/{prop['id']}/review").json()
    assert review["proposal"]["status"] == "rejected"
    assert "Already tracked" in review["proposal"]["rejection_reason"]


def test_use_existing_closes_the_proposal_against_the_record_already_there(scene):
    c, a, p, aisha, sam = scene["c"], scene["a"], scene["p"], scene["aisha"], scene["sam"]
    existing = c.post("/api/commitments", json={
        "program_id": p["id"], "description": "Send the updated comms plan",
        "responsible_party_id": aisha["id"], "internal_owner_id": sam["id"],
        "due_date": "2026-07-31"}).json()
    prop = _email_commitment(scene)
    r = c.post(f"/api/extraction/proposals/{prop['id']}/resolve-existing",
               json={"target_type": "commitment", "target_id": existing["id"],
                     "note": "Same commitment, already on the board."})
    assert r.status_code == 200, r.text
    board = c.get(f"/api/programs/{p['id']}/execution").json()
    assert len(board["commitments"]) == 1, "use-existing created a second copy"
    review = c.get(f"/api/extraction/proposals/{prop['id']}/review").json()
    assert review["proposal"]["status"] == "resolved_existing"
    assert review["proposal"]["resolved_target"]["id"] == existing["id"]
