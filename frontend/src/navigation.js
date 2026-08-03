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
    return { dest: "account", accountId, tab, ...(programId ? { programId } : {}) };
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
    const search = nav.programId ? `?program=${encodeURIComponent(nav.programId)}` : "";
    return `/accounts/${encodeURIComponent(nav.accountId)}/${tab}${search}`;
  }
  return "/today";
}

export function sameNavigation(a, b) {
  return navigationUrl(a) === navigationUrl(b);
}
