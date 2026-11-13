import assert from "node:assert/strict";
import test from "node:test";

import { answerView, definitionHref, isAnswer, readText, scopeText, standingText, staleLines } from "./qaModel.js";

const types = [{ id: "order", name: "订单" }];

test("a count, a measure and a share read as one line each, and groups as a table", () => {
  assert.deepEqual(answerView({ answer: { total: 16 }, types, status: "answered" }), { big: "16 个订单", note: "", table: null });
  assert.equal(answerView({ answer: { total: 160, measure: { field: "金额", op: "sum", value: 1115, counted: 160, skipped: 0 } }, types }).big, "金额合计 1,115");
  assert.equal(answerView({ answer: { total: 160, matched: 16, share: { field: "状态码", equals: "2" } }, types }).note, "状态码 = 2 的订单占 10%");
  const grouped = answerView({ answer: { groups: [["华东", 3], ["华北", 1]], total_groups: 2, without_value: 0 }, types });
  assert.deepEqual([grouped.big, grouped.table.head, grouped.table.rows], ["2 组", ["分组", "订单数"], [["华东", "3"], ["华北", "1"]]]);
  assert.equal(answerView({ status: "refused" }), null);
});

test("the orders the relation check counts are counted as orders, not as the first type of the answer", () => {
  assert.equal(answerView({ answer: { total: 3, relation_gap: { many: "订单" } }, types: [{ name: "客户" }, { name: "订单" }] }).big, "3 个订单");
  assert.equal(isAnswer({ status: "no_data" }) && !isAnswer({ status: "refused" }), true);
});

test("a saved answer says which dataset has a newer version and which definition is not as it was", () => {
  assert.deepEqual(staleLines({ stale: [{ dataset: "订单", read: 1, now: 2 }], changed: [{ name: "订单.状态码", state: "needs_look" }, { name: "订单", state: "confirmed" }] }),
    ["订单 有新版本：这条回答读的是第 1 版，现在是第 2 版", "订单.状态码 现在需再看", "订单 在回答之后重新确认过"]);
  assert.deepEqual(staleLines({ stale: [], changed: [] }), []);
  assert.deepEqual(readText({ 订单: 1, 客户: 2 }), ["订单 第 1 版", "客户 第 2 版"]);
});

test("a definition links to its own page and a refusal says where it stands", () => {
  assert.equal(definitionHref("enum:order:状态码"), "#/types/order");
  assert.equal(definitionHref("objtype:order"), "#/types/order");
  assert.equal(definitionHref("relation:order_customer"), "#/relations/order_customer");
  assert.equal(standingText({ state: "needs_look", reason: "取值变了" }), "取值变了");
  assert.equal(standingText({ state: "checked", proposed_by: "Ann" }), "Ann 提出，还没有另一位确认");
  assert.equal(scopeText({ types: [1, 2, 3] }), "范围：3 个已确认的对象类型");
});
