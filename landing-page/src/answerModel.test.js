import assert from "node:assert/strict";
import test from "node:test";

import { derivedCard, reasonView } from "./answerModel.js";

test("a reason the model wrote is said in one plain sentence, its words one click away", () => {
  const item = { status: "query_limit", reason: "要从 客户 经 下单 到 订单明细，再算 单价 × 数量 ×（1 − 折扣）", reason_from_model: true };
  assert.deepEqual(reasonView(item), { line: "本体里需要的都有，但现在的查询还算不了这种问法。", detail: item.reason });
  assert.deepEqual(reasonView({ ...item, status: "ontology_gap" }), { line: "回答它需要的对象、关系或字段，本体里还没有。", detail: item.reason });
});

test("a reason code found is short and stands as it is", () => {
  const item = { status: "ontology_gap", reason: "本体里的 订单明细 没有属性 地区，无法按它筛选" };
  assert.deepEqual(reasonView(item), { line: item.reason, detail: null });
  assert.equal(reasonView({ status: "answered" }), null);
});

test("a derived measure waiting for the person shows the formula, what code computed and what it could not", () => {
  const item = { status: "needs_derived", derive: { type: "order_line", label: "金额", formula: "单价 × 数量 ×（1 − 折扣）",
    preview: { counted: 2155, skipped: 2, skipped_examples: ["10248 · 11：折扣 = 无 不是数字"], examples: [{ name: "10248 · 11", value: 168 }] } } };
  assert.deepEqual(derivedCard(item, "订单明细"), {
    formula: "金额 = 单价 × 数量 ×（1 − 折扣）",
    tried: "在全部订单明细上试算：算出 2,155 个，2 个算不了",
    examples: ["10248 · 11 → 168"],
    skipped: ["10248 · 11：折扣 = 无 不是数字"],
  });
});
