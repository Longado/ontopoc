import assert from "node:assert/strict";
import test from "node:test";

import { editForm, formOf } from "./formModel.js";

const run = { evaluation: { form: { types: { order: { label: "销售订单", description: "一次下单", display_field: "订单号", drafted: true,
  fields: { 金额: { label: "订单金额", description: "含税", drafted: true } } } } } } };

test("an object's form comes out whole, empty where nothing was written", () => {
  assert.deepEqual(formOf(run, "customer"), { label: "", description: "", display_field: null, drafted: false, fields: {} });
  assert.equal(formOf(run, "order").fields.金额.label, "订单金额");
  assert.equal(formOf({ evaluation: {} }, "order").label, "");
});

test("what a person types is theirs: the drafted mark goes, the rest stays", () => {
  const f = editForm(formOf(run, "order"), null, "label", "订单");
  assert.deepEqual([f.label, f.drafted, f.fields.金额.drafted], ["订单", false, true]);
  const g = editForm(f, "金额", "label", "成交金额");
  assert.deepEqual(g.fields.金额, { label: "成交金额", description: "含税", drafted: false });
  const h = editForm(g, "折扣", "description", "打折");
  assert.deepEqual(h.fields.折扣, { label: "", description: "打折", drafted: false });
  assert.equal(editForm(h, null, "display_field", "金额").display_field, "金额");
});
