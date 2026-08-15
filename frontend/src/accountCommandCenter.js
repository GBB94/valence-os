export const COMMAND_CENTER_LENSES = ["operate", "prepare", "leadership"];
export const DEFAULT_COMMAND_CENTER_LENS = "operate";

const LENS_STORAGE_KEY = "valence-command-center:lens:v1";
const VISIT_STORAGE_PREFIX = "valence-command-center:last-visit:v1";

export function isCommandCenterLens(value) {
  return COMMAND_CENTER_LENSES.includes(value);
}

export function readPreferredLens(storage) {
  try {
    const value = storage?.getItem(LENS_STORAGE_KEY);
    return isCommandCenterLens(value) ? value : DEFAULT_COMMAND_CENTER_LENS;
  } catch {
    return DEFAULT_COMMAND_CENTER_LENS;
  }
}

export function writePreferredLens(storage, lens) {
  if (!isCommandCenterLens(lens)) return false;
  try {
    storage?.setItem(LENS_STORAGE_KEY, lens);
    return true;
  } catch {
    return false;
  }
}

export function resolveCommandCenterLens(requestedLens, storage) {
  return isCommandCenterLens(requestedLens) ? requestedLens : readPreferredLens(storage);
}

export function lastVisitStorageKey(accountId, programId) {
  const scope = programId ? `program:${programId}` : "account";
  return `${VISIT_STORAGE_PREFIX}:${accountId}:${scope}`;
}

function isIsoTimestamp(value) {
  return typeof value === "string" && value.includes("T") && Number.isFinite(Date.parse(value));
}

export function readLastVisit(storage, accountId, programId) {
  if (!accountId) return null;
  try {
    const value = storage?.getItem(lastVisitStorageKey(accountId, programId));
    return isIsoTimestamp(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeLastVisit(storage, accountId, programId, serverTimestamp) {
  if (!accountId || !isIsoTimestamp(serverTimestamp)) return false;
  try {
    storage?.setItem(lastVisitStorageKey(accountId, programId), serverTimestamp);
    return true;
  } catch {
    return false;
  }
}
