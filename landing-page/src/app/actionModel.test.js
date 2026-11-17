import assert from "node:assert/strict";
import test from "node:test";

import { actionFits, actionPayload, actionProblem, emptyActionForm, emptyCondition, opsFor, recordChangeText, recordStateText, rowKey, runPayload, runProblem } from "./actionModel.js";
import { notifyRecipient, choicesPayload } from "./actionModel.js";

test("an action form needs a name, a property for an edit, and a value for each condition that takes one", () => {
  const form = emptyActionForm();
  assert.equal(form.kind, "edit");
  assert.equal(actionProblem(form), "要写行为的名字");
  assert.equal(actionProblem({ ...form, name: "改订单状态" }), "要选至少一个要改的属性");
  assert.equal(actionProblem({ ...form, name: "新建订单", kind: "create" }), "");   // a create may ask for the key alone
  assert.equal(actionProblem({ ...form, name: "删除订单", kind: "delete" }), "");
  const named = { ...form, name: "改订单状态", properties: ["状态码"] };
  assert.equal(actionProblem({ ...named, conditions: [{ ...emptyCondition(), column: "" }] }), "每个条件要选属性");
  assert.equal(actionProblem({ ...named, conditions: [{ column: "状态码", op: "eq", value: " " }] }), "条件要写取值，或者去掉这个条件");
  assert.equal(actionProblem({ ...named, conditions: [{ column: "金额", op: "empty", value: "" }] }), "");
  assert.equal(actionProblem(named), "");
});

test("the payload carries the kind, the conditions in the service's form, and no property for a delete or condition for a create", () => {
  const form = { ...emptyActionForm(), name: " 改金额 ", properties: ["金额"],
    conditions: [{ column: "状态码", op: "eq", value: " 1 " }, { column: "金额", op: "gt", value: "3000" }, { column: "客户编号", op: "in", value: "KH001，KH002, KH003、" }, { column: "备注", op: "empty", value: "x" }] };
  assert.deepEqual(actionPayload("order", form), {
    name: "改金额", type: "order", kind: "edit", description: "", properties: ["金额"],
    conditions: [{ column: "状态码", op: "eq", value: "1" }, { column: "金额", op: "gt", value: "3000" }, { column: "客户编号", op: "in", value: ["KH001", "KH002", "KH003"] }, { column: "备注", op: "empty" }],
  });
  assert.deepEqual(actionPayload("order", { ...form, kind: "delete" }).properties, []);
  assert.deepEqual(actionPayload("order", { ...form, kind: "create" }).conditions, []);
  assert.deepEqual(actionPayload("order", { ...form, submitters: [3, 5] }).submitters, [3, 5]);
});

test("a property offers the operators that make sense for it", () => {
  assert.deepEqual(opsFor({ type: "integer", enum: false }), ["eq", "ne", "gt", "ge", "lt", "le", "in", "empty", "not_empty"]);
  assert.deepEqual(opsFor({ type: "date", enum: false }), ["eq", "ne", "gt", "ge", "lt", "le", "in", "empty", "not_empty"]);
  assert.deepEqual(opsFor({ type: "text", enum: false }), ["eq", "ne", "in", "empty", "not_empty"]);
  assert.deepEqual(opsFor({ type: "integer", enum: true }), ["eq", "ne", "in", "empty", "not_empty"]);   // a code is a meaning, not an amount
});

test("a row's key comes from the key columns only", () => {
  const columns = [{ column: "订单号", key: true }, { column: "金额", key: false }, { column: "状态码", key: false }];
  assert.deepEqual(rowKey(columns, ["DD1", "10", "1"]), { key: { 订单号: "DD1" }, text: "DD1" });
});

test("a record that undoes another says which, after its state", () => {
  assert.equal(recordStateText({ state: "pending", undo_of: 7 }), "等批准（撤销 #7）");
  assert.equal(recordStateText({ state: "approved", undo_of: 7 }), "已批准（撤销 #7）");
  assert.equal(recordStateText({ state: "approved" }), "已批准");
});

test("a pending record whose data moved says so", () => {
  assert.equal(recordStateText({ state: "pending", stale: false }), "等批准");
  assert.equal(recordStateText({ state: "pending", stale: true }), "等批准（数据已变）");
  assert.equal(recordStateText({ state: "needs_look" }), "需再看");
});

