import assert from "node:assert/strict";
import test from "node:test";

import { connectedText, itemAction, keyPairText, relationPayload, relationProblem, suggestedColumns, toggled, waitingText } from "./relationModel.js";

test("a relation reads as connected rows over all rows, and as the key pair it joins on", () => {
  assert.equal(connectedText({ matched: 157, rows: 160 }), "157 / 160");
  assert.equal(connectedText(null), "—");
  assert.equal(keyPairText({ from_name: "订单", from_column: "客户编号", to_name: "客户", to_column: "客户编号" }), "订单.客户编号 = 客户.客户编号");
});

test("a relation whose types are not confirmed says which ones, and the queue tells apart confirm, wait, put forward again and blocked", () => {
  assert.equal(waitingText({ waiting_on: [{ name: "订单" }, { name: "客户" }] }), "要先确认对象类型“订单”、对象类型“客户”，才能确认这个关系");
  assert.equal(waitingText({ waiting_on: [] }), "");
  assert.equal(itemAction({ kind: "relation", can_confirm: true }), "confirm");
  assert.equal(itemAction({ kind: "relation", can_confirm: false, waiting_on: [{ name: "订单" }] }), "blocked");
  assert.equal(itemAction({ kind: "meaning", state: "needs_look", can_confirm: false }), "repropose");
  assert.equal(itemAction({ kind: "type", state: "checked", can_confirm: false }), "wait");
});

test("a new relation starts from the far end's key and the near end's column of that name", () => {
  const order = { key: ["订单号"], columns: [{ name: "订单号" }, { name: "客户编号" }] };
  const customer = { key: ["客户编号"], columns: [{ name: "客户编号" }] };
  assert.deepEqual(suggestedColumns(order, customer), { fromColumn: "客户编号", toColumn: "客户编号" });
  assert.deepEqual(suggestedColumns(customer, order), { fromColumn: "", toColumn: "订单号" });
  assert.deepEqual(suggestedColumns(null, customer), { fromColumn: "", toColumn: "" });
});

test("the form says what is missing and sends the service's own field names", () => {
  const form = { english: " order_customer ", name: " 订单属于客户 ", description: "", from: "order", to: "customer", cardinality: "many_to_one", fromColumn: "客户编号", toColumn: "客户编号" };
  assert.equal(relationProblem(form, false), "");
  assert.equal(relationProblem({ ...form, toColumn: "" }, false), "两边各要选一列");
  assert.equal(relationProblem({ ...form, english: "" }, true), "");
  assert.deepEqual(relationPayload(form), { english_name: "order_customer", name: "订单属于客户", description: "", from: "order", to: "customer", cardinality: "many_to_one", from_column: "客户编号", to_column: "客户编号" });
});

test("toggling a person on a type's list adds or takes away only that person", () => {
  assert.deepEqual(toggled([1, 2], 3, true), [1, 2, 3]);
  assert.deepEqual(toggled([1, 2], 1, false), [2]);
  assert.deepEqual(toggled([1, 2], 2, true), [1, 2]);
});
