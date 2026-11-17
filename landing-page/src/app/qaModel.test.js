import assert from "node:assert/strict";
import test from "node:test";

import { answerView, definitionHref, isAnswer, isThenAnswer, queryExample, queryParams, queryRecord, rangeNotes, readText, scopeText, standingText, staleHeading, staleLines } from "./qaModel.js";

const types = [{ id: "order", name: "订单" }];

test("a count, a measure and a share read as one line each, and groups as a table", () => {
  assert.deepEqual(answerView({ answer: { total: 16 }, types, status: "answered" }), { big: "16 个订单", note: "", table: null });
  assert.equal(answerView({ answer: { total: 160, measure: { field: "金额", op: "sum", value: 1115, counted: 160, skipped: 0 } }, types }).big, "金额合计 1,115");
  assert.equal(answerView({ answer: { total: 160, matched: 16, share: { field: "状态码", equals: "2" } }, types }).note, "状态码 = 2 的订单占 10%");
  const grouped = answerView({ answer: { groups: [["华东", 3], ["华北", 1]], total_groups: 2, without_value: 0 }, types });
  assert.deepEqual([grouped.big, grouped.table.head, grouped.table.rows], ["2 组", ["分组", "订单数"], [["华东", "3"], ["华北", "1"]]]);
  assert.equal(answerView({ status: "refused" }), null);
});

test("the orders the relation check counts are counted as orders, not as the first type of the answer", () => {
  assert.equal(answerView({ answer: { total: 3, relation_gap: { many: "订单" } }, types: [{ name: "客户" }, { name: "订单" }] }).big, "3 个订单");
  assert.equal(isAnswer({ status: "no_data" }) && !isAnswer({ status: "refused" }), true);
});

test("a saved answer says which dataset has a newer version and which definition is not as it was", () => {
  assert.deepEqual(staleLines({ stale: [{ dataset: "订单", read: 1, now: 2 }], changed: [{ name: "订单.状态码", state: "needs_look" }, { name: "订单", state: "confirmed" }] }),
    ["订单 有新版本：这条回答读的是第 1 版，现在是第 2 版", "订单.状态码 现在需再看", "订单 在回答之后重新确认过"]);
  assert.deepEqual(staleLines({ stale: [], changed: [] }), []);
  assert.deepEqual(readText({ 订单: 1, 客户: 2 }), ["订单 第 1 版", "客户 第 2 版"]);
});

test("a saved answer whose definition needs a look says so and is shown as the answer of then; newer data alone says the data is newer", () => {
  assert.equal(staleHeading({ changed: [{ name: "订单", state: "needs_look" }], stale: [{ dataset: "订单", read: 1, now: 2 }] }), "依据的定义现在需要再看，下面是当时的答案");
  assert.equal(staleHeading({ changed: [{ name: "订单", state: "confirmed" }], stale: [] }), "依据的定义在回答之后重新确认过，下面是当时的答案");
  assert.equal(staleHeading({ changed: [], stale: [{ dataset: "订单", read: 1, now: 2 }] }), "数据有新版本，这条回答是旧的");
  assert.equal(staleHeading({ changed: [], stale: [] }), "");
  assert.equal(isThenAnswer({ changed: [{ name: "订单", state: "needs_look" }] }) && !isThenAnswer({ changed: [], stale: [{ dataset: "订单" }] }), true);
  assert.deepEqual(staleLines({ changed: [{ name: "有效订单", state: null }] }), ["有效订单 已经不在了"]);
});

test("a definition links to its own page and a refusal says where it stands", () => {
  assert.equal(definitionHref("enum:order:状态码"), "#/types/order");
  assert.equal(definitionHref("objtype:order"), "#/types/order");
  assert.equal(definitionHref("relation:order_customer"), "#/relations/order_customer");
  assert.equal(definitionHref("objview:有效订单", "order"), "#/types/order/views");
  assert.equal(standingText({ state: "needs_look", reason: "取值变了" }), "取值变了");
  assert.equal(standingText({ state: "checked", proposed_by: "Ann" }), "Ann 提出，还没有另一位确认");
  assert.equal(scopeText({ types: [1, 2, 3] }), "范围：3 个已确认的对象类型");
});

test("the query box starts from a query that runs on the first type in scope, and none when nothing is in scope", () => {
  assert.equal(queryExample({ types: [{ id: "order", name: "订单" }, { id: "customer", name: "客户" }] }), "SELECT count(x) AS 数量\nFROM (x:订单)");
  assert.equal(queryExample({ types: [] }), "");
  assert.equal(queryExample(null), "");
});

test("a query's result reads as an answer card, and a refusal with no definitions or steps still reads", () => {
  const ran = queryRecord({ status: "answered", answer: { total: 5 }, types, definitions: [{ id: "objtype:order" }], steps: [], datasets: { 订单: 1 }, text: "SELECT count(o) AS 数量\nFROM (o:订单)" });
  assert.equal(answerView(ran).big, "5 个订单");
  assert.equal(ran.text, "SELECT count(o) AS 数量\nFROM (o:订单)");
  const refused = queryRecord({ status: "refused", reason: "没有计算：关系「订单属于客户」现在不能走" });
  assert.deepEqual([refused.definitions, refused.steps, refused.datasets, isAnswer(refused)], [[], [], {}, false]);
});

test("a range says what it could not read, and nothing is said when it read everything", () => {
  const record = { evidence: { filters: [{ field: "金额", range: "金额 > 1000", unreadable: 2, unreadable_examples: ["待定", "n/a"] }, { field: "下单日期", range: "下单日期 >= 2026-01-01" }, { field: "状态码", equals: "2" }] } };
  assert.deepEqual(rangeNotes(record), ["金额 > 1000：2 个值读不成数字或日期，没有算进去（例如 待定、n/a）"]);
  assert.deepEqual(rangeNotes({}), []);
  assert.deepEqual(rangeNotes({ evidence: { filters: [{ range: "金额 > 1", unreadable: 1 }] } }), ["金额 > 1：1 个值读不成数字或日期，没有算进去"]);   // a viewer gets the count, not the values
});

test("a month or year grouping says how many dates it could not read", () => {
  assert.deepEqual(rangeNotes({ answer: { unreadable: { field: "下单日期", count: 3, unreadable_examples: ["待定"] } } }), ["下单日期：3 个值读不成日期，没有分到哪个月或哪一年（例如 待定）"]);
});

test("the query box asks for the parameters its text uses and sends only those", () => {
  assert.deepEqual(queryParams("SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who", { who: "KH001", old: "x" }), { who: "KH001" });
  assert.equal(queryParams("SELECT count(o) FROM (o:订单)", { who: "KH001" }), undefined);   // nothing to send
});

test("a query that finds nothing says so instead of breaking the card", () => {
  const view = answerView({ status: "no_data", reason: "数据里没有满足筛选条件的对象", types: [{ id: "order", name: "订单" }] });
  assert.deepEqual(view, { big: "没有数据", note: "数据里没有满足筛选条件的对象", table: null });
  assert.equal(answerView({ status: "refused" }), null);
});
