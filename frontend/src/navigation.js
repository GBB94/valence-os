import { isCommandCenterLens } from "./accountCommandCenter.js";

export const WORKSPACE_TABS = [
  ["overview", "Overview"],
  ["ledger", "Ledger"],
  ["people", "People"],
  ["plan", "Plan"],
  ["commercial", "Commercial"],
  ["evidence", "Evidence"],
  ["outputs", "Outputs"],
  ["internal", "Internal"],
];

const WORKSPACE_TAB_KEYS = new Set(WORKSPACE_TABS.map(([key]) => key));
const GLOBAL_DESTINATIONS = new Set(["today", "accounts", "library", "operations"]);
export const COMMERCIAL_SECTIONS = [
  "whitespace", "ledger", "funding", "signals", "company", "growth", "pipeline",
];
const COMMERCIAL_SECTION_KEYS = new Set(COMMERCIAL_SECTIONS);
export const PEOPLE_SECTIONS = ["map", "champions", "influence", "exec", "changes", "messaging"];

// `section` is one nav field shared by the tabs that have sub-views, and each tab owns its own
// keys. Validating per tab rather than against a merged set is what stops a Commercial section
// surviving a hop to People — the URL would round-trip a value that tab cannot render.
const SECTION_KEYS = { commercial: COMMERCIAL_SECTION_KEYS, people: new Set(PEOPLE_SECTIONS) };

function sectionFor(tab, value) {
  return SECTION_KEYS[tab]?.has(value) ? value : undefined;
}

function cleanSegment(value) {
  if (!value) return "";
  try { return decodeURIComponent(value); } catch { return ""; }
}

function cleanPreference(value) {
  return typeof value === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(value) ? value : undefined;
}

export function parseNavigation(locationLike) {
  const pathname = locationLike?.pathname || "/";
  const search = new URLSearchParams(locationLike?.search || "");
  const segments = pathname.split("/").filter(Boolean).map(cleanSegment);

  if (segments.length === 0) return { dest: "today" };
  const [first, accountId, rawTab] = segments;

  if (first === "accounts" && accountId && segments.length <= 3) {
    const tab = WORKSPACE_TAB_KEYS.has(rawTab) ? rawTab : "overview";
    const programId = cleanPreference(search.get("program"));
    const lens = tab === "overview" && isCommandCenterLens(search.get("lens"))
      ? search.get("lens") : undefined;
    const meetingId = lens === "prepare" ? cleanPreference(search.get("meeting")) : undefined;
    const section = sectionFor(tab, search.get("section"));
    const recordId = section === "company" ? cleanPreference(search.get("record")) : undefined;
    return {
      dest: "account", accountId, tab,
      ...(programId ? { programId } : {}),
      ...(lens ? { lens } : {}),
      ...(meetingId ? { meetingId } : {}),
      ...(section ? { section } : {}),
      ...(recordId ? { recordId } : {}),
    };
  }

  if (GLOBAL_DESTINATIONS.has(first) && segments.length === 1) {
    const view = (first === "today" || first === "accounts") ? cleanPreference(search.get("view")) : undefined;
    return { dest: first, ...(view ? { view } : {}) };
  }

  return { dest: "today" };
}

export function navigationUrl(nav) {
  if (!nav || nav.dest === "today") {
    const search = nav?.view ? `?view=${encodeURIComponent(nav.view)}` : "";
    return `/today${search}`;
  }
  if (nav.dest === "accounts") {
    const search = nav.view ? `?view=${encodeURIComponent(nav.view)}` : "";
    return `/accounts${search}`;
  }
  if (nav.dest === "library") return "/library";
  if (nav.dest === "operations") return "/operations";
  if (nav.dest === "account" && nav.accountId) {
    const tab = WORKSPACE_TAB_KEYS.has(nav.tab) ? nav.tab : "overview";
    const params = new URLSearchParams();
    if (nav.programId) params.set("program", nav.programId);
    const lens = tab === "overview" && isCommandCenterLens(nav.lens) ? nav.lens : undefined;
    if (lens) params.set("lens", lens);
    if (lens === "prepare" && cleanPreference(nav.meetingId)) params.set("meeting", nav.meetingId);
    const section = sectionFor(tab, nav.section);
    if (section) params.set("section", section);
    if (section === "company" && cleanPreference(nav.recordId)) params.set("record", nav.recordId);
    const search = params.size ? `?${params}` : "";
    return `/accounts/${encodeURIComponent(nav.accountId)}/${tab}${search}`;
  }
  return "/today";
}

export function sameNavigation(a, b) {
  return navigationUrl(a) === navigationUrl(b);
}
