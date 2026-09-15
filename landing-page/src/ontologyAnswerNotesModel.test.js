import assert from "node:assert/strict";
import test from "node:test";

import { conflictNote } from "./ontologyStudioModel.js";

test("an answer counting objects whose identity disagrees with itself says it counted each identity once", () => {
  const run = { ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }] },
    evaluation: { data_fit: { identity_conflicts: [{ type: "customer", identity: "C010", field: "客户名称" }, { type: "customer", identity: "C010", field: "地区" }] } } };
  assert.equal(conflictNote(run, ["order", "customer"]), "按编号数对象：有 1 个客户编号在数据里信息不一致（见数据体检），每个编号只算一次。");
  assert.equal(conflictNote(run, ["order"]), "");
  assert.equal(conflictNote({ ...run, evaluation: { data_fit: null } }, ["customer"]), "");
});
