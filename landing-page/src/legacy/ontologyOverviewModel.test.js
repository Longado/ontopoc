import assert from "node:assert/strict";
import test from "node:test";

import { neighboursOf, overviewTiles, pathOf } from "./ontologyGraphModel.js";

const t = (key, label) => ({ key, label, populated_from: [], attributes: [] });
const r = (key, from, to) => ({ key, from, to });
const ontology = { object_types: [t("customer", "客户"), t("order", "订单"), t("product", "产品"), t("ticket", "工单")],
  relations: [r("order_customer", "order", "customer"), r("order_product", "order", "product"), r("ticket_order", "ticket", "order")] };

test("selecting a type lights up its neighbours and the relations between them", () => {
  const n = neighboursOf(ontology, "order");
  assert.deepEqual([...n.nodes].sort(), ["customer", "order", "product", "ticket"]);
  assert.deepEqual([...n.edges].sort(), ["order_customer", "order_product", "ticket_order"]);
  assert.deepEqual([...neighboursOf(ontology, "customer").nodes].sort(), ["customer", "order"]);
});

test("an answered question's query becomes a path on the graph", () => {
  const p = pathOf(ontology, { start: "ticket", via: ["ticket_order", "order_product"] });
  assert.deepEqual(p.nodes, ["ticket", "order", "product"]);
  assert.deepEqual(p.edges, ["ticket_order", "order_product"]);
  assert.equal(pathOf(ontology, { start: "ticket", via: ["missing"] }), null);
  assert.equal(pathOf(ontology, null), null);
});

test("the overview sums up each evaluation in one line, or says it has not run", () => {
  const run = { file: { kind: "table" }, ontology,
    evaluation: { data_fit: { checks: [{ passed: true }, { passed: false }] }, questions: { answered: 5, total: 6 }, reference: { diff: { counts: { types: { reference: 5, matched: 4 } } } } },
    previous: { diff: { types: { only_reference: ["x"], only_ours: [] }, relations: { only_reference: [], only_ours: [] } } } };
  assert.deepEqual(overviewTiles(run).map((x) => [x.key, x.value, x.tone]), [
    ["ontology", "4 个对象 · 3 条关系", "neutral"], ["fit", "通过 1 / 2", "warn"], ["qa", "能回答 5 / 6", "warn"],
    ["ref", "命中 4 / 5", "warn"], ["stability", "和上次有 1 处不同", "warn"]]);
  const fresh = overviewTiles({ file: { kind: "document" }, ontology, evaluation: { document_fit: { checks: [{ passed: true }] } } });
  assert.deepEqual(fresh.map((x) => [x.key, x.value]), [["ontology", "4 个对象 · 3 条关系"], ["fit", "通过 1 / 1"], ["qa", "不适用于文档"], ["ref", "还没比对"], ["stability", "第一次运行"]]);
});
