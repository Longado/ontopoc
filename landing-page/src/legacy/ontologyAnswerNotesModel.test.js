import assert from "node:assert/strict";
import test from "node:test";

import { conflictNote, rerunLine } from "./ontologyStudioModel.js";

test("an answer counting objects whose identity disagrees with itself says it counted each identity once", () => {
  const run = { ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }] },
    evaluation: { data_fit: { identity_conflicts: [{ type: "customer", identity: "C010", field: "客户名称" }, { type: "customer", identity: "C010", field: "地区" }] } } };
  assert.equal(conflictNote(run, ["order", "customer"]), "按编号数对象：有 1 个客户编号在数据里信息不一致（见数据体检），每个编号只算一次。");
  assert.equal(conflictNote(run, ["order"]), "");
  assert.equal(conflictNote({ ...run, evaluation: { data_fit: null } }, ["customer"]), "");
});

test("a conflict a person settled by keeping the latest row is no longer said", () => {
  const run = { ontology: { object_types: [{ key: "customer", label: "客户" }] },
    evaluation: { data_fit: { identity_conflicts: [{ type: "customer", identity: "KH012", field: "城市", settled: "keep_latest" }] } } };
  assert.equal(conflictNote(run, ["customer"]), "");
  run.evaluation.data_fit.identity_conflicts.push({ type: "customer", identity: "KH013", field: "城市" });
  assert.equal(conflictNote(run, ["customer"]), "按编号数对象：有 1 个客户编号在数据里信息不一致（见数据体检），每个编号只算一次。");
});

test("an answer worked out again says what changed and what it said before", () => {
  assert.equal(rerunLine({ status: "answered" }), "");
  const item = { query: { start: "order" }, rerun: { because: ["「状态码」的含义已确认（2 = 已取消）"], was: { status: "no_data", reason: "数据里没有满足筛选条件的对象" } } };
  assert.equal(rerunLine(item), "已按新确认的内容重算：「状态码」的含义已确认（2 = 已取消）。之前是：数据里没有满足筛选条件的对象");
  assert.equal(rerunLine({ ...item, rerun: { because: ["a", "b"], was: { status: "answered", answer: { total: 5 } } } }), "已按新确认的内容重算：a；b。之前是：共 5 个");
});
