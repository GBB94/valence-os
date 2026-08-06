"""The account drop zone pipeline — ACCOUNT-INTAKE-SPEC.md §6.

A dropped document drafts; the operator accepts. That is the whole shape, and everything awkward
about this module follows from it being a *drafting* path rather than a writing one.

Six steps, each of which can fail and say so:

    1  receive    one item, in the account whose page it was dropped on (§8)
    2  screen     size cap + extension refusal          → outcome=rejected_kind
    3  detect      deterministic kind routing (§7.1)    → falls back to notes, never fails
    4  segment     kind-specific parse *from bytes*     → outcome=parse_failed
                   (decoding happens HERE, per kind, not before — §6)
    5  extract     new text only, the existing extractor → outcome=no_proposals
    6  persist     one extraction_run + proposals, via routers.ai._persist_run
    7  report      what was drafted, what was not, what was skipped (§14)

**Decoding is inside step 4, and the ordering is the point.** An earlier draft of this pipeline
decoded everything to UTF-8 up front and parsed afterwards, which is exactly the defect
`adapters._parse_eml`'s own comment warns about: a MIME part declares its own charset, and a
str-parsed message falls back to `raw-unicode-escape`, rewriting a real em dash as the six literal
characters of its escape sequence — straight into a proposal description and its span. A citation
is only worth having if it is byte-accurate to what the source said. Text kinds decode as UTF-8,
which is the right answer for them; `.eml` never reaches `decode_text` at all and decodes per MIME
part with the charset that part declares (§4.1, §7.3).

**No new proposal store, no new acceptance path.** Step 6 calls the same `_persist_run` a transcript
extraction calls. A drop is one more `source_kind`. Nothing in this module accepts, rejects, edits,
resolves, or supersedes anything — that happens in `ProposalReview`, which is the one place a
drafted proposal becomes a decision.

**And no second email path.** A dropped `.eml` does not persist its own run either: `_process_eml`
hands the parsed message to `ingestion.ingest_email_message`, the same call the mock inbox sync
makes, so it produces the same `comm_message`, thread identity, and run a synced copy would (§7.4).
Divergence there would not surface as an error — it would surface as a comms timeline and a set of
relationship-health counts that are quietly incomplete.

**Untrusted text reaches nothing that decides.** Routing never reads the model (§7.1); scope never
reads the text (§8); the extractor call is the existing constrained one with a strict schema and
validated output. A drop can only ever produce a proposal, and the proposal vocabulary contains no
verb that does anything outside this account's review queue.
"""
from __future__ import annotations

import json
import sqlite3

from . import adapters, audit, email_thread, extractor, ingestion, intake_kind, repo
from .db import new_id, now_utc
from .proposals import content_hash

# --- §4.1 limits, stated before anyone can hit them --------------------------------------------

MAX_BYTES = 1_000_000          # ~a 200-page transcript
MAX_ITEMS_PER_DROP = 10

# §6.6. A run's source-version key names who supplied the material, because two providers can hand
# back the same Message-ID and mean different material. A dropped `.eml` came off the operator's own
# machine, so it must not claim `mock-inbox` provenance even though it takes the same ingestion path.
PROVIDER = "account_drop"

# Text kinds, plus `.eml` since Slice 2. `.eml` is the one accepted kind that is *not* held to the
# UTF-8 gate below: a valid message declares its own charset per MIME part, and refusing it for not
# being UTF-8 at the door would turn away real mail while blaming the file (§4.1).
ACCEPTED_EXTENSIONS = (".txt", ".md", ".markdown", ".vtt", ".srt", ".text", ".log", ".eml")

