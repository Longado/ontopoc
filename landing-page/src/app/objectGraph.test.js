import assert from "node:assert/strict";
import test from "node:test";

import { OBJECT_BOX, nodeLines, objectGraphLayout } from "./objectGraphModel.js";
import { setLocale } from "./i18n/index.js";
import { answerView } from "./qaModel.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in askEnglish.test.js

const GRAPH = {
  nodes: [
    { id: "order:D1", type: "order", type_name: "订单", key: "D1", start: true },
    { id: "order:D2", type: "order", type_name: "订单", key: "D2", start: true },
    { id: "customer:KH1", type: "customer", type_name: "客户", key: "KH1", name: "苏州客户", start: false },
    { id: "ticket:T1", type: "ticket", type_name: "售后工单", key: "T1", start: false },
  ],
  edges: [
    { from: "order:D1", to: "customer:KH1", relation: "order_customer", name: "订单属于客户" },
    { from: "order:D2", to: "customer:KH1", relation: "order_customer", name: "订单属于客户" },
    { from: "ticket:T1", to: "order:D2", relation: "ticket_order", name: "工单属于订单" },
  ],
  starts: 16, shown: 2, cut: false,
};

test("the start objects stand in the first column and each object a step further in the next, whichever way the relation points", () => {
  const { boxes, width, height } = objectGraphLayout(GRAPH);
  assert.equal(boxes["order:D1"].x, 0);
  assert.equal(boxes["order:D2"].x, 0);
  assert.ok(boxes["customer:KH1"].x > 0);
  assert.equal(boxes["ticket:T1"].x, boxes["customer:KH1"].x);   // a ticket points at the order, and is still one step from it
  assert.equal(boxes["order:D1"].w, OBJECT_BOX.w);
  assert.ok(width >= boxes["customer:KH1"].x + OBJECT_BOX.w && height >= 2 * OBJECT_BOX.h);
  const ys = Object.values(boxes).filter((b) => b.x === 0).map((b) => b.y);
  assert.equal(new Set(ys).size, 2);   // no two objects on top of each other
});

test("an empty graph lays out to nothing rather than failing", () => {
  assert.deepEqual(objectGraphLayout({ nodes: [], edges: [] }).boxes, {});
});

test("a node shows its name with its type and key under it, or its key when it has no name", () => {
  assert.deepEqual(nodeLines(GRAPH.nodes[2]), ["苏州客户", "客户 KH1"]);
  assert.deepEqual(nodeLines(GRAPH.nodes[0]), ["D1", "订单"]);
});

test("a graph answer says how many start objects matched and how many are drawn", () => {
  const view = answerView({ status: "answered", types: [{ id: "order", name: "订单" }], answer: { total: 16, graph: GRAPH } });
  assert.equal(view.big, "16 个订单");
  assert.equal(view.note, "画出前 2 个，和它们连到的 2 个对象");
  assert.equal(view.graph, GRAPH);
  const all = answerView({ status: "answered", types: [{ id: "order", name: "订单" }], answer: { total: 2, graph: { ...GRAPH, starts: 2, cut: true } } });
  assert.equal(all.note, "画出全部 2 个，和它们连到的 2 个对象；连到的对象太多，只画了一部分");
});
