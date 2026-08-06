export function nextTabKey(tabs, currentKey, key) {
  const keys = tabs.map(([tabKey]) => tabKey);
  if (!keys.length) return null;
  const current = Math.max(0, keys.indexOf(currentKey));
  if (key === "Home") return keys[0];
  if (key === "End") return keys[keys.length - 1];
  if (key === "ArrowRight") return keys[(current + 1) % keys.length];
  if (key === "ArrowLeft") return keys[(current - 1 + keys.length) % keys.length];
  return null;
}
