import { useCallback, useEffect, useMemo, useState } from "react";
import { createCustomView, readCustomViews, resolveSavedView, sameViewState, writeCustomViews } from "./savedViews";

export function useSavedViews({ surface, builtIns, defaultId, requestedId, onActivate, normalizeState = (state) => state }) {
  const [customViews, setCustomViews] = useState(() => readCustomViews(window.localStorage, surface));
  const views = useMemo(() => [...builtIns, ...customViews], [builtIns, customViews]);
  const resolved = resolveSavedView(builtIns, customViews, requestedId || defaultId, defaultId);
  const resolvedState = normalizeState(resolved.state);
  const [state, setState] = useState(() => resolvedState);

  useEffect(() => {
    const next = resolveSavedView(builtIns, customViews, requestedId || defaultId, defaultId);
    setState(normalizeState(next.state));
    if (requestedId && next.id !== requestedId) onActivate(defaultId, { replace: true });
  }, [builtIns, customViews, defaultId, normalizeState, onActivate, requestedId]);

  const activate = useCallback((id) => {
    const next = resolveSavedView(builtIns, customViews, id, defaultId);
    setState(normalizeState(next.state));
    onActivate(next.id);
  }, [builtIns, customViews, defaultId, normalizeState, onActivate]);

  const save = useCallback((label) => {
    const created = createCustomView(label, state);
    const next = [...customViews, created];
    if (!writeCustomViews(window.localStorage, surface, next)) return null;
    setCustomViews(next);
    onActivate(created.id);
    return created;
  }, [customViews, onActivate, state, surface]);

  const remove = useCallback((id) => {
    const next = customViews.filter((view) => view.id !== id);
    if (!writeCustomViews(window.localStorage, surface, next)) return false;
    setCustomViews(next);
    setState(normalizeState(resolveSavedView(builtIns, next, defaultId, defaultId).state));
    onActivate(defaultId);
    return true;
  }, [builtIns, customViews, defaultId, normalizeState, onActivate, surface]);

  return {
    views,
    activeId: resolved.id,
    state,
    setState,
    activate,
    save,
    remove,
    modified: !sameViewState(state, resolvedState),
    canDelete: resolved.id.startsWith("custom-"),
  };
}
