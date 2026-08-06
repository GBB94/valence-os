import test from "node:test";
import assert from "node:assert/strict";
import { accountFilterOptions } from "./queueView.js";

test("account filter options ignore portfolio-level attention", () => {
  assert.deepEqual(accountFilterOptions([
    { account_id: "account-z", account_name: "Zeta" },
    { account_id: null, account_name: null },
    { account_id: "account-a", account_name: "Alpha" },
    { account_id: "account-a", account_name: "Alpha" },
  ]), [
    ["account-a", "Alpha"],
    ["account-z", "Zeta"],
  ]);
});
