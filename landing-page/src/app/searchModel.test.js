import assert from "node:assert/strict";
import test from "node:test";
import { buildEntries, matchScore, pageEntries, recordVisit, search } from "./searchModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("matchScore: exact beats prefix beats contains beats nothing; case and spaces do not matter", () => {
  assert.ok(matchScore("订单", "订单") > matchScore("订单明细", "订单"));
  assert.ok(matchScore("订单明细", "订单") > matchScore("售后订单", "订单"));
  assert.ok(matchScore("售后订单", "订单") > 0);
  assert.equal(matchScore("客户", "订单"), 0);
  assert.ok(matchScore("Order Items", " order ") > 0);
  assert.equal(matchScore("订单", ""), 0);
});

test("buildEntries turns each list into entries with a kind, a label and an address", () => {
  const entries = buildEntries({
    datasets: [{ name: "订单" }],
    types: [{ id: "order", name: "订单", state: "confirmed" }],
    relations: [{ id: "order_customer", name: "订单属于客户", from_name: "订单", to_name: "客户" }],
    pipelines: [{ id: "p1", name: "订单清洗" }],
    boards: [{ id: 4, name: "销售总览" }],
    actions: [{ type: "order", name: "取消订单" }],
  });
  assert.deepEqual(entries.map((e) => [e.kind, e.label, e.href]), [
    ["数据集", "订单", "#/datasets/%E8%AE%A2%E5%8D%95/fields"],
    ["对象类型", "订单", "#/types/order/props"],
    ["关系", "订单属于客户", "#/relations/order_customer"],
    ["管道", "订单清洗", "#/pipelines/p1"],
    ["看板", "销售总览", "#/boards/4"],
    ["行为", "取消订单", "#/types/order/actions"],
  ]);
});

test("a missing list is skipped, not an error", () => {
  assert.deepEqual(buildEntries({}), []);
  assert.deepEqual(buildEntries({ datasets: null, types: [{ id: "a", name: "A" }] }).map((e) => e.kind), ["对象类型"]);
});

test("search ranks by score, then keeps the kinds in a steady order, and caps the list", () => {
  const entries = buildEntries({ datasets: [{ name: "售后订单" }, { name: "订单" }], types: [{ id: "order", name: "订单" }, { id: "x", name: "订单明细" }] });
  const hits = search(entries, "订单", 10);
  assert.deepEqual(hits.map((h) => h.label), ["订单", "订单", "订单明细", "售后订单"]);
  assert.equal(hits[0].kind, "数据集");
  assert.equal(search(entries, "订单", 2).length, 2);
  assert.deepEqual(search(entries, "不存在", 5), []);
});

test("an english id also finds a type", () => {
  const entries = buildEntries({ types: [{ id: "order", name: "订单" }] });
  assert.equal(search(entries, "order", 5).length, 1);
});

test("pageEntries lists the pages this person's navigation offers, plus the account page", () => {
  const viewer = pageEntries({ role: "viewer" }).map((e) => e.label);
  assert.deepEqual(viewer, ["首页", "助手", "看板", "消息", "我的账号"]);
  const admin = pageEntries({ role: "admin" }).map((e) => e.label);
  assert.ok(admin.includes("用户") && admin.includes("AI 工具接入") && admin.includes("血缘"));
  assert.ok(pageEntries({ role: "viewer" }).every((e) => e.kind === "页面"));
});

test("recordVisit puts the newest first, drops a repeat, and keeps eight", () => {
  let list = [];
  for (let i = 0; i < 10; i += 1) list = recordVisit(list, { href: `#/x/${i}`, label: `x${i}` });
  assert.equal(list.length, 8);
  assert.equal(list[0].href, "#/x/9");
  list = recordVisit(list, { href: "#/x/5", label: "x5" });
  assert.deepEqual([list[0].href, list.length], ["#/x/5", 8]);
  assert.equal(list.filter((e) => e.href === "#/x/5").length, 1);
});

test("recordVisit ignores the home page and addresses with no label", () => {
  assert.deepEqual(recordVisit([], { href: "#/home", label: "首页" }), []);
  assert.deepEqual(recordVisit([], { href: "#/x", label: "" }), []);
});
