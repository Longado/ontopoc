import assert from "node:assert/strict";
import test from "node:test";

import { groupTitle, markKey, missing, requestItems, resultLines, withMark } from "./batchModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests pin the Chinese wording; the English is in modelingEnglish.test.js

const item = (over) => ({ element: "objtype:order", title: "订单", version: 3, seen: { dataset_version: 2, rows: 160 }, ready: true, ...over });
const view = item({ element: "objview:有效订单", title: "有效订单（订单的视图）", version: 5, new_values: [{ column: "状态码", value: "3", label: "已发货待签收", rows: 16 }] });
const group = { items: [item({ element: "enum:order:状态码", title: "订单.状态码", version: 4, seen: { dataset_version: 2, counts: { 1: 96 } } }), item(), view, item({ element: "relation:order_customer", title: "订单属于客户", seen: [160, 157, 3, 0, 0, 0], version: 2 })] };

test("the heading names the version and how many items it moved", () => {
  assert.equal(groupTitle("订单", 2, 4), "订单 第 2 版 让这 4 项需要再看");
});

test("the confirm waits until every offered item is marked seen and every new value has an answer", () => {
  assert.equal(missing(group, [], {}), "还有 4 项没有标“已看过”");
  const seen = group.items.reduce((marks, i) => withMark(marks, i, true), []);
  assert.equal(missing(group, seen.slice(0, 3), {}), "还有 1 项没有标“已看过”");
  assert.equal(missing(group, seen, {}), "“有效订单（订单的视图）”的新值还没有选算不算进来");
  assert.equal(missing(group, seen, { "objview:有效订单": { "状态码|3": "in" } }), "");
});

test("a mark does not outlive a change to the version or the data the item showed", () => {
  const marks = withMark([], group.items[1], true);
  assert.equal(marks.includes(markKey(group.items[1])), true);
  assert.equal(marks.includes(markKey({ ...group.items[1], version: 4 })), false);
  assert.equal(marks.includes(markKey({ ...group.items[1], seen: { dataset_version: 3, rows: 161 } })), false);
  assert.deepEqual(withMark(marks, group.items[1], false), []);
});

test("an item the person is not offered is neither waited for nor sent", () => {
  const not = item({ element: "objview:有效订单", ready: false, why_not: "这一项是你提的或你改过的，要另一位建设者确认", new_values: [] });
  const g = { items: [group.items[0], not] };
  const marks = withMark([], g.items[0], true);
  assert.equal(missing(g, marks, {}), "");
  assert.deepEqual(requestItems(g, {}).map((i) => i.element), ["enum:order:状态码"]);
  assert.equal(missing({ items: [not] }, [], {}), "这一组里没有你现在能确认的");
});

test("the request carries what each item showed and the answers to the view's question", () => {
  const body = requestItems(group, { "objview:有效订单": { "状态码|3": "out" } });
  assert.deepEqual(body.map((i) => i.element), ["enum:order:状态码", "objtype:order", "objview:有效订单", "relation:order_customer"]);
  assert.deepEqual(body[2], { element: "objview:有效订单", version: 5, seen: { dataset_version: 2, rows: 160 }, new_values: [{ column: "状态码", value: "3", choice: "out" }] });
  assert.equal("new_values" in body[1], false);
});

test("the result says what was confirmed, what went to the other builder and what was left out and why", () => {
  assert.deepEqual(resultLines({ confirmed: [{ title: "订单.状态码" }, { title: "订单" }], sent_on: [{ title: "有效订单" }], left_out: [{ title: "订单属于客户", why: "要先确认“订单”类型" }] }), [
    "确认了 2 项：订单.状态码、订单",
    "有效订单：新值不算进来，视图的条件改了，要另一位建设者确认",
    "订单属于客户：没有确认，要先确认“订单”类型",
  ]);
  assert.deepEqual(resultLines({ confirmed: [], sent_on: [], left_out: [] }), []);
});