test("an action is offered only on rows that meet all its conditions, and a create on none", () => {
  const columns = [{ column: "订单号" }, { column: "状态码" }, { column: "金额" }, { column: "客户编号" }];
  const action = { kind: "edit", conditions: [{ column: "状态码", op: "eq", value: "1" }, { column: "金额", op: "gt", value: "3000" }, { column: "客户编号", op: "in", value: ["KH001", "KH002"] }] };
  assert.equal(actionFits(action, columns, ["DD1", "1", "4600", "KH001"]), true);
  assert.equal(actionFits(action, columns, ["DD2", "1", "2080", "KH001"]), false);   // 2080 is not more than 3000 (as numbers, not as text)
  assert.equal(actionFits(action, columns, ["DD3", "1", "4600", "KH009"]), false);
  assert.equal(actionFits(action, columns, ["DD4", "0", "4600", "KH001"]), false);
  assert.equal(actionFits({ kind: "edit", conditions: [{ column: "客户编号", op: "empty" }] }, columns, ["DD5", "1", "1", ""]), true);
  assert.equal(actionFits({ kind: "edit", conditions: [{ column: "客户编号", op: "ne", value: "KH001" }] }, columns, ["DD5", "1", "1", null]), true);
  assert.equal(actionFits({ kind: "edit", conditions: [] }, columns, ["DD2", "0"]), true);
  assert.equal(actionFits({ kind: "create", conditions: [] }, columns, ["DD2", "0"]), false);   // a create is run from the type, not on an object
});

test("running a create sends the key apart from the values; a delete sends no values and needs a reason", () => {
  const create = { kind: "create", parameters: [{ column: "订单号", key: true }, { column: "金额", key: false }] };
  assert.deepEqual(runPayload(create, { 订单号: " DD9 ", 金额: "10" }), { key: { 订单号: "DD9" }, params: { 金额: "10" } });
  assert.equal(runProblem(create, { 订单号: "DD9", 金额: " " }, ""), "每一项都要填");
  assert.equal(runProblem(create, { 订单号: "DD9", 金额: "10" }, ""), "");
  const drop = { kind: "delete", parameters: [] };
  assert.deepEqual(runPayload(drop, {}), { params: {} });
  assert.equal(runProblem(drop, {}, " "), "删除要写理由");
  assert.equal(runProblem(drop, {}, "客户撤单"), "");
  assert.deepEqual(runPayload({ kind: "edit", parameters: [{ column: "状态码" }] }, { 状态码: "0" }), { params: { 状态码: "0" } });
});

test("a create or a delete record reads as what it does, an edit as before → after", () => {
  assert.equal(recordChangeText({ kind: "create", change_text: "新建：金额 1200", before_text: "（还没有）", after_text: "金额 1200" }), "新建：金额 1200");
  assert.equal(recordChangeText({ kind: "delete", change_text: "删除：金额 1", before_text: "金额 1", after_text: "（删除）" }), "删除：金额 1");
  assert.equal(recordChangeText({ kind: "edit", before_text: "状态码 生产中", after_text: "状态码 已交付" }), "状态码 生产中 → 状态码 已交付");
  assert.equal(recordChangeText({ before_text: "a", after_text: "b" }), "a → b");
});

test("a notice recipient from the form is whole or nothing", () => {
  assert.deepEqual(notifyRecipient({ kind: "attr", column: "客户编号", attr: " 负责客户 " }), { kind: "attr", column: "客户编号", user_attr: "负责客户" });
  assert.deepEqual(notifyRecipient({ kind: "via", relation: "order_customer", column: "城市", attr: "城市" }), { kind: "via", relation: "order_customer", column: "城市", user_attr: "城市" });
  assert.equal(notifyRecipient({ kind: "via", relation: "", column: "城市", attr: "城市" }), null);
  assert.equal(notifyRecipient({ kind: "attr", column: "", attr: "部门" }), null);
});

test("only whole choices of a written property are sent", () => {
  const form = { properties: ["客户编号"], choices: { 客户编号: { type: "customer", column: " 客户编号 " }, 金额: { type: "customer", column: "x" }, 数量: { type: "", column: "y" } } };
  assert.deepEqual(choicesPayload(form), { 客户编号: { type: "customer", column: "客户编号" } });
  assert.deepEqual(choicesPayload({ properties: [], choices: undefined }), {});
});
