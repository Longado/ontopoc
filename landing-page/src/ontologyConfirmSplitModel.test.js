import assert from "node:assert/strict";
import test from "node:test";

import { splitExtras } from "./ontologyConfirmModel.js";

test("against a confirmed reference, what the ontology has extra is either judged wrong or not judged yet", () => {
  const ontology = { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }, { key: "product", label: "产品" }],
    relations: [{ key: "oc", from: "order", to: "customer" }, { key: "op", from: "order", to: "product" }] };
  const decisions = { types: { customer: { verdict: "wrong" }, order: { verdict: "ok" } }, relations: { oc: { verdict: "wrong" } }, added: [] };
  const diff = { types: { only_ours: ["客户", "产品"] }, relations: { only_ours: ["订单 — 客户", "订单 — 产品"] } };
  assert.deepEqual(splitExtras(ontology, decisions, diff), {
    types: { wrong: ["客户"], unjudged: ["产品"] }, relations: { wrong: ["订单 — 客户"], unjudged: ["订单 — 产品"] } });
});
