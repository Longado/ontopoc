import assert from "node:assert/strict";
import test from "node:test";

import { answerView, besideView, definitionHref, isAnswer, namedLines, isThenAnswer, queryExample, queryParams, queryRecord, rangeNotes, readText, scopeText, standingText, staleHeading, staleLines, todayNote } from "./qaModel.js";

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

import { timeWord, timeWarning, criteriaLine, dataAsOf, historyView } from "./qaModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in askEnglish.test.js

test("time words in a question are found", () => {
  for (const [q, w] of [["本月已取消订单有多少", "本月"], ["今年的销售额", "今年"], ["最近30天下单客户", "最近30天"], ["最近3个月的订单", "最近3个月"], ["2026年3月订单", "2026年3月"], ["昨天有几单", "昨天"], ["上个月退款", "上个月"], ["3月份订单", "3月份"]]) assert.equal(timeWord(q), w, q);
  assert.equal(timeWord("已取消订单有多少"), null);
  assert.equal(timeWord(""), null);
  assert.equal(timeWord(undefined), null);
});

test("a time word the query did not use is warned about; one it used, or no time word, is not", () => {
  const noDate = { question: "本月已取消订单有多少", status: "answered", query_text: "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'", query: { type: "order", filters: [{ field: "状态码", op: "eq", value: "9" }] } };
  assert.equal(timeWarning(noDate), "问题里的「本月」没有用上：这个数是全部时间的");
  assert.equal(timeWarning({ ...noDate, query_text: undefined, query: { filters: [] } }), "问题里的「本月」没有用上：这个数是全部时间的");
  assert.equal(timeWarning({ ...noDate, query: { filters: [{ field: "下单日期", op: "gte", value: "2026-11-01" }] }, query_text: undefined }), null);
  assert.equal(timeWarning({ ...noDate, query_text: "SELECT count(o) FROM (o:订单) WHERE o.下单日期 >= '2026-11-01'", query: undefined }), null);
  assert.equal(timeWarning({ ...noDate, question: "已取消订单有多少" }), null);
  assert.equal(timeWarning({ ...noDate, status: "refused" }), null);
  assert.equal(timeWarning({ status: "answered", query_text: "SELECT count(o) FROM (o:订单)" }), null);
});

test("the caliber line says what was counted and as of when", () => {
  assert.equal(criteriaLine({ query_text: "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'" }, "11月16日 08:00"), "按已确认的定义：订单.状态码 = 已取消，数据截至 11月16日 08:00");
  assert.equal(criteriaLine({ query_text: "SELECT count(o) FROM (o:订单)" }, ""), "按已确认的定义：全部订单");
  assert.equal(criteriaLine({}, ""), "");
});

test("the caliber line names the derived property an answer read its values from", () => {
  const record = { query_text: "SELECT sum(c.有效订单金额) AS 合计\nFROM (c:客户)", definitions: [{ kind: "type", name: "客户" }, { kind: "derived", name: "客户.有效订单金额" }] };
  assert.equal(criteriaLine(record, ""), "按已确认的定义：派生属性「客户.有效订单金额」");   // not 全部客户 alone: the amounts are the property's
  assert.equal(criteriaLine({ ...record, query_text: `${record.query_text}\nWHERE c.tier = 'A'` }, ""), "按已确认的定义：派生属性「客户.有效订单金额」，客户.tier = A");
});

test("the data an answer read is named by its version and when that version came, not by when the question was asked", () => {
  const record = { asked_at: "2026-11-20T09:00:00+00:00", data_as_of: [{ dataset: "orders", version: 2, imported_at: "2026-11-20T07:43:00+00:00" }, { dataset: "customers", version: 1, imported_at: "2026-11-20T07:27:00+00:00" }] };
  assert.equal(dataAsOf(record, (iso) => iso.slice(11, 16)), "orders 第 2 版（07:43）、customers 第 1 版（07:27）");
  assert.equal(dataAsOf({ asked_at: "2026-11-20T09:00:00+00:00" }, (iso) => iso), "");   // an answer kept before versions were noted says nothing rather than the question's time
});

