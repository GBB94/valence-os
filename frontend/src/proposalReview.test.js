import test from "node:test";
import assert from "node:assert/strict";

import {
  acceptAllBlocker, acceptAllState, changedFields, commandsFor, conflictNote, draftFrom,
  editableFields, isEdited, missingRequired, needsProgram, outcomeLine, overridesFrom, pairKey,
  sourceFacts, supersedeCandidates,
} from "./proposalReview.js";

function proposal(over = {}) {
  return {
    id: "p1", run_id: "r1", intent: "create", target_type: "task", status: "proposed",
    program_id: null,
    payload: { description: "Publish the rollout plan" },
    source: { kind: "transcript", span: "Action item: publish the rollout plan." },
    ...over,
  };
}

const commitment = () => proposal({
  id: "p2", target_type: "commitment",
  payload: { description: "Send the signed order form", due_date: "2026-08-14" },
});

function command(proposalObj, key, opts = {}) {
  return commandsFor(proposalObj, opts).find((c) => c.key === key);
}

// --- the pair, not the legacy enum -------------------------------------------------------------

test("the pair key reads intent and target separately", () => {
  assert.equal(pairKey(proposal({ intent: "update", target_type: "person" })), "update:person");
  assert.equal(pairKey(proposal()), "create:task");
});

test("an update to a person edits identity fields, never the drafted sentence", () => {
  const keys = editableFields(proposal({ intent: "update", target_type: "person" }))
    .map((f) => f.key);
  assert.deepEqual(keys, ["name", "title"]);
  assert.ok(!keys.includes("description"),
    "offering a description on a placeholder-fill invites an edit the server will refuse");
});

test("a create shows its required fields before the drafted sentence", () => {
  const keys = editableFields(commitment()).map((f) => f.key);
  assert.deepEqual(keys, ["responsible_party_id", "internal_owner_id", "due_date", "description"]);
});

// --- what applying it would write --------------------------------------------------------------

test("the draft starts from what the source said, not from a guess", () => {
  const draft = draftFrom(commitment());
  assert.equal(draft.description, "Send the signed order form");
  assert.equal(draft.due_date, "2026-08-14");
  assert.equal(draft.responsible_party_id, "", "nothing the source did not say is prefilled");
});

test("an empty optional field is omitted rather than sent as an empty value", () => {
  const p = proposal({ intent: "update", target_type: "person",
                       payload: { name: "Robin Vale", title: "Head of Enablement" } });
  const overrides = overridesFrom(p, { name: "Robin Vale", title: "" });
  assert.equal(overrides.name, "Robin Vale");
  assert.ok(!("title" in overrides),
    "an empty string is a value — sending one would erase the drafted title");
});

test("a program is attached only to the targets that are program-scoped", () => {
  assert.equal(needsProgram(proposal({ target_type: "person" })), false);
  assert.equal(needsProgram(proposal({ target_type: "task" })), true);
  assert.equal(overridesFrom(proposal(), { description: "x" }, { programId: "pg1" }).program_id,
    "pg1");
  assert.ok(!("program_id" in overridesFrom(
    proposal({ target_type: "person", intent: "update" }), { name: "n" }, { programId: "pg1" })));
});

// --- accept vs edit-and-accept -----------------------------------------------------------------

test("accepting an untouched draft is labelled as drafted", () => {
  const p = proposal();
  const c = command(p, "accept", { programId: "pg1", draft: draftFrom(p) });
  assert.equal(c.label, "Accept as drafted");
  assert.equal(c.enabled, true);
});

test("changing the drafted text renames the command so it cannot be applied unnoticed", () => {
  const p = proposal();
  const keys = commandsFor(p, { programId: "pg1", draft: { description: "Something else" } })
    .map((c) => c.key);
  assert.ok(keys.includes("edit_and_accept"));
  assert.ok(!keys.includes("accept"));
  assert.equal(isEdited(p, { description: "Publish the rollout plan" }), false);
});

// --- a command is offered only when it can succeed ----------------------------------------------

test("a missing required field disables accept and names the field", () => {
  const p = commitment();
  const c = command(p, "accept", { programId: "pg1", draft: draftFrom(p) });
  assert.equal(c.enabled, false);
  assert.match(c.why, /Responsible party/);
  assert.deepEqual(missingRequired(p, draftFrom(p)),
    ["Responsible party", "Internal owner"]);
});

