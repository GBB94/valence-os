/** Pure helpers for the private Call Coach UI. */

export function extractSpeakers(text) {
  const found = [];
  const seen = new Set();
  for (const line of String(text || "").split(/\r?\n/)) {
    const match = line.trim().match(/^(?:\[[^\]]{1,24}\]\s*)?([^:\n]{1,60}):\s*.+$/);
    const speaker = match?.[1]?.trim();
    if (speaker && !seen.has(speaker)) { seen.add(speaker); found.push(speaker); }
  }
  return found;
}

export function sourceKindForFile(filename) {
  const extension = String(filename || "").toLowerCase().split(".").pop();
  return ["txt", "md", "vtt", "srt"].includes(extension) ? extension : null;
}

export function coachingSessionPath(id) {
  return `/coach/sessions/${encodeURIComponent(id)}`;
}

export const LENS_LABELS = Object.freeze({
  advanced_evidence: "Advanced evidence",
  clarified: "Clarified in the call",
  missed_opportunity: "Worth asking next time",
  not_relevant: "Not needed for this call",
  unable_to_assess: "Unable to assess",
});

export function sourceParts(source, observation) {
  if (!source || !observation) return { before: "", quote: "", after: "" };
  const start = observation.source_start;
  const end = observation.source_end;
  if (!Number.isInteger(start) || !Number.isInteger(end) || source.slice(start, end) !== observation.source_span) {
    return { before: source, quote: "", after: "" };
  }
  const windowStart = Math.max(0, start - 420);
  const windowEnd = Math.min(source.length, end + 420);
  return {
    before: source.slice(windowStart, start), quote: source.slice(start, end),
    after: source.slice(end, windowEnd),
  };
}
