import assert from "node:assert/strict";
import test from "node:test";

import { relatedCard, unconfirmedNote } from "./objectModel.js";

const related = [
  { id: "order_customer", name: "订单属于客户", other: "customer", other_name: "客户", count: 1, confirmed: false, objects: [{ n: 3, text: "KH022 + 苏州", name: "苏州家电客户22" }] },
  { id: "order_product", name: "订单用产品", other: "product", other_name: "产品", count: 12, confirmed: false, objects: [{ n: 1, text: "CP03", name: null }, { n: 2, text: "CP04", name: "吸尘器" }] },
  { id: "order_task", name: "订单有工单", other: "task", other_name: "工单", count: 0, confirmed: true, objects: [] },
];

test("a related object shows its name beside the key, and only the key when the type has no name column (W3)", () => {
  const card = relatedCard(related[1]);
  assert.deepEqual(card.objects.map((o) => o.label), ["CP03", "CP04 · 吸尘器"]);
  assert.equal(card.more, "等 12 个");
  assert.equal(relatedCard(related[0]).objects[0].label, "KH022 + 苏州 · 苏州家电客户22");
  assert.equal(relatedCard(related[2]).more, "");
});

test("a card does not repeat 关系未确认; the page says it once, naming the relations (W3)", () => {
  assert.equal("note" in relatedCard(related[0]), false);
  assert.equal(unconfirmedNote(related), "有 2 个关系还没确认：订单属于客户、订单用产品。关联到的对象可能会变。");
  assert.equal(unconfirmedNote([related[2]]), "");
  assert.equal(unconfirmedNote([]), "");
});
