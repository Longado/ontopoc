import assert from "node:assert/strict";
import test from "node:test";

import { pathOf } from "./ontologyGraphModel.js";
import { answerLines } from "./ontologyStudioModel.js";

const t = (key, label) => ({ key, label, populated_from: [], attributes: [] });
const r = (key, from, to) => ({ key, from, to });
const ontology = { object_types: [t("customer", "客户"), t("order", "订单"), t("product", "产品"), t("ticket", "工单")],
  relations: [r("order_customer", "order", "customer"), r("order_product", "order", "product"), r("ticket_order", "ticket", "order")] };

test("a query grouped along two routes lights up both, one walk each", () => {
  const p = pathOf(ontology, { start: "ticket", group_by: [{ via: ["ticket_order", "order_customer"], field: "客户.名称" }, { via: ["ticket_order", "order_product"], field: "产品.名称" }] });
  assert.deepEqual(p.walks, [{ nodes: ["ticket", "order", "customer"], edges: ["ticket_order", "order_customer"] },
    { nodes: ["ticket", "order", "product"], edges: ["ticket_order", "order_product"] }]);
  assert.deepEqual(p.nodes, ["ticket", "order", "customer", "product"]);
  assert.deepEqual(p.edges, ["ticket_order", "order_customer", "order_product"]);
  assert.deepEqual(pathOf(ontology, { start: "ticket", via: ["ticket_order"] }).walks, [{ nodes: ["ticket", "order"], edges: ["ticket_order"] }]);
});

test("shares read as matched over all with a percentage", () => {
  assert.deepEqual(answerLines({ status: "answered", answer: { groups: [["甲", 2, 2], ["乙", 1, 6]], total_groups: 2, without_value: 0, share: { field: "交货状态", equals: "延期交货" } } }),
    ["甲：2 / 2（100%）", "乙：1 / 6（17%）"]);
  assert.deepEqual(answerLines({ status: "answered", answer: { total: 40, matched: 9, share: { field: "交货状态", equals: "延期交货" } } }),
    ["共 40 个，其中 9 个“交货状态”为“延期交货”（23%）"]);
});
