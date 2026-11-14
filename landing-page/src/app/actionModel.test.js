import assert from "node:assert/strict";
import test from "node:test";

import { actionFits, actionPayload, actionProblem, emptyActionForm, recordStateText, rowKey } from "./actionModel.js";

test("an action form needs a name, a property to change, and a value when a condition column is picked", () => {
  const form = emptyActionForm();
  assert.equal(actionProblem(form), "要写行为的名字");
  assert.equal(actionProblem({ ...form, name: "改订单状态" }), "要选至少一个要改的属性");
  assert.equal(actionProblem({ ...form, name: "改订单状态", properties: ["状态码"], condition: { column: "状态码", value: " " } }), "条件要写取值，或者不设条件");
  assert.equal(actionProblem({ ...form, name: "改订单状态", properties: ["状态码"] }), "");
});

test("the payload has no condition unless a column was picked", () => {
  const form = { ...emptyActionForm(), name: " 改订单状态 ", properties: ["状态码"] };
  assert.deepEqual(actionPayload("order", form), { name: "改订单状态", type: "order", description: "", properties: ["状态码"], condition: null });
  assert.deepEqual(actionPayload("order", { ...form, condition: { column: "状态码", value: "1" } }).condition, { column: "状态码", value: "1" });
});

test("a row's key comes from the key columns only", () => {
  const columns = [{ column: "订单号", key: true }, { column: "金额", key: false }, { column: "状态码", key: false }];
  assert.deepEqual(rowKey(columns, ["DD1", "10", "1"]), { key: { 订单号: "DD1" }, text: "DD1" });
});

test("a pending record whose data moved says so", () => {
  assert.equal(recordStateText({ state: "pending", stale: false }), "等批准");
  assert.equal(recordStateText({ state: "pending", stale: true }), "等批准（数据已变）");
  assert.equal(recordStateText({ state: "needs_look" }), "需再看");
});

test("an action is offered only on rows that meet its condition", () => {
  const columns = [{ column: "订单号" }, { column: "状态码" }];
  const action = { condition: { column: "状态码", value: "1" } };
  assert.equal(actionFits(action, columns, ["DD1", "1"]), true);
  assert.equal(actionFits(action, columns, ["DD2", "0"]), false);
  assert.equal(actionFits({ condition: null }, columns, ["DD2", "0"]), true);
});
