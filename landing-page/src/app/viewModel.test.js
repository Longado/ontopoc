import assert from "node:assert/strict";
import test from "node:test";

import { confirmWords, emptyViewForm, newValueChoices, newValueText, rowsText, viewPayload, viewProblem, viewWaitingText } from "./viewModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests pin the Chinese wording; the English is in modelingEnglish.test.js

const form = (over = {}) => ({ ...emptyViewForm(), name: " 有效订单 ", filters: [{ column: "状态码", op: "is_not", label: "已取消" }, { column: "", op: "is", label: "" }], ...over });

test("the payload keeps the conditions that name a meaning and the latest rule only when it is on", () => {
  assert.deepEqual(viewPayload("order", form()), { name: "有效订单", type: "order", description: "", filters: [{ column: "状态码", op: "is_not", label: "已取消" }], latest: null });
  const latest = viewPayload("stock", form({ filters: [], latest: { on: true, key: ["产品编号"], order: "快照月份" } }));
  assert.deepEqual([latest.filters, latest.latest], [[], { key: ["产品编号"], order: "快照月份" }]);
});

test("the form says what is missing, in the order a person fills it", () => {
  assert.equal(viewProblem(form({ name: " " })), "要写视图的名字");
  assert.equal(viewProblem(emptyViewForm()), "要写视图的名字");
  assert.match(viewProblem({ ...emptyViewForm(), name: "x" }), /至少一个条件/);
  assert.equal(viewProblem(form()), "");
  assert.match(viewProblem(form({ latest: { on: true, key: [], order: "m" } })), /编号的列/);
  assert.match(viewProblem(form({ latest: { on: true, key: ["a"], order: "" } })), /比先后/);
  assert.match(viewProblem(form({ latest: { on: true, key: ["a"], order: "a" } })), /不能是编号列/);
});

test("the row count and what a view waits for read as sentences", () => {
  assert.equal(rowsText({ rows: 144, of: 160 }), "144 / 160 行");
  assert.equal(rowsText({ rows: null }), "读不出来");
  assert.equal(viewWaitingText({ waiting_on: [] }), "");
  assert.equal(viewWaitingText({ waiting_on: [{ name: "订单" }, { name: "订单.状态码" }] }), "要先确认“订单”、“订单.状态码”，才能确认这个视图");
});

test("a view with a new value cannot be confirmed until each new value has a choice, and the choice that changes the view says so on the button", () => {
  const nv = [{ column: "状态码", value: "3", label: "已发货待签收", rows: 5 }];
  assert.equal(newValueText(nv[0]), "“状态码”出现了新值 3（已发货待签收），5 行：算不算进来？");
  assert.equal(newValueChoices(nv, {}), null);
  assert.deepEqual(newValueChoices(nv, { "状态码|3": "in" }), [{ column: "状态码", value: "3", choice: "in" }]);
  assert.equal(confirmWords(newValueChoices(nv, { "状态码|3": "in" })), "确认这个视图");
  assert.equal(confirmWords(newValueChoices(nv, { "状态码|3": "out" })), "加上这个条件，交给另一位确认");
  assert.deepEqual(newValueChoices([], {}), []);   // nothing to ask: confirm as before
});
