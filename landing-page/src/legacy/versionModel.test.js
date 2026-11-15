import assert from "node:assert/strict";
import test from "node:test";

import { earlierVersionOf, versionRows } from "./versionModel.js";

const runs = [
  { saved_as: "b.json", file: "orders.csv、customers.csv", status: "auto_built_verified" },
  { saved_as: "a.json", file: "orders.csv、customers.csv", status: "auto_built_verified" },
  { saved_as: "c.json", file: "orders.csv", status: "blocked" },
];

test("files named like a kept run's are offered as its next version, pointing at its latest verified run", () => {
  assert.deepEqual(earlierVersionOf(runs, [{ name: "customers.csv" }, { name: "orders.csv" }]), { saved_as: "b.json", file: "orders.csv、customers.csv" });
  assert.equal(earlierVersionOf(runs, [{ name: "orders.csv" }]), null);   // only a run that did not verify has that name
  assert.equal(earlierVersionOf(runs, [{ name: "other.csv" }]), null);
  assert.equal(earlierVersionOf("offline", [{ name: "orders.csv" }]), null);
});

test("each object's change is drawn from its counts, and an unchanged one says so", () => {
  const rows = versionRows({ objects: [{ label: "合同", before: 3000, after: 2990, added: 1, removed: 11 }, { label: "部门", before: 30, after: 30, added: 0, removed: 0 }] });
  assert.deepEqual(rows.map((r) => [r.label, r.before, r.after, r.changed]), [["合同", 3000, 2990, true], ["部门", 30, 30, false]]);
  assert.equal(rows[0].scale, 3000);   // both bars share one scale: the largest count on the page
});
