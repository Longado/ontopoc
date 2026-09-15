import assert from "node:assert/strict";
import test from "node:test";

import { conflictGroups } from "./ontologyStudioModel.js";

test("conflicts are summed by object and field, the largest first", () => {
  const c = (type, identity, field) => ({ type, identity, field, source: "t", values: ["1", "2"] });
  const fit = { identity_conflicts: [c("line", "A", "Quantity"), c("product", "P1", "Description"), c("line", "B", "Quantity"), c("line", "B", "Price")] };
  assert.deepEqual(conflictGroups(fit), [{ type: "line", field: "Quantity", count: 2 }, { type: "product", field: "Description", count: 1 }, { type: "line", field: "Price", count: 1 }]);
});
