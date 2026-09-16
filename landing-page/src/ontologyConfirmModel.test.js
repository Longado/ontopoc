import assert from "node:assert/strict";
import test from "node:test";

import { addType, confirmProgress, decisionsOf, removeAdded, renameType, setVerdict } from "./ontologyConfirmModel.js";
import { overviewTiles } from "./ontologyGraphModel.js";

const ontology = { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }, { key: "product", label: "产品" }],
  relations: [{ key: "order_customer", from: "order", to: "customer" }, { key: "order_product", from: "order", to: "product" }] };
const empty = decisionsOf({ ontology });

test("a run starts with no decisions, or with the ones saved on it", () => {
  assert.deepEqual(empty, { types: {}, relations: {}, added: [] });
  const saved = { types: { order: { verdict: "ok" } }, relations: {}, added: ["发票"] };
  assert.deepEqual(decisionsOf({ ontology, confirmation: { decisions: saved } }), saved);
});

test("verdicts toggle, and relations stay consistent with their ends", () => {
  const d1 = setVerdict(ontology, empty, "relations", "order_customer", "ok");
  assert.deepEqual(d1.types, { order: { verdict: "ok" }, customer: { verdict: "ok" } });   // a right relation needs its ends
  assert.equal(empty.types.order, undefined);                                           // the old decisions are not changed
  const d2 = setVerdict(ontology, d1, "types", "customer", "wrong");
  assert.equal(d2.relations.order_customer.verdict, "wrong");                           // a wrong object takes its relations with it
  assert.equal(setVerdict(ontology, d2, "types", "customer", "wrong").types.customer, undefined);   // same button again clears
});

test("renames and additions are kept, and blank renames clear", () => {
  const d = renameType(setVerdict(ontology, empty, "types", "customer", "ok"), "customer", "客户主体");
  assert.deepEqual(d.types.customer, { verdict: "ok", label: "客户主体" });
  assert.deepEqual(renameType(d, "customer", "  ").types.customer, { verdict: "ok" });
  const a = addType(ontology, addType(ontology, empty, " 发票 "), "发票");
  assert.deepEqual(a.added, ["发票"]);
  assert.deepEqual(addType(ontology, empty, "订单").added, []);   // already in the ontology
  assert.deepEqual(removeAdded(a, "发票").added, []);
});

test("progress counts judged items", () => {
  const d = setVerdict(ontology, empty, "relations", "order_customer", "ok");
  assert.deepEqual(confirmProgress(ontology, d), { judged: 3, total: 5, ok: 3, wrong: 0, added: 0 });
});

test("a confirmed reference names itself on the tile", () => {
  const run = { file: { kind: "table" }, saved_as: "x.json", ontology, evaluation: { data_fit: null,
    reference: { confirmed: true, diff: { counts: { types: { reference: 3, matched: 2 } } } } } };
  const tile = overviewTiles(run).find((t) => t.key === "ref");
  assert.equal(tile.value, "命中 2 / 3");
  assert.equal(tile.hint, "对照你确认过的本体：1 个对象没对上");
});