# §4.2. Every refusal names the reason and offers the working path. A refusal that says
# "unsupported file type" teaches the operator the product is limited; the truth is that one
# boundary is closed (`CONNECTIONS.md` → `file_storage`) and there is a four-second alternative.
_REFUSALS = {
    ".pdf": ("PDF isn't accepted yet. Reading a PDF means keeping the file itself, and file storage "
             "is an unopened connection. Open it and paste the text — the drop takes pasted text in full."),
    ".doc": ("Word documents aren't accepted yet, for the same reason as PDF: reading one means "
             "keeping the file. Copy the text and paste it instead."),
    # `.msg` used to share `.eml`'s refusal. It no longer can: `.eml` is accepted, and the two are
    # not variants of one format — `.msg` is a Microsoft compound binary, not RFC-822, so nothing
    # here can read it. Saying "email files aren't read" would now be false as well as unhelpful.
    ".msg": ("Outlook `.msg` files are a binary format, not the RFC-822 message a `.eml` is, and "
             "nothing here can read one. In Outlook, save the message as `.eml` and drop that — or "
             "paste the text."),
    ".zip": ("Archives aren't accepted. Drop the individual documents, or paste their text."),
}
for _alias, _target in ((".docx", ".doc"), (".pptx", ".doc"), (".xlsx", ".doc")):
    _REFUSALS[_alias] = _REFUSALS[_target]
for _image in (".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp", ".tiff"):
    _REFUSALS[_image] = ("Images aren't read. There is no OCR here and adding one would mean holding "
                         "the file and running a parser over untrusted binary. Type or paste what it says.")
for _av in (".mp3", ".m4a", ".wav", ".mp4", ".mov", ".webm", ".aac"):
    _REFUSALS[_av] = ("Audio and video aren't transcribed here — transcription is an unopened "
                      "connection. Paste the transcript if you have one.")

_GENERIC_REFUSAL = ("Only text can be dropped here: notes, a pasted email thread, or a transcript. "
                    "Open the file and paste its text.")
_TOO_BIG = ("That's larger than the {cap} limit. A 1 MB text file is about a 200-page transcript, so "
            "this is almost certainly not text — paste the part that matters instead.")
_NOT_TEXT = ("That file isn't readable as text — it decoded as binary. Only text can be dropped "
             "here; open it and paste what it says.")
_ALL_QUOTED = ("Every line of that is quoted history from earlier in the thread. Nothing was drafted, "
               "because everything in it has already been read once.")
_NOTHING_FOUND = ("Nothing in that was clear enough to draft. It is kept here with its text, so you "
                  "can read it back or drop a fuller version.")
# --- §7.2 / §7.4, the `.eml` sentences ---------------------------------------------------------
_NOT_A_MESSAGE = ("That has an `.eml` name but no sender in it, so it cannot be read as a message or "
                  "recorded as correspondence. If it came from a mail client, try saving it again; "
                  "if it is really a text file, rename it or paste the text.")
_HTML_ONLY = ("That message has no plain-text part — it is HTML only. Reading the markup would mean "
              "running a tag stripper over untrusted input, which is not something this does. Open "
              "it and paste the text.")
_EMPTY_MESSAGE = ("That message has headers but no body text. Its details are on the correspondence "
                  "record; there was nothing to draft from.")
_ALREADY_HERE = ("That message is already in this account's correspondence — it arrived by sync, or "
                 "it was dropped before. Nothing was drafted a second time.")
_ALREADY_ELSEWHERE = ("That message is already recorded on a different account, so it was not added "
                      "here and nothing was drafted. If this is the wrong place for it, delete this "
                      "drop; if the other record is wrong, correct it there.")
_WHOLE_THREAD_REFUSED = ("Read the whole thread is not applied to an .eml. Its quoted history is made "
                         "of messages that carry their own ids, so each one is either already in the "
                         "correspondence record or will be when it syncs — reading them again here "
                         "would draft the same commitments twice.")
# --- §12, the duplicate sentence ---------------------------------------------------------------
# It names the date and the drop it matched, because silent dedupe is indistinguishable from a
# failed upload: the operator dropped a file, saw nothing appear, and has no way to tell which
# happened. The earlier receipt is the answer to "then where did it go".
_ALREADY_DROPPED = ("Identical to a drop on {date}{name}. Nothing new was drafted — the proposals "
                    "from that drop are where this material already is.")