test("a program-scoped proposal with no program says so instead of failing at the server", () => {
  const p = proposal();
  const c = command(p, "accept", { programId: "", draft: draftFrom(p) });
  assert.equal(c.enabled, false);
  assert.match(c.why, /program/i);
});

test("a stale target stops acceptance rather than overwriting the newer edit", () => {
  const p = proposal();
  const conflict = { stale: true, fields: [{ field: "description", current: "b", proposed: "a", changed: true }] };
  const c = command(p, "accept", { programId: "pg1", draft: draftFrom(p), conflict });
  assert.equal(c.enabled, false);
  assert.match(c.why, /changed/i);
});

test("every command is unavailable while one is in flight, so a double-press writes once", () => {
  const p = proposal();
  const cmds = commandsFor(p, { programId: "pg1", draft: draftFrom(p), pending: true });
  for (const c of cmds) {
    if (c.key === "open_source") continue;
    assert.equal(c.enabled, false, `${c.key} stayed live during a request`);
  }
});

test("a resolved proposal offers nothing but its source", () => {
  const p = proposal({ status: "accepted" });
  for (const c of commandsFor(p, { programId: "pg1", draft: draftFrom(p) })) {
    if (c.key === "open_source") { assert.equal(c.enabled, true); continue; }
    assert.equal(c.enabled, false);
    assert.match(c.why, /Already accepted/);
  }
});

test("the source is always openable — a reviewer who cannot read it cannot review", () => {
  assert.equal(command(proposal({ status: "rejected" }), "open_source", {}).enabled, true);
});

// --- reject, use existing, supersede -------------------------------------------------------------

test("rejecting needs a reason, because the reason is the only record of the disagreement", () => {
  const p = proposal();
  assert.equal(command(p, "reject", { rejectReason: "" }).enabled, false);
  assert.equal(command(p, "reject", { rejectReason: "no" }).enabled, false);
  assert.equal(command(p, "reject", { rejectReason: "Already handled offline" }).enabled, true);
});

test("use existing waits for a chosen record and never preselects one", () => {
  const p = proposal();
  assert.equal(command(p, "use_existing", {}).enabled, false);
  assert.equal(command(p, "use_existing", { chosenExistingId: "t9" }).enabled, true);
});

test("supersede only offers open proposals over the same target type", () => {
  const p = proposal();
  const siblings = supersedeCandidates(p, [
    p,
    proposal({ id: "p3", target_type: "task", status: "proposed" }),
    proposal({ id: "p4", target_type: "task", status: "accepted" }),
    proposal({ id: "p5", target_type: "risk", status: "proposed" }),
  ]);
  assert.deepEqual(siblings.map((s) => s.id), ["p3"],
    "superseding across target types would close a task against a risk");
  assert.equal(command(p, "supersede", { siblings, supersedeById: "p3" }).enabled, true);
  assert.match(command(p, "supersede", { siblings: [] }).why, /No other proposal/);
});

// --- what the reviewer is told ------------------------------------------------------------------

test("the conflict note names the fields that moved, and says nothing when none did", () => {
  assert.equal(conflictNote(null), null);
  assert.equal(conflictNote({ stale: false, fields: [] }), null);
  const note = conflictNote({
    stale: true,
    fields: [{ field: "due_date", changed: true }, { field: "description", changed: false }],
  });
  assert.match(note, /due_date/);
  assert.ok(!note.includes("description"), "an unchanged field is not a conflict");
  assert.match(conflictNote({ stale: true, missing: true }), /no longer exists/);
  assert.equal(changedFields({ fields: [{ changed: false }] }).length, 0);
});

test("the source facts are the record's own values and omit what the record does not have", () => {
  const p = proposal({ source: { kind: "email", external_id: "m-1@example.test",
                                 content_hash: "abc123", span: "…", locator: null } });
  const labels = sourceFacts(p, { kind: "email", provider: "mock-inbox" }).map((f) => f.label);
  assert.deepEqual(labels, ["Kind", "Provider", "Message / reference", "Content hash"]);
  assert.ok(!labels.includes("Locator"), "a null locator is left out rather than shown as empty");
});

