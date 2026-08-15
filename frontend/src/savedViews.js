const MAX_CUSTOM_VIEWS = 30;

export function savedViewStorageKey(surface) {
  return `valence-saved-views:${surface}`;
}

export function readCustomViews(storage, surface) {
  try {
    const parsed = JSON.parse(storage.getItem(savedViewStorageKey(surface)) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((view) => view &&
      typeof view.id === "string" && /^custom-[a-z0-9]+$/.test(view.id) &&
      typeof view.label === "string" && view.label.trim().length > 0 && view.label.length <= 80 &&
      view.state && typeof view.state === "object" && !Array.isArray(view.state)
    ).slice(-MAX_CUSTOM_VIEWS);
  } catch {
    return [];
  }
}

export function writeCustomViews(storage, surface, views) {
  try {
    storage.setItem(savedViewStorageKey(surface), JSON.stringify(views.slice(-MAX_CUSTOM_VIEWS)));
    return true;
  } catch {
    return false;
  }
}

export function resolveSavedView(builtIns, customViews, requestedId, defaultId) {
  const all = [...builtIns, ...customViews];
  return all.find((view) => view.id === requestedId) || all.find((view) => view.id === defaultId) || all[0];
}

export function createCustomView(label, state, now = Date.now()) {
  return {
    id: `custom-${now.toString(36)}`,
    label: label.trim().slice(0, 80),
    state: JSON.parse(JSON.stringify(state)),
  };
}

export function sameViewState(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}