def limits() -> dict:
    """One server-side source for the idle zone's copy, the accepted kinds, and the caps.

    A UI that hard-coded the accepted extensions would drift the day a kind is added, and would
    state a limit the server does not enforce.
    """
    return {
        "max_bytes": MAX_BYTES,
        "max_bytes_label": "1 MB",
        "max_items_per_drop": MAX_ITEMS_PER_DROP,
        "accepted_extensions": list(ACCEPTED_EXTENSIONS),
        "accepted_summary": ("Email threads, transcripts, or notes — pasted, or as .eml, .txt, .md, "
                             ".vtt, .srt."),
        "paste_is_first_class": True,
        # The trust statement. It is what makes the first drop safe to try, and it is not optional.
        "assurance": "Nothing is saved to your trackers until you say so.",
        "refusals": dict(sorted(_REFUSALS.items())),
        "generic_refusal": _GENERIC_REFUSAL,
    }


def extension_of(filename: str | None) -> str:
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    return name[dot:] if dot > 0 else ""


def screen(raw: bytes, filename: str | None) -> str | None:
    """Step 2. Returns a refusal sentence, or None to continue.

    The size cap is checked on bytes before anything else so a stray video fails on the fast path
    rather than after a decode attempt.
    """
    if len(raw) > MAX_BYTES:
        return _TOO_BIG.format(cap="1 MB")
    if not raw.strip():
        return "That was empty — there was nothing to read."
    ext = extension_of(filename)
    if not ext:
        return None                                   # a paste, or a file with no extension
    if ext in _REFUSALS:
        return _REFUSALS[ext]
    if ext not in ACCEPTED_EXTENSIONS:
        return _GENERIC_REFUSAL
    return None


