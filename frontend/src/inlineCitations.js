/**
 * Inline citation chips for copilot prose (VISIBILITY-SPEC §7.1).
 *
 * The generator already writes the packet id into the answer body — `copilot_model` emits
 * `- {claim text} [p003]` — so today an operator reads a raw `[p003]` mid-sentence and has to go
 * find it in the claims block below. This module turns that existing token into the chip, and that
 * is the whole design: **it introduces no new mapping.** The chip cannot cite anything the claims
 * block does not, because the only ids it will render are the ones the claims block links to.
 *
 * A bracket the claims block does not cite stays **literal text**. That case is a validation
 * failure upstream (an uncited clause fails validation, unchanged by this slice), and dressing it up
 * as a working citation would hide the failure behind the affordance that is supposed to expose it.
 *
 * The chip spends no colour — shape plus a number — per the no-state-by-colour-alone rule.
 *
 * Not applied to `shared_plan`'s artifact, despite §7.1 naming it. That generator carries no
 * claim→source links and no packet ids; its provenance is a per-row `source` label that is already
 * rendered. Building the chip there would mean inventing the mapping this module exists to avoid.
 */

// `copilot_context` stamps `p001`, `p002`, … onto packet items. The pattern is deliberately exact:
// a looser one would start turning ordinary bracketed prose into citations.
const CITATION = /\[(p\d{3})\]/g;

/** The packet ids the claims block actually cites. Nothing outside this set becomes a chip. */
export function citedPacketIds(run) {
  const ids = new Set();
  for (const claim of (run || {}).claims || []) {
    for (const link of claim.sources || []) {
      if (link && link.packet_id) ids.add(link.packet_id);
    }
  }
  return ids;
}

/** The chip's label: the packet's own number, so a chip reading 3 opens a drawer titled `p003`. */
export function citationNumber(packetId) {
  const digits = /(\d+)$/.exec(packetId || "");
  return digits ? String(Number(digits[1])) : String(packetId || "");
}

/**
 * One line of answer prose, split into text runs and citation chips.
 *
 * Returns a flat list of `{kind: "text", text}` and `{kind: "cite", packetId, number}`. Text is
 * never dropped: concatenating every `text` plus the original bracket for every `cite` reproduces
 * the input exactly, which is what keeps this a presentation change rather than an edit.
 */
export function citationRuns(text, cited) {
  const source = typeof text === "string" ? text : "";
  const allowed = cited instanceof Set ? cited : new Set();
  const runs = [];
  let cursor = 0;
  CITATION.lastIndex = 0;
  let match = CITATION.exec(source);
  while (match) {
    const packetId = match[1];
    if (allowed.has(packetId)) {
      if (match.index > cursor) runs.push({ kind: "text", text: source.slice(cursor, match.index) });
      runs.push({ kind: "cite", packetId, number: citationNumber(packetId) });
      cursor = match.index + match[0].length;
    }
    // An id the claims block does not cite is left inside the text run, brackets and all.
    match = CITATION.exec(source);
  }
  if (cursor < source.length) runs.push({ kind: "text", text: source.slice(cursor) });
  return runs;
}

/** The frozen snapshot a chip opens, or null if the run does not carry it. */
export function sourceForPacket(run, packetId) {
  return ((run || {}).sources || []).find((source) => source.packet_id === packetId) || null;
}