test("the caliber line names the view an answer read and no query quoting", () => {
  const view = { evidence: { views: [{ name: "Valid orders", kind: "filter", rows: 107 }] } };
  assert.equal(criteriaLine({ query_text: "SELECT sum(o.amount) AS 合计\nFROM (o:`Order`)", ...view }, ""), "按已确认的定义：视图「Valid orders」");   // not 全部Order: the view chose the rows
  assert.equal(criteriaLine({ query_text: "SELECT count(o) AS 数量\nFROM (o:`Order`)" }, ""), "按已确认的定义：全部Order");
  assert.equal(criteriaLine({ query_text: "SELECT count(o) AS 数量\nFROM (o:`Order`)\nWHERE o.`status code` = 'Delivered'", ...view }, ""), "按已确认的定义：视图「Valid orders」，Order.status code = Delivered");
});

test("a filter the model wrote is said as the model's reading of confirmed code meanings, never as a confirmed definition", () => {
  const meanings = [{ kind: "type", name: "Order" }, { kind: "meaning", name: "Order.status_code" }];
  const ownFilter = { model: "m", definitions: meanings, query_text: "SELECT sum(o.amount) AS 合计\nFROM (o:`Order`)\nWHERE o.status_code NOT IN ('Cancelled', 'Refunded')" };
  assert.equal(criteriaLine(ownFilter, ""), "按已确认的定义：全部Order；模型按已确认的代码含义写的筛选（不是已确认的视图）：Order.status_code NOT IN (Cancelled, Refunded)");
  const view = { evidence: { views: [{ name: "Valid orders", kind: "filter", rows: 95 }] } };
  assert.equal(criteriaLine({ ...ownFilter, ...view, query_text: "SELECT count(o) AS 数量\nFROM (o:`Order`)\nWHERE o.status_code = 'Delivered'" }, ""),
    "按已确认的定义：视图「Valid orders」；模型按已确认的代码含义写的筛选（不是已确认的视图）：Order.status_code = Delivered");   // the view chose the rows; the filter on top is still the model's
  assert.equal(criteriaLine({ model: "m", definitions: [{ kind: "type", name: "客户" }], query_text: "SELECT count(c) FROM (c:客户)\nWHERE c.tier = 'A'" }, "11月20日 08:00"),
    "按已确认的定义：全部客户；模型写的筛选：客户.tier = A，数据截至 11月20日 08:00");   // no code meaning in it: not said to be one
  assert.equal(criteriaLine({ model: "m", definitions: meanings, query_text: "SELECT sum(o.amount) AS 合计\nFROM (o:`Order`)", ...view }, ""), "按已确认的定义：视图「Valid orders」");   // no filter of the model's
});

test("a grouped total has a header over each of its three columns", () => {
  const top = answerView({ answer: { groups: [["C001", 7140, 6], ["C013", 6205, 5]], total_groups: 39, without_value: 0, measure: { field: "amount", op: "sum", value: 119810, counted: 107, skipped: 0 } }, types });
  assert.deepEqual(top.table.head, ["分组", "amount合计", "订单数"]);
  assert.deepEqual(top.table.rows[0], ["C001", "7,140", "6"]);
  assert.equal(top.table.head.length, top.table.rows[0].length);
  const avg = answerView({ answer: { groups: [["C001", 1190, 6]], total_groups: 1, without_value: 0, measure: { field: "amount", op: "avg", value: 1119, counted: 107, skipped: 0 } }, types });
  assert.deepEqual(avg.table.head, ["分组", "amount平均", "订单数"]);
});

test("history rows carry question, status and time", () => {
  assert.deepEqual(historyView({ id: 3, question: "q", status: "answered", asked_at: "t" }, "T"), { id: 3, question: "q", meta: "T 已回答" });
});

test("a viewer's refusal line that names nothing is shown as its text alone, not as a link (the payload a viewer gets while a definition waits)", () => {
  const refusal = { kind: "unsettled", definitions: [{ kind: "type", state: "needs_look", waiting: true, text: "A definition it uses is waiting to be confirmed again" }] };
  assert.deepEqual(namedLines(refusal.definitions), [{ key: "line-0", plain: true, text: "A definition it uses is waiting to be confirmed again" }]);
  assert.equal(definitionHref(undefined), null);
  const named = namedLines([{ id: "objview:有效订单", type: "order", kind: "view", name: "有效订单", state: "needs_look" }, { kind: "type", state: "needs_look", waiting: true, text: "x" }]);
  assert.deepEqual(named.map((l) => [l.key, l.plain ?? false, l.href ?? null]), [["objview:有效订单", false, "#/types/order/views"], ["line-1", true, null]]);
});

