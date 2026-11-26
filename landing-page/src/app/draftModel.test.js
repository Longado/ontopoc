import assert from "node:assert/strict";
import test from "node:test";

import { draftView, isDraft } from "./draftModel.js";
import { definitionHref, statusText } from "./qaModel.js";
import { setLocale } from "./i18n/index.js";

const action = { id: "改订单状态", name: "改订单状态", kind: "edit", type: "order", type_name: "订单", says: "改 订单 的「状态码」", version: 2,
  parameters: [{ column: "状态码", name: "状态码", type: "integer", key: false, options: [{ value: "0", label: "已交付" }, { value: "1", label: "生产中" }] }] };
const edit = { status: "draft", reason: "x", draft: { action, object: "订单 DD20260003", key: { 订单号: "DD20260003" }, params: { 状态码: "0" }, values: { 状态码: "0" }, reason: "客户已签收",
  beside: [{ column: "状态码", name: "状态码", current: "生产中", asked: "已交付" }], submit: { action: "改订单状态", key: { 订单号: "DD20260003" }, params: { 状态码: "0" }, reason: "客户已签收" } } };

test("a draft is told apart from an answer and a refusal", () => {
  assert.equal(isDraft(edit), true);
  assert.equal(isDraft({ status: "answered", answer: {} }), false);
  assert.equal(isDraft({ status: "draft" }), false);   // no draft in it: nothing to show
});

test("an edit draft shows the object's current value beside the asked one and prefills the action's own form", () => {
  setLocale("zh");
  const view = draftView(edit);
  assert.equal(view.title, "草拟：改订单状态（订单 DD20260003）");
  assert.deepEqual(view.rows, [{ key: "状态码", name: "状态码", current: "生产中", asked: "已交付" }]);
  assert.deepEqual(view.form, { action, objectKey: { 订单号: "DD20260003" }, objectText: "订单 DD20260003", values: { 状态码: "0" }, reason: "客户已签收" });
  assert.match(view.note, /还没有提交/);
  setLocale("en");
  assert.equal(draftView(edit).title, "Draft: 改订单状态 (订单 DD20260003)");
  assert.match(draftView(edit).note, /Nothing is submitted yet/);
});

test("a create has no object yet and a delete asks for nothing: the form takes the key, the rows say what is new and what goes", () => {
  setLocale("en");
  const create = { status: "draft", draft: { ...edit.draft, action: { ...action, kind: "create" }, object: "订单 DD29990001", key: { 订单号: "DD29990001" }, values: { 订单号: "DD29990001", 金额: "1200" },
    beside: [{ column: "订单号", name: "订单号", current: null, asked: "DD29990001" }, { column: "金额", name: "金额", current: null, asked: "1200" }] } };
  const made = draftView(create);
  assert.equal(made.form.objectKey, null);
  assert.deepEqual(made.rows.map((r) => [r.current, r.asked]), [["(none yet)", "DD29990001"], ["(none yet)", "1200"]]);
  const drop = { status: "draft", draft: { ...edit.draft, action: { ...action, kind: "delete", parameters: [] }, values: {}, beside: [{ column: "金额", name: "金额", current: "2520", asked: null }] } };
  assert.deepEqual(draftView(drop).rows, [{ key: "金额", name: "金额", current: "2520", asked: "(deleted)" }]);
  setLocale("zh");
  assert.deepEqual(draftView(drop).rows[0].asked, "（删除）");
});

test("an action named in a refusal links to its type's actions tab, and a draft has its own word in the history", () => {
  assert.equal(definitionHref("objaction:改订单状态", "order"), "#/types/order/actions");
  setLocale("en");
  assert.equal(statusText("draft"), "Drafted");
  setLocale("zh");
  assert.equal(statusText("draft"), "已草拟");
});
