import assert from "node:assert/strict";
import test from "node:test";

import { conflictGroups } from "./ontologyStudioModel.js";

test("conflicts are summed by object and field, the largest first", () => {
  const c = (type, identity, field) => ({ type, identity, field, source: "t", values: ["1", "2"] });
  const fit = { identity_conflicts: [c("line", "A", "Quantity"), c("product", "P1", "Description"), c("line", "B", "Quantity"), c("line", "B", "Price")] };
  assert.deepEqual(conflictGroups(fit), [{ type: "line", field: "Quantity", count: 2 }, { type: "product", field: "Description", count: 1 }, { type: "line", field: "Price", count: 1 }]);
});

test("the data check says how many conflicts a person settled by keeping the latest row", async () => {
  const { conflictCount } = await import("./ontologyStudioModel.js");
  const fit = { identity_conflicts: [{ type: "customer", field: "城市", identity: "KH012", settled: "keep_latest" }, { type: "customer", field: "城市", identity: "KH013" }] };
  assert.equal(conflictCount(fit), "2，其中 1 个已按只留最新处理");
  assert.equal(conflictCount({ identity_conflicts: [fit.identity_conflicts[1]] }), "1");
  assert.deepEqual(conflictGroups(fit), [{ type: "customer", field: "城市", count: 2, settled: 1 }]);
  assert.deepEqual(conflictGroups({ identity_conflicts: [fit.identity_conflicts[1]] }), [{ type: "customer", field: "城市", count: 1 }]);
});