test("an answer on every row shows each confirmed view's own number beside it, and an answer on one view shows every row", () => {
  const measure = (value, counted) => ({ total: counted, measure: { field: "金额", op: "sum", value, counted, skipped: 0 } });
  const all = besideView({ status: "answered", types, answer: measure(162960, 150), beside: { views: [{ id: "objview:有效订单", name: "有效订单", confirmed_by: "Bob", answer: measure(119810, 107) }], more: ["视图6", "视图7"] } });
  assert.equal(all.title, "同一个问法，换成别的行来算：");
  assert.deepEqual(all.lines.map((l) => [l.name, l.text, l.of, l.by]), [["有效订单", "金额合计 119,810", "150 个订单里的 107 个", "Bob 确认"]]);
  assert.equal(all.hint, "上面的数算的是你能看到的全部行。");
  assert.equal(all.more, "还有 2 个确认过的视图：视图6、视图7");
  const one = besideView({ status: "answered", types, answer: measure(119810, 107), beside: { views: [{ all_rows: true, name: "订单", answer: measure(162960, 150) }], more: [] } });
  assert.deepEqual(one.lines.map((l) => [l.name, l.text, l.of, l.by]), [["全部订单", "金额合计 162,960", "", ""]]);
  assert.equal(one.hint, "上面的数只算了它读的那个视图的行。");
  assert.equal(besideView({ status: "answered", types, answer: measure(1, 1) }), null);
});

test("a list reads as its count and a table of one page, a code by its meaning, and one object found by its key as that object", () => {
  const columns = [{ column: "订单号", name: "订单号", key: true }, { column: "紧急程度", name: "紧急程度", meanings: { 0: "普通", 1: "加急" } }, { column: "金额", name: "金额" }];
  const answer = { total: 120, objects: { columns, rows: [["DD1", "1", "60000"], ["DD2", "0", null]], page: 2, pages: 3, page_size: 50, order_by: ["订单号"] } };
  for (const [locale, big, coded, page] of [["zh", "120 个订单", "加急（1）", "第 2 页，共 3 页，每页 50 个，一共 120 个"], ["en", "120 订单", "加急 (1)", "Page 2 of 3, 50 a page, 120 in all"]]) {
    setLocale(locale);
    const view = answerView({ answer, types, status: "answered" });
    assert.equal(view.big, big);
    assert.deepEqual(view.objects.head, ["订单号", "紧急程度", "金额"]);
    assert.deepEqual(view.objects.rows, [["DD1", coded, "60000"], ["DD2", locale === "zh" ? "普通（0）" : "普通 (0)", "—"]]);
    assert.deepEqual([view.objects.keys, view.objects.hasPrev, view.objects.hasNext, view.objects.pageText], [[true, false, false], true, true, page]);
  }
  setLocale("zh");
  const one = answerView({ answer: { total: 1, lookup: { 措施编号: "M-17" }, objects: { columns: [{ column: "措施编号", name: "措施编号", key: true }], rows: [["M-17"]], page: 1, pages: 1, page_size: 50, order_by: ["措施编号"] } }, types: [{ id: "measure", name: "处置措施" }], status: "answered" });
  assert.deepEqual([one.big, one.objects.pageText, one.objects.hasNext], ["找到这个处置措施", "", false]);
  assert.equal(answerView({ status: "no_data", reason: "没有措施编号 = M-99 的处置措施" }).note, "没有措施编号 = M-99 的处置措施");   // a key nobody has, or one the reader may not read: said the same
});

test("an answer that compared a date with today says which date today was", () => {
  setLocale("zh");
  assert.equal(todayNote({ today: { date: "2026-06-15", time_zone: "UTC+08:00" } }), "“今天”按 2026-06-15 算（UTC+08:00，服务所在的时区）");
  setLocale("en");
  assert.equal(todayNote({ today: { date: "2026-06-15", time_zone: "UTC+08:00" } }), "\"today\" was taken as 2026-06-15 (UTC+08:00, the service's time zone)");
  assert.equal(todayNote({}), "");
  setLocale("zh");
});
