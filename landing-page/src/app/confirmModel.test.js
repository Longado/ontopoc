import assert from "node:assert/strict";
import test from "node:test";

import { batchPlan, batchSummary, queueCounts, queueRow, rejectProblem, sortByProblem } from "./confirmModel.js";

const rel = { element: "relation:order_customer", kind: "relation", title: "订单 → 客户（订单属于客户）", state: "needs_look", can_confirm: true, version: 3, seen: "sig",
  lines: [{ ok: false, text: "数据变了：订单 第 2 版" }, { ok: false, text: "157 行连上了" }, { ok: false, strong: true, text: "3 行订单找不到客户：KH099" }, { ok: true, text: "客户里没有重复" }] };
const type = { element: "objtype:customer", kind: "type", title: "客户", state: "proposed", can_confirm: true, version: 1, lines: [{ ok: true, text: "来自 客户 第 1 版，5 个属性" }] };
const approval = { element: "record:7", kind: "approval", record: 7, title: "改订单状态：DD1", state: "pending", can_confirm: true, can_withdraw: false, lines: [{ ok: true, text: "Ann 想把 DD1 的 状态码 1 → 2" }] };
const pipeline = { element: "pipeline:p", kind: "pipeline", title: "清洗", state: "proposed", can_confirm: true, lines: [] };

test("a queue row: what it is, one summary line, and the real problems apart from it (W3)", () => {
  const row = queueRow(rel);
  assert.equal(row.kind, "关系");
  assert.equal(row.summary, "数据变了：订单 第 2 版");
  assert.deepEqual(row.problems, [{ text: "157 行连上了", level: "warn" }, { text: "3 行订单找不到客户：KH099", level: "error" }]);
  assert.equal(row.hasError, true);
  assert.deepEqual([queueRow(type).summary, queueRow(type).problems, queueRow(type).hasError], ["来自 客户 第 1 版，5 个属性", [], false]);
});

test("each kind of item has the one thing a person can do inline", () => {
  assert.equal(queueRow(rel).mode, "confirm");
  assert.equal(queueRow(approval).mode, "approve");
  assert.equal(queueRow(pipeline).mode, "open");   // a pipeline is confirmed on its own screen
  assert.equal(queueRow({ ...type, kind: "view", new_values: [{ value: "9" }] }).mode, "open");   // new values must be picked first
  assert.equal(queueRow({ ...type, can_confirm: false }).mode, "wait");
  assert.equal(queueRow({ ...type, can_confirm: false, waiting_on: [{ name: "客户" }] }).mode, "blocked");
  assert.equal(queueRow({ ...type, kind: "meaning", state: "needs_look", can_confirm: false }).mode, "repropose");
  assert.equal(queueRow({ ...approval, can_confirm: false, can_withdraw: true }).mode, "withdraw");
});

test("sending back needs a reason, for a definition and for a submission alike", () => {
  assert.equal(rejectProblem("  "), "退回要写理由");
  assert.equal(rejectProblem(""), "退回要写理由");
  assert.equal(rejectProblem("条件写错了"), "");
});

test("counts are what the navigation badge counts: what this person can confirm now", () => {
  const data = { items: [rel, type, approval, { ...type, can_confirm: false }], count: 3 };
  assert.deepEqual(queueCounts(data), { mine: 3, all: 4, text: "共 4 项，其中 3 项你现在能确认" });
  assert.equal(queueCounts({ items: [], count: 0 }).text, "没有要确认的");
  assert.equal(queueCounts({ items: [rel], count: 1 }).text, "共 1 项，其中 1 项你现在能确认");
});

test("items with a real problem come first; the order is otherwise kept", () => {
  assert.deepEqual(sortByProblem([type, rel, approval]).map((i) => i.element), ["relation:order_customer", "objtype:customer", "record:7"]);
});

test("a batch is the picked items that can be confirmed inline, as the calls to make", () => {
  const plan = batchPlan([rel, type, approval, pipeline], new Set([rel.element, type.element, approval.element, pipeline.element]));
  assert.deepEqual(plan, [
    { key: "relation:order_customer", title: "订单 → 客户（订单属于客户）", call: "confirm", element: "relation:order_customer", version: 3, seen: "sig" },
    { key: "objtype:customer", title: "客户", call: "confirm", element: "objtype:customer", version: 1, seen: undefined },
    { key: "record:7", title: "改订单状态：DD1", call: "approve", record: 7 },
  ]);   // the pipeline is not batchable
  assert.deepEqual(batchPlan([type], new Set()), []);
});

test("what a batch did, in a sentence, with each failure named", () => {
  assert.equal(batchSummary([{ title: "a", ok: true }, { title: "b", ok: true }]), "确认了 2 项");
  assert.equal(batchSummary([{ title: "a", ok: true }, { title: "b", ok: false, error: "数据变了" }]), "确认了 1 项；1 项没成：b（数据变了）");
  assert.equal(batchSummary([]), "");
});
