import test from "node:test";
import assert from "node:assert/strict";

import {
  citationNumber, citationRuns, citedPacketIds, sourceForPacket,
} from "./inlineCitations.js";

const RUN = {
  claims: [
    { claim_text: "Renewal is in November.", sources: [{ packet_id: "p001" }, { packet_id: "p003" }] },
    { claim_text: "Two champions are named.", sources: [{ packet_id: "p003" }] },
  ],
  sources: [
    { packet_id: "p001", record_kind: "account", snapshot_json: "{}" },
    { packet_id: "p003", record_kind: "interaction", snapshot_json: "{}" },
  ],
};

/** The rebuilt string: text runs verbatim, chips back to the bracket form they came from. */
function rejoin(runs) {
  return runs.map((run) => (run.kind === "text" ? run.text : `[${run.packetId}]`)).join("");
}

test("the cited ids come from the claim links, not from the prose", () => {
  // The whole point of §7.1: the chip renders an id the claims block already carries. Scanning the
  // answer text for brackets instead would let a generated string mint its own citation.
  assert.deepEqual([...citedPacketIds(RUN)].sort(), ["p001", "p003"]);
  assert.deepEqual([...citedPacketIds(null)], []);
  assert.deepEqual([...citedPacketIds({ claims: [{ claim_text: "no links" }] })], []);
});

test("a cited bracket becomes a chip and an uncited one stays literal text", () => {
  const runs = citationRuns("Renewal is in November [p001], per the last call [p002].",
    citedPacketIds(RUN));
  assert.deepEqual(runs.map((run) => run.kind), ["text", "cite", "text"]);
  assert.equal(runs[1].packetId, "p001");
  // p002 is not linked by any claim, so it is still sitting in the trailing text run, brackets and
  // all. An uncited clause is a validation failure upstream; dressing it as a citation hides it.
  assert.equal(runs[2].text.includes("[p002]"), true);
});

test("concatenating the runs reproduces the input exactly", () => {
  const cited = citedPacketIds(RUN);
  for (const line of [
    "Renewal is in November [p001], per the last call [p002].",
    "[p003] leads the sentence.",
    "It ends with the source [p003]",
    "[p001][p003] back to back",
    "No citation at all.",
    "",
  ]) {
    assert.equal(rejoin(citationRuns(line, cited)), line, line);
  }
});

test("nothing becomes a chip when the run cites nothing", () => {
  const runs = citationRuns("Renewal is in November [p001].", new Set());
  assert.deepEqual(runs, [{ kind: "text", text: "Renewal is in November [p001]." }]);
  // Same for a caller that passes no set at all — the draft preview does exactly this.
  assert.deepEqual(citationRuns("Renewal [p001].", undefined),
    [{ kind: "text", text: "Renewal [p001]." }]);
});

test("only the exact packet form is matched", () => {
  // A looser pattern would start converting ordinary bracketed prose into citations.
  const cited = new Set(["p001", "p1", "p0001"]);
  for (const line of ["[p1]", "[p0001]", "[P001]", "[p001", "p001]", "[see p001]"]) {
    assert.deepEqual(citationRuns(line, cited), [{ kind: "text", text: line }], line);
  }
});

test("the chip's number is the packet's own number", () => {
  assert.equal(citationNumber("p003"), "3");
  assert.equal(citationNumber("p012"), "12");
  assert.equal(citationNumber("p001"), "1");
  // Nothing to derive from: show the id rather than inventing an ordinal that means nothing.
  assert.equal(citationNumber("packet"), "packet");
  assert.equal(citationNumber(null), "");
});

test("a chip resolves to the snapshot the run carries, or to nothing", () => {
  assert.equal(sourceForPacket(RUN, "p003").record_kind, "interaction");
  // Cited but not carried: the chip must not fabricate a drawer.
  assert.equal(sourceForPacket(RUN, "p009"), null);
  assert.equal(sourceForPacket(null, "p001"), null);
});

test("the module spends no colour and asserts no state", () => {
  // §7.1 is presentation over an existing token. A tone, status, or severity here would be this
  // module deciding something about the claim, which is the validator's job and not the chip's.
  const source = citationRuns("A [p001] B", citedPacketIds(RUN));
  for (const run of source) {
    assert.deepEqual(Object.keys(run).sort(),
      run.kind === "cite" ? ["kind", "number", "packetId"] : ["kind", "text"]);
  }
});

test("repeated calls do not leak regex state between lines", () => {
  // The pattern is a module-level /g regex; a forgotten lastIndex reset would silently drop the
  // first citation on every other line.
  const cited = citedPacketIds(RUN);
  for (let i = 0; i < 3; i += 1) {
    const runs = citationRuns("Leading [p001] citation.", cited);
    assert.equal(runs.filter((run) => run.kind === "cite").length, 1, `pass ${i}`);
  }
});
