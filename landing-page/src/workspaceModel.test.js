import assert from "node:assert/strict";
import test from "node:test";

import { objectCards, objectRelations, sectionOfTile, sectionsFor } from "./workspaceModel.js";

const run = (extra = {}) => ({
  file: { name: "orders.csv", kind: "table" },
  ontology: {
    object_types: [
      { key: "order", label: "订单", definition: "一次购买", populated_from: [{ source: "orders", identity: { id: "订单号" } }], attributes: [{ source: "orders", path: "金额" }] },
      { key: "customer", label: "客户", populated_from: [{ source: "orders", identity: { id: "客户编号" } }, { source: "customers", identity: { id: "客户编号" } }], attributes: [] },
      { key: "region", label: "大区", populated_from: [{ source: "customers", identity: { id: "大区" } }], attributes: [] },
    ],
    relations: [{ key: "r1", from: "order", to: "customer", label: "属于" }, { key: "r2", from: "customer", to: "region", label: "位于" }],
    verification: { metrics: { instances: { order: 35, customer: 26, region: 4 } } },
  },
  evaluation: { data_fit: {} },
  ...extra,
});

test("the sidebar offers every module for a table run, and leaves out data and questions for a document", () => {
  assert.deepEqual(sectionsFor(run()).map(([key]) => key), ["data", "objects", "graph", "qa", "check"]);
  assert.deepEqual(sectionsFor(run({ file: { name: "制度.md", kind: "document" } })).map(([key]) => key), ["objects", "graph", "check"]);
  assert.deepEqual(sectionsFor(null), []);
});

test("each object is a card: its name, a line about it, the tables it comes from, how many there are and how it connects", () => {
  const [order, customer] = objectCards(run(), null);
  assert.deepEqual(order, { key: "order", label: "订单", note: "一次购买", sources: ["orders"], identity: ["订单号"], count: 35, relations: 1, verdict: null, renamed: null });
  assert.deepEqual([customer.sources, customer.relations, customer.note], [["orders", "customers"], 2, ""]);
});

test("a card shows the person's verdict and the name they gave", () => {
  const decisions = { types: { customer: { verdict: "ok", label: "客户主体" }, region: { verdict: "wrong" } }, relations: {}, added: [] };
  const cards = objectCards(run(), decisions);
  assert.deepEqual(cards.map((c) => [c.verdict, c.renamed]), [[null, null], ["ok", "客户主体"], ["wrong", null]]);
});

test("an object's relations read from its own side", () => {
  assert.deepEqual(objectRelations(run(), "customer").map((r) => [r.key, r.text, r.other]),
    [["r1", "订单 属于 客户", "order"], ["r2", "客户 位于 大区", "region"]]);
});

test("the status chips lead to the module that explains them", () => {
  assert.deepEqual(["ontology", "stability", "fit", "qa", "ref"].map(sectionOfTile), ["objects", "objects", "check", "qa", "check"]);
});
