import assert from "node:assert/strict";
import test from "node:test";

import { edgeStats, findingsByType, layoutGraph } from "./ontologyGraphModel.js";

const t = (key, label) => ({ key, label, populated_from: [], attributes: [] });
const r = (key, from, to) => ({ key, from, to, source: "s", meaning: "m" });
const ontology = {
  object_types: [t("customer", "客户"), t("order", "订单"), t("product", "产品"), t("ticket", "售后工单"), t("employee", "员工")],
  relations: [r("order_customer", "order", "customer"), r("order_product", "order", "product"), r("ticket_order", "ticket", "order")],
};

test("types flow left to right along relations; unrelated types still get a place", () => {
  const g = layoutGraph(ontology);
  const x = Object.fromEntries(g.nodes.map((n) => [n.key, n.x]));
  assert.ok(x.ticket < x.order && x.order < x.customer);
  assert.equal(x.customer, x.product);
  assert.equal(g.nodes.length, 5);
  assert.ok(g.nodes.some((n) => n.key === "employee"));
  assert.equal(g.edges.length, 3);
});

test("nodes never overlap and everything fits the drawing", () => {
  const g = layoutGraph(ontology);
  for (const a of g.nodes) {
    assert.ok(a.x >= 0 && a.y >= 0 && a.x + a.w <= g.width && a.y + a.h <= g.height);
    for (const b of g.nodes) {
      if (a === b) continue;
      const apart = a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y;
      assert.ok(apart, `${a.key} overlaps ${b.key}`);
    }
  }
});

test("a cycle does not hang the layout", () => {
  const g = layoutGraph({ object_types: [t("a", "A"), t("b", "B")], relations: [r("ab", "a", "b"), r("ba", "b", "a")] });
  assert.equal(g.nodes.length, 2);
  assert.equal(g.edges.length, 2);
});

test("data-check findings are counted on the type they belong to", () => {
  const fit = {
    identity_conflicts: [{ type: "customer" }], identity_spellings: [{ type: "customer" }], suspected_duplicates: [{ type: "product" }],
    missing_across_sources: [{ type: "customer", count: 2 }], orphans: [{ type: "order", count: 3 }, { type: "customer", count: 0 }],
    relations: [{ key: "order_customer", rows: 10, linked_rows: 10 }, { key: "ticket_order", rows: 5, linked_rows: 4 }],
  };
  const by = findingsByType(fit);
  assert.deepEqual(by.customer.map((f) => f.kind), ["identity_conflict", "identity_spelling", "missing_reference"]);
  assert.deepEqual(by.product.map((f) => f.kind), ["suspected_duplicate"]);
  assert.deepEqual(by.order.map((f) => f.kind), ["orphans"]);
  assert.equal(by.employee, undefined);
  assert.deepEqual(edgeStats(fit, "ticket_order"), { rows: 5, linked_rows: 4, complete: false });
  assert.deepEqual(edgeStats(fit, "order_customer"), { rows: 10, linked_rows: 10, complete: true });
  assert.equal(edgeStats(null, "x"), null);
});