def decode_text(raw: bytes) -> str:
    """Step 4's decode, for the **text** kinds — not for `.eml`.

    Strict UTF-8 with a BOM strip. Deliberately not `errors="replace"`: a document that silently
    became a page of replacement characters would be quoted verbatim into a proposal span, and a
    citation nobody can read is worse than a refusal that says "this isn't text".

    §4.1 is explicit that this gate is per-kind and not global. An `.eml` never comes through here:
    it declares its own charset per MIME part, so holding it to UTF-8 at the door would refuse real
    mail while claiming the file was malformed. `_process_eml` decodes each part with what that
    part says it is.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8")


def _hash_bytes(raw: bytes) -> str:
    """Content hash over the exact bytes, whatever encoding they were in.

    `latin-1` is not a claim about the encoding — it is the one codec that maps every byte to a
    distinct character, so the hash is injective over byte strings. The obvious alternative,
    `utf-8` with `errors="replace"`, collapses every undecodable byte to the same character, which
    would make two different non-UTF-8 messages hash identically and report the second as a
    duplicate of the first. That is a live case precisely here, where non-UTF-8 bytes arrive.
    """
    return content_hash(raw.decode("latin-1"))


# --- §14 coverage --------------------------------------------------------------------------------

def _coverage(*, read_chars, skipped, other_accounts, whole_thread):
    """What the drop did not do.

    Modelled on `ACCOUNT-PATH-SPEC.md`'s `coverage.omitted_sources` and D-160: a response the server
    calls complete can still be subtractive, and a subtractive response always says so.

    Every entry pairs a machine reason code with an operator-readable sentence authored **here**,
    on the server. The client never composes a coverage sentence — the same rule as
    `sharedPlan.withheldSentence` (D-153), for the same reason: a view that composes any part of an
    "I did not do this" statement is a view that can soften one.
    """
    return {
        "read_chars": read_chars,
        "skipped": skipped,
        # Reserved and honestly empty in Slice 1. Populating it would need entity recognition we do
        # not have, and inventing "2 people named" from nothing would be a coverage claim about
        # material we never identified.
        "named_not_proposed": [],
        "refused": [],
        "other_accounts_mentioned": other_accounts,
        "read_whole_thread": whole_thread,
    }


def _skip_entry(reason, chars, note):
    return {"reason": reason, "chars": chars, "note": note}


def _other_accounts(conn, account_id: str, text: str) -> list[str]:
    """§8 rule 3: a document that names another account does not move.

    The mention is reported and changes nothing. Re-scoping is the operator deleting the drop and
    dropping it in the right place — a source that could redirect itself into another client's
    review queue is the injection payload writing itself, and there is no version of automatic
    re-scoping that is safe here.
    """
    lowered = (text or "").lower()
    names = []
    for row in conn.execute(
            "SELECT name FROM accounts WHERE id <> ? AND COALESCE(archived,0)=0", (account_id,)):
        name = (row["name"] or "").strip()
        # Short names produce false positives against ordinary prose; a mention we are not sure of
        # is worse than one we do not report, because the notice is meant to be trusted.
        if len(name) >= 5 and name.lower() in lowered:
            names.append(name)
    return sorted(names)


# --- §12 duplicate detection ---------------------------------------------------------------------

# Which earlier outcomes count as "this was already read". Deliberately not `rejected_kind` or
# `parse_failed`: re-dropping the PDF should reproduce "PDF isn't accepted yet, paste the text",
# which is the sentence that tells the operator what to do. Answering "you dropped this before"
# instead would be true, useless, and would hide the working path behind a second attempt.
_DUPLICABLE_OUTCOMES = ("drafted", "no_proposals", "duplicate")


def prior_drop(conn: sqlite3.Connection, account_id: str, hash_: str) -> sqlite3.Row | None:
    """The earliest live drop in **this account** made from exactly these bytes, or None.

    Three choices worth naming:

    - **Account-scoped, always.** The same deck can legitimately go to two clients, and D-225's rule
      holds regardless: a receipt in this account must never hold a handle on another account's
      record. A cross-account match would either link there or describe it, and both leak.
    - **Earliest, not latest**, so the chain never grows. Drop the same file four times and all
      three duplicates point at the original rather than at each other, which is what makes
      `duplicate_of_id` a pointer to the answer instead of a linked list to walk.
    - **Live only.** An archived drop has been withdrawn; re-dropping the material should draft it
      again rather than be turned away by a receipt the operator can no longer see.
    """
    return conn.execute(
        "SELECT id, created_at, filename, detected_kind, outcome, comm_message_id FROM intake_drops "
        f"WHERE account_id=? AND content_hash=? AND outcome IN ({','.join('?' * len(_DUPLICABLE_OUTCOMES))}) "
        # `rowid`, not `id`, as the tie-break. Timestamps are second-resolution, so two drops in the
        # same second are routine, and ids are random hex — ordering by one would pick an arbitrary
        # member of that second and the "earliest" guarantee that keeps the chain flat would not
        # hold. `rowid` is insertion order, which is the thing actually being asked for.
        "AND COALESCE(archived,0)=0 ORDER BY created_at ASC, rowid ASC LIMIT 1",
        (account_id, hash_, *_DUPLICABLE_OUTCOMES)).fetchone()


def _already_dropped_reason(prior: sqlite3.Row) -> str:
    name = f" ({prior['filename']})" if prior["filename"] else ""
    return _ALREADY_DROPPED.format(date=(prior["created_at"] or "")[:10], name=name)


# --- the pipeline --------------------------------------------------------------------------------

def process_drop(conn: sqlite3.Connection, *, account_id: str, raw: bytes,
                 filename: str | None = None, program_id: str | None = None,
                 read_whole_thread: bool = False, backend: str | None = None,
                 actor: str = audit.DEFAULT_ACTOR) -> dict:
    """Run one dropped item end to end and return its receipt.

    `account_id` is the route parameter (§8). It is never read from the text, and there is no
    association step and no confidence gate on scope: a drop happened inside an account, chosen by
    a human, one second ago.
    """
    repo.get_row(conn, "accounts", account_id)
    if program_id:
        program = repo.get_row(conn, "programs", program_id)
        if program["account_id"] != account_id:
            raise ValueError("that program belongs to a different account")

    hash_ = _hash_bytes(raw)

    refusal = screen(raw, filename)
    if refusal:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind="notes", raw=raw, hash_=hash_, snapshot=None, outcome="rejected_kind",
                       reason=refusal, actor=actor)

    # §12. Checked after the refusal and before any parse, which is the only ordering that works in
    # both directions: a refused kind must keep giving its own reason rather than being answered
    # "you dropped this before", and everything past this point — decode, segment, extract, ingest —
    # is work whose entire output would be a second copy of records that already exist.
    #
    # The kind and any correspondence record are taken from the earlier drop rather than re-derived.
    # Identical bytes detect to an identical kind and are the same message, so this is a read of a
    # fact rather than a guess — and claiming `notes` here because we skipped detection would put a
    # wrong word on the receipt. The earlier drop's *run* is deliberately not carried: this receipt
    # must not report "Drafted 6 updates" a second time, which is the double-count §12 exists to
    # stop. `duplicate_of.extraction_run_id` is the pointer to those drafts instead.
    #
    # This runs ahead of `.eml`'s message-identity dedupe rather than replacing it. The two catch
    # different things: identical bytes here, and the same Message-ID arriving in a *different* file
    # or by sync there, which this check cannot see.
    prior = prior_drop(conn, account_id, hash_)
    if prior is not None:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind=prior["detected_kind"], raw=raw, hash_=hash_, snapshot=None,
                       outcome="duplicate", reason=_already_dropped_reason(prior),
                       comm_message_id=prior["comm_message_id"], duplicate_of_id=prior["id"],
                       actor=actor)

    # §7.3. `.eml` routes on the extension *before* any decode, because that is the whole reason
    # step 4 owns decoding: the message declares its own charset per part, and flattening it to
    # UTF-8 here would be the mangled-em-dash defect `adapters.parse_eml_bytes` warns about,
    # straight into a proposal span.
    if extension_of(filename) == ".eml":
        return _process_eml(conn, account_id=account_id, program_id=program_id, filename=filename,
                            raw=raw, hash_=hash_, read_whole_thread=read_whole_thread,
                            backend=backend, actor=actor)

    try:
        text = decode_text(raw)
    except UnicodeDecodeError:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind="notes", raw=raw, hash_=hash_, snapshot=None, outcome="parse_failed",
                       reason=_NOT_TEXT, actor=actor)

    kind = intake_kind.detect_kind(text, filename)
    # A pasted thread arrives with the newest message's own header block still attached, because
    # nothing stripped an envelope off it. `split_quoted` reads a leading `From:` as the start of
    # quoted history, so the block has to come off first or the whole paste is classified as
    # history and nothing is read. It is scaffolding, not content, and it gets its own reason
    # below rather than inflating the quoted-history count.
    headers = ""
    if kind == "email_paste":
        headers, text_to_read = intake_kind.strip_leading_headers(text)
    else:
        text_to_read = text

    if read_whole_thread:
        new_text, set_aside = intake_kind.read_whole_thread(text_to_read)
    else:
        new_text, set_aside = intake_kind.segment(text_to_read, kind)

    skipped = []
    if headers:
        skipped.append(_skip_entry(
            "message_headers", len(headers),
            "The message header block was not read as content."))
    if kind == "email_paste" and set_aside:
        skipped.append(_skip_entry(
            "quoted_history", len(set_aside),
            "Quoted history below this message was not read — it was drafted from once already."))
    if kind == "transcript" and set_aside:
        skipped.append(_skip_entry(
            "cue_scaffolding", len(set_aside),
            "Cue numbers and timecodes were removed before reading; what was said is intact."))
    # §7.4. Stating it is the honest option: inventing a message id would corrupt the thread graph,
    # and staying silent would make the comms timeline quietly incomplete.
    if kind == "email_paste":
        skipped.append(_skip_entry(
            "no_message_id", 0,
            "Pasted text has no message id, so this is not added to the correspondence record."))

    other_accounts = _other_accounts(conn, account_id, text)
    coverage = _coverage(read_chars=len(new_text), skipped=skipped, other_accounts=other_accounts,
                         whole_thread=bool(read_whole_thread))

    if not new_text.strip():
        reason = _ALL_QUOTED if kind == "email_paste" else "There was no readable text in that."
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind=kind, raw=raw, hash_=hash_, snapshot=text, outcome="no_proposals",
                       reason=reason, new_chars=0, quoted_chars=len(set_aside), actor=actor)

    try:
        ex = extractor.get_extractor(backend)
        proposals = ex.extract(new_text)
    except ValueError as e:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind=kind, raw=raw, hash_=hash_, snapshot=text, outcome="parse_failed",
                       reason=f"The extractor rejected that: {e}", new_chars=len(new_text),
                       quoted_chars=len(set_aside), actor=actor)
    except RuntimeError as e:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind=kind, raw=raw, hash_=hash_, snapshot=text, outcome="parse_failed",
                       reason=str(e), new_chars=len(new_text), quoted_chars=len(set_aside),
                       actor=actor)

    if not proposals:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind=kind, raw=raw, hash_=hash_, snapshot=text, outcome="no_proposals",
                       reason=_NOTHING_FOUND, new_chars=len(new_text), quoted_chars=len(set_aside),
                       coverage=coverage, actor=actor)

    from .routers.ai import _persist_run          # local: the router imports this module's siblings
    run_id = _persist_run(
        conn, account_id=account_id, program_id=program_id, interaction_id=None,
        model_version=ex.model_version, prompt_version=ex.prompt_version, source_text=new_text,
        proposals=proposals, extractor_backend=(backend or extractor.configured_backend()),
        source_kind="document", provider=PROVIDER, external_id=None, coverage=coverage)

    return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                   kind=kind, raw=raw, hash_=hash_, snapshot=text, outcome="drafted",
                   reason=None, new_chars=len(new_text), quoted_chars=len(set_aside),
                   run_id=run_id, coverage=coverage, actor=actor)


def _process_eml(conn, *, account_id, program_id, filename, raw, hash_, read_whole_thread,
                 backend, actor) -> dict:
    """Step 4 for `.eml` — ACCOUNT-INTAKE-SPEC.md §7.3 and §7.4.

    **This function drafts nothing itself.** It parses the message and hands it to
    `ingestion.ingest_email_message`, which is the same call the mock inbox sync makes. That is the
    entire point of the slice: a dropped message must produce the same records a synced one does —
    a `source_reference`, a `comm_message` carrying message and thread identity and `new_text_hash`,
    and only then an extraction run over the new text. A drop that skipped to extraction would
    never appear in the account's comms timeline, and because relationship-health signals are counts
    over our own correspondence, it would be silently missing from reciprocity and response-time
    figures that are supposed to describe all of it. That failure does not surface as an error; it
    surfaces as numbers that are quietly wrong.

    So the outcome here is *reported from* what ingestion did, never computed alongside it:

        None returned          → the message is already recorded → `duplicate`
        row with a run         → `drafted`
        row without a run      → `no_proposals`, with the reason naming which no

    **`Read the whole thread` is refused, not ignored.** It is right for a paste, where there is no
    message identity and a forwarded thread may genuinely be all new. An `.eml`'s quoted history is
    made of messages that each carry their own id, so re-reading it is the duplicate-proposal storm
    §14.8 exists to prevent — and unlike a paste, we can say that with certainty. A refusal that
    changed behaviour silently would be the worse half of that call, so it lands in
    `coverage.refused` with its own sentence.
    """
    msg = adapters.parse_eml_bytes(raw, filename or "dropped message")
    body = msg["body"]
    # A sender is the one header this path cannot do without, and the check has to be here rather
    # than left to the parser: `message_from_bytes` never fails: hand it a plain text file and it
    # returns a message with no headers whose body is the whole file. Without this, renaming
    # `notes.txt` to `notes.eml` would mint a `comm_message` with an empty `from_addr` and
    # `direction: inbound` — a correspondence record with nobody on the other end of it, quietly
    # skewing the reciprocity and response-time counts that are the reason §7.4 exists at all.
    if not msg["from_addr"]:
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind="email_file", raw=raw, hash_=hash_, snapshot=None,
                       outcome="parse_failed", reason=_NOT_A_MESSAGE, actor=actor)

    new_text, quoted = email_thread.split_quoted(body)

    skipped = []
    if quoted:
        skipped.append(_skip_entry(
            "quoted_history", len(quoted),
            "Quoted history below this message was not read — it was drafted from once already."))
    if msg["attachments"]:
        skipped.append(_skip_entry(
            "attachments", 0,
            f"{len(msg['attachments'])} attachment(s) are named on the correspondence record but "
            "not read — nothing here opens a file."))

    coverage = _coverage(read_chars=len(new_text), skipped=skipped,
                         other_accounts=_other_accounts(conn, account_id, body), whole_thread=False)
    if read_whole_thread:
        coverage["refused"].append({"what": "Read the whole thread", "why": _WHOLE_THREAD_REFUSED})

    row = ingestion.ingest_email_message(conn, msg, ingestion.DropOrigin(
        account_id=account_id, program_id=program_id, provider=PROVIDER,
        source_label=f"Email (dropped): {msg.get('subject') or '(no subject)'}",
        extractor_backend=backend, coverage=coverage))

    if row is None:
        existing = conn.execute(
            "SELECT id, account_id FROM comm_messages WHERE external_id=?",
            (msg["external_id"],)).fetchone()
        # A message already recorded on *another* account is reported without being linked to. §8
        # rule 3's discipline: a receipt in this account must not hold a handle on another client's
        # record, and re-scoping is the operator's act, never ours.
        here = bool(existing) and existing["account_id"] == account_id
        return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                       kind="email_file", raw=raw, hash_=hash_, snapshot=body or None,
                       outcome="duplicate", reason=_ALREADY_HERE if here else _ALREADY_ELSEWHERE,
                       new_chars=len(new_text), quoted_chars=len(quoted),
                       comm_message_id=existing["id"] if here else None, actor=actor)

    run_id = row.get("extraction_run_id")
    if run_id:
        reason, outcome = None, "drafted"
    elif msg["body_source"] == "html_only":
        reason, outcome = _HTML_ONLY, "no_proposals"
    elif not new_text.strip():
        reason, outcome = (_ALL_QUOTED if quoted else _EMPTY_MESSAGE), "no_proposals"
    else:
        reason, outcome = _NOTHING_FOUND, "no_proposals"

    return _record(conn, account_id=account_id, program_id=program_id, filename=filename,
                   kind="email_file", raw=raw, hash_=hash_, snapshot=body or None, outcome=outcome,
                   reason=reason, new_chars=len(new_text), quoted_chars=len(quoted), run_id=run_id,
                   comm_message_id=row["id"], coverage=coverage, actor=actor)


def _record(conn, *, account_id, program_id, filename, kind, raw, hash_, snapshot, outcome, reason,
            new_chars=None, quoted_chars=None, run_id=None, comm_message_id=None,
            duplicate_of_id=None, coverage=None, actor):
    """Write the drop row and return its receipt.

    A refused drop is recorded, not discarded. A file that vanished with a toast is a file the
    operator has no way to reason about afterwards, and the refusal reason is exactly the thing
    worth keeping.

    A §12 duplicate is written with `snapshot=None` on purpose. The text is already on the drop this
    one points at, and a second copy would be a second thing to find and delete under §5 — a
    snapshot deletion that left an identical copy one row above it would not be a deletion.
    """
    ts = now_utc()
    drop_id = new_id()
    with conn:
        conn.execute(
            "INSERT INTO intake_drops (id, account_id, program_id, filename, detected_kind, "
            "byte_length, content_hash, snapshot_text, new_text_chars, quoted_chars, outcome, "
            "outcome_reason, extraction_run_id, comm_message_id, duplicate_of_id, created_at, "
            "created_by, updated_at, archived) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
            (drop_id, account_id, program_id, filename, kind, len(raw), hash_, snapshot,
             new_chars, quoted_chars, outcome, reason, run_id, comm_message_id, duplicate_of_id,
             ts, actor, ts))
        audit.record(conn, object_type="intake_drop", object_id=drop_id, action="create",
                     after={"outcome": outcome, "kind": kind, "filename": filename,
                            "bytes": len(raw), "run_id": run_id,
                            "comm_message_id": comm_message_id,
                            "duplicate_of_id": duplicate_of_id})
    return read_drop(conn, drop_id, coverage=coverage)


# --- read model ------------------------------------------------------------------------------

def read_drop(conn: sqlite3.Connection, drop_id: str, coverage: dict | None = None) -> dict:
    """One receipt (§11.1). It is an outcome line and a link — it resolves nothing.

    Proposal counts are read from `extraction_proposals` on every request rather than stored: a
    count that was frozen at drop time would keep advertising work the operator has already done.
    Coverage is read from `extraction_runs.coverage_json`, which is the one place it lives.
    """
    row = repo.get_row(conn, "intake_drops", drop_id)
    run_id = row["extraction_run_id"]
    drafted = pending = 0
    if run_id:
        counts = conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status='proposed' THEN 1 ELSE 0 END) AS pending "
            "FROM extraction_proposals WHERE run_id=?", (run_id,)).fetchone()
        drafted = counts["total"] or 0
        pending = counts["pending"] or 0
        if coverage is None:
            raw = conn.execute("SELECT coverage_json FROM extraction_runs WHERE id=?",
                               (run_id,)).fetchone()
            if raw and raw["coverage_json"]:
                coverage = json.loads(raw["coverage_json"])
    row["proposals_drafted"] = drafted
    row["proposals_pending"] = pending
    row["coverage"] = coverage
    row["snapshot_present"] = row["snapshot_text"] is not None
    # §12. The pointer is resolved into a small block rather than left as a bare id, because the
    # receipt's job is to answer "then where did it go" in one line. Read live, so a duplicate whose
    # original was archived stops advertising a receipt the operator can no longer open.
    row["duplicate_of"] = None
    if row["duplicate_of_id"]:
        prior = conn.execute(
            "SELECT id, created_at, filename, detected_kind, outcome, extraction_run_id "
            "FROM intake_drops WHERE id=? AND COALESCE(archived,0)=0",
            (row["duplicate_of_id"],)).fetchone()
        if prior:
            row["duplicate_of"] = {
                "id": prior["id"], "created_at": prior["created_at"],
                "filename": prior["filename"], "detected_kind": prior["detected_kind"],
                "outcome": prior["outcome"], "extraction_run_id": prior["extraction_run_id"],
            }
    return row


def list_drops(conn: sqlite3.Connection, account_id: str, limit: int = 20) -> list[dict]:
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM intake_drops WHERE account_id=? AND COALESCE(archived,0)=0 "
        "ORDER BY created_at DESC, id DESC LIMIT ?", (account_id, limit))]
    return [read_drop(conn, drop_id) for drop_id in ids]


def delete_snapshot(conn: sqlite3.Connection, drop_id: str, actor: str = audit.DEFAULT_ACTOR) -> dict:
    """§5. Nulls the text and keeps everything else — the drop, its hash, its run, and every
    proposal drawn from it. The citations survive as quoted spans even when their source is gone.

    Deleting is an operator act with an audit row. There is no automatic expiry, because a timer
    that silently destroyed the evidence behind a live proposal would be worse than keeping it.
    """
    row = repo.get_row(conn, "intake_drops", drop_id)
    if row["snapshot_text"] is None:
        return read_drop(conn, drop_id)
    ts = now_utc()
    with conn:
        conn.execute("UPDATE intake_drops SET snapshot_text=NULL, snapshot_deleted_at=?, "
                     "snapshot_deleted_by=? WHERE id=?", (ts, actor, drop_id))
        # `update` rather than a new action verb: the audit CHECK is a small closed vocabulary on
        # purpose, and deleting the snapshot is a field going to NULL on a row that survives.
        audit.record(conn, object_type="intake_drop", object_id=drop_id, action="update",
                     before={"snapshot_chars": len(row["snapshot_text"] or "")},
                     after={"snapshot_text": None, "reason": "operator deleted the source text"})
    return read_drop(conn, drop_id)
