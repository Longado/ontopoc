import assert from "node:assert/strict";
import test from "node:test";

import { searchHits, searchIndex } from "./searchModel.js";

const run = (extra = {}) => ({
  file: { name: "orders.csv", kind: "table" },
  sources: [{ name: "orders", rows: 35 }, { name: "customers", rows: 26 }],
  ontology: {
    object_types: [
      { key: "order", label: "订单", populated_from: [{ source: "orders", identity: { id: "订单号" } }], attributes: [{ source: "orders", path: "金额" }, { source: "orders", path: "客户编号" }] },
      { key: "customer", label: "客户", populated_from: [{ source: "customers", identity: { id: "客户编号" } }], attributes: [{ source: "customers", path: "客户名称" }] },
    ],
    relations: [{ key: "r1", from: "order", to: "customer", label: "属于" }],
  },
  evaluation: {},
  ...extra,
});

test("objects, their fields, relations and tables can all be found, each leading to where it is shown", () => {
  const index = searchIndex(run(), null);
  const find = (q) => searchHits(index, q).map((h) => [h.kind, h.text, h.target]);
  assert.deepEqual(find("订单"), [
    ["object", "订单", { tab: "objects", object: "order" }],
    ["field", "订单号", { tab: "objects", object: "order", sub: "fields" }],
    ["relation", "订单 属于 客户", { tab: "graph", relation: "r1" }],
  ]);
  assert.deepEqual(find("customers"), [["table", "customers", { tab: "data", table: "customers" }]]);
});

test("a field found in two objects is listed once per object, and says which", () => {
  const hits = searchHits(searchIndex(run(), null), "客户编号").filter((h) => h.kind === "field");
  assert.deepEqual(hits.map((h) => [h.sub, h.target.object]), [["订单", "order"], ["客户 · 主键", "customer"]]);
});

test("a person's rename is searchable and shown, the key still finds it, and case does not matter", () => {
  const index = searchIndex(run(), { types: { customer: { label: "买家" } }, relations: {} });
  assert.deepEqual(searchHits(index, "买家").map((h) => h.text), ["买家", "订单 属于 买家"]);
  assert.deepEqual(searchHits(index, "CUSTOMER").filter((h) => h.kind === "object").map((h) => h.text), ["买家"]);
});

test("a document run has no tables to open, and an empty query finds nothing", () => {
  const index = searchIndex(run({ file: { name: "制度.md", kind: "document" } }), null);
  assert.equal(searchHits(index, "orders").filter((h) => h.kind === "table").length, 0);
  assert.deepEqual(searchHits(index, "  "), []);
});
