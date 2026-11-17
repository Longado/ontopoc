// F3 (modeling): the approval warning, the queue's verbs, the tab count, sent-back reasons, relation lines, the preview of a new relation and the name beside a key.
import assert from "node:assert/strict";
import test from "node:test";

import { QUEUE_LEGEND, approveWarning, queueRow } from "./confirmModel.js";
import { objectLabel, objectName } from "./objectModel.js";
import { lineLabel, matchRateText, previewPayload, previewText, sentBackLine } from "./relationModel.js";
import { tabCounts } from "./typeModel.js";

const rel = { element: "relation:order_customer", kind: "relation", title: "订单属于客户", state: "needs_look", can_confirm: true, lines: [] };
const approval = { element: "record:7", kind: "approval", record: 7, title: "改订单状态：DD1", state: "pending", can_confirm: true, lines: [{ ok: true, text: "x" }] };
const pipeline = { element: "pipeline:p", kind: "pipeline", title: "清洗", state: "proposed", can_confirm: true, lines: [] };

test("approving a data change warns that the dataset gets a new version and how many confirmed definitions are rechecked", () => {
  const w = approveWarning({ ...approval, dataset: "订单", readers: 4 });
  assert.match(w, /订单/);
  assert.match(w, /新版本/);
  assert.match(w, /4 个已确认的定义/);
  assert.match(w, /需再看/);
  assert.match(approveWarning({ ...approval, dataset: "订单", readers: 0 }), /没有已确认的定义/);
  assert.match(approveWarning({ ...approval, dataset: "订单", readers: null }), /已确认的定义会重新检查/);
  assert.equal(approveWarning(rel), "");   // a definition's confirmation writes no data
});

test("the queue row says which verb it uses, and a pipeline item is labelled as a pipeline", () => {
  assert.equal(queueRow(approval).verb, "批准");
  assert.equal(queueRow(rel).verb, "确认");
  assert.equal(queueRow(pipeline).kind, "管道");
  assert.equal(queueRow(pipeline).tag, "管道：打开看改了什么");
  assert.equal(queueRow(approval).tag, "数据改动：批准后写成新版本");
  assert.equal(queueRow(rel).tag, "定义：确认后问答才会用它");
  assert.match(QUEUE_LEGEND, /批准.*数据/);
  assert.match(QUEUE_LEGEND, /确认.*定义/);
});

test("the tab count of the actions is the list's own count once the list is read", () => {
  const type = { properties: [1], rows: 5 };
  const uses = { used_by: [{ kind: "actions", count: 2 }] };
  assert.equal(tabCounts(type, uses).actions, 2);
  assert.equal(tabCounts(type, uses, { actions: 3 }).actions, 3);
  assert.equal(tabCounts(type, null, { actions: 3 }).actions, 3);
});

test("a relation's line carries its short name, and the match rate stays in the drawer", () => {
  const edge = { name: "订单属于客户", connected: 157, of: 160 };
  assert.equal(lineLabel({ edges: [edge] }), "订单属于客户");
  assert.equal(lineLabel({ edges: [edge, edge] }), "2 个关系");
  assert.equal(lineLabel({ edges: [{ name: "一个非常非常长的关系名字啊" }] }), "一个非常非常长的关系名…");
  assert.equal(matchRateText(edge), "连上 157 / 160 行（98%）");
  assert.equal(matchRateText({ connected: null }), "现在查不了");
});

test("the preview of a new relation says how many rows connect and how many do not", () => {
  assert.equal(previewText({ rows: 160, matched: 157, unmatched: 3, samples: [{ key: "KH099", rows: 3 }], many_name: "订单", one_name: "客户" }), "能连上 157/160 行，3 行找不到（KH099）");
  assert.equal(previewText({ rows: 160, matched: 160, unmatched: 0, samples: [], many_name: "订单", one_name: "客户" }), "160 行都能连上");
  assert.equal(previewText({ rows: 160, matched: 150, unmatched: 0, empty: 10, samples: [] }), "能连上 150/160 行，10 行这一列是空的");
  assert.equal(previewText(null), "");
});

test("a preview is asked for only when both types and both columns are picked", () => {
  assert.equal(previewPayload({ from: "order", to: "", cardinality: "many_to_one", fromColumn: "a", toColumn: "b" }), null);
  assert.deepEqual(previewPayload({ from: "order", to: "customer", cardinality: "many_to_one", fromColumn: "客户编号", toColumn: "客户编号" }),
    { from: "order", to: "customer", cardinality: "many_to_one", from_column: "客户编号", to_column: "客户编号" });
});

test("a sent-back item shows 已退回 with its reason, and nothing for an item that was not sent back", () => {
  assert.equal(sentBackLine({ state: "rejected", reason: "条件写得不清楚，请补充" }), "已退回：条件写得不清楚，请补充");
  assert.equal(sentBackLine({ state: "rejected", reason: null }), "已退回");
  assert.equal(sentBackLine({ state: "confirmed", reason: "x" }), "");
});

test("the name beside a key: a related object shows both", () => {
  assert.equal(objectLabel({ text: "KH022", name: "苏州家电客户22" }), "KH022 · 苏州家电客户22");
  assert.equal(objectLabel({ text: "KH022", name: null }), "KH022");
  assert.equal(objectName([{ name: "客户编号", key: true }, { name: "客户名称" }], ["KH1", "甲"]), "甲");
});
