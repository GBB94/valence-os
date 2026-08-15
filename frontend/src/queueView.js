export function accountFilterOptions(items = []) {
  return [...new Map(items
    .filter((item) => item.account_id && item.account_name)
    .map((item) => [item.account_id, item.account_name])).entries()]
    .sort((a, b) => a[1].localeCompare(b[1]));
}