test("a resolved proposal says what happened, not what could happen", () => {
  assert.equal(outcomeLine(proposal()), null);
  assert.match(outcomeLine(proposal({ status: "accepted", resolved_target: { type: "task" } })),
    /Applied/);
  assert.match(
    outcomeLine(proposal({ status: "resolved_existing", resolved_target: { type: "commitment" } })),
    /already held this/);
  assert.match(outcomeLine(proposal({ status: "rejected", rejection_reason: "Handled offline" })),
    /Handled offline/);
  assert.match(outcomeLine(proposal({ status: "superseded" })), /Superseded/);
});

// --- run-scoped accept-all — ACCOUNT-INTAKE-SPEC.md §11.4 ----------------------------------------

test("accept-all offers itself only when every open draft could be applied untouched", () => {
  const clean = [proposal(), proposal({ id: "p2" })];
  const state = acceptAllState(clean, { programId: "prog-1" });
  assert.equal(state.enabled, true);
  assert.equal(state.count, 2);
  assert.equal(state.label, "Accept all 2");
  assert.equal(state.why, null);
  assert.deepEqual(state.blocked, []);
});

test("one draft that needs a decision disables the batch and the reason says how many", () => {
  // The count matters: "3 of these 5" tells the reviewer whether they are about to do two minutes of
  // work or twenty. A bare "some of these" would be true and useless.
  const state = acceptAllState([
    proposal(),
    proposal({ id: "p2", match_candidates: [{ id: "t-9", label: "Publish the rollout plan" }] }),
    proposal({ id: "p3" }),
  ], { programId: "prog-1" });
  assert.equal(state.enabled, false);
  assert.match(state.why, /^1 of these 3 needs a decision of its own/);
  assert.deepEqual(state.blocked.map((b) => b.id), ["p2"]);
  assert.match(state.blocked[0].why, /may already hold this/);
});

test("a resolved sibling is out of scope, not a permanent block", () => {
  // Reading §11.4's "every item proposed" over *every* item rather than every *open* item would
  // disable accept-all forever after a single rejection — a rule that punishes reviewing.
  const state = acceptAllState([
    proposal({ id: "p1", status: "rejected", rejection_reason: "Handled offline" }),
    proposal({ id: "p2" }),
    proposal({ id: "p3", status: "accepted" }),
  ], { programId: "prog-1" });
  assert.equal(state.count, 1, "only the open one is counted");
  assert.equal(state.enabled, true);
  assert.equal(state.label, "Accept all 1");
});

test("an empty or working list says which it is instead of just being dead", () => {
  const none = acceptAllState([], { programId: "prog-1" });
  assert.equal(none.enabled, false);
  assert.equal(none.count, 0);
  assert.equal(none.label, "Accept all");
  assert.match(none.why, /Nothing open/);

  const working = acceptAllState([proposal()], { programId: "prog-1", pending: true });
  assert.equal(working.enabled, false);
  assert.match(working.why, /Working/);
});

test("the client's blockers mirror the server's dry run, one reason each", () => {
  assert.equal(acceptAllBlocker(proposal(), "prog-1"), null);
  assert.match(acceptAllBlocker(proposal({ status: "accepted" })), /already accepted/);
  assert.match(
    acceptAllBlocker(proposal({ conflict: { stale: true } }), "prog-1"),
    /changed after this was drafted/);
  assert.match(
    acceptAllBlocker(proposal({ match_candidates: [{ id: "t-9" }] }), "prog-1"),
    /may already hold this/);
  // A commitment with no owners cannot be created from the draft alone, whatever else is true.
  assert.match(acceptAllBlocker(commitment(), "prog-1"), /it needs /);
});

test("a proposal needing a program is blocked without one and cleared by the group's program", () => {
  const p = proposal();
  assert.equal(needsProgram(p), true);
  assert.match(acceptAllBlocker(p, null), /it needs a program/);
  assert.equal(acceptAllBlocker(p, "prog-1"), null);
  // A program carried on the proposal itself is just as good — the batch does not require the
  // account workspace to have one selected.
  assert.equal(acceptAllBlocker(proposal({ program_id: "prog-2" }), null), null);
});
