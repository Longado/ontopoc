import assert from "node:assert/strict";
import test from "node:test";

import { acceptItem, acceptanceSummary, canAccept, purposeNote, savedAcceptance } from "./ontologyAcceptanceModel.js";

const answered = { question: "每个客户有多少订单？", query: { start: "order" }, status: "answered" };
const unmet = { question: "上个月延期造成的金额是多少？", query: null, status: "query_limit", reason: "查询还不能限定时间段" };
const run = (items) => ({ saved_as: "x.json", evaluation: { acceptance: items ? { items } : undefined } });

test("a question that came back unanswerable can be fixed too, so the ones that pass cannot hide it", () => {
  assert.equal(canAccept(run(), unmet), "");
  assert.equal(canAccept(run(), { ...unmet, status: "ontology_gap" }), "");
  assert.equal(canAccept(run(), { ...unmet, reason: "" }), "只能把已经答出来的问题存为验收问题");
  assert.equal(canAccept(run(), { ...unmet, status: "no_data" }), "只能把已经答出来的问题存为验收问题");
});

test("what is sent back keeps why an unmet question is unmet", () => {
  const list = acceptItem([], unmet, "客户点名要的");
  assert.deepEqual(list, [{ question: unmet.question, query: null, note: "客户点名要的", status: "query_limit", reason: "查询还不能限定时间段" }]);
  assert.deepEqual(savedAcceptance(run([{ ...list[0], previous: null, changed: null }])), list);
  assert.deepEqual(acceptItem([], answered, " 按订单号计数 "), [{ question: answered.question, query: { start: "order" }, note: "按订单号计数" }]);
});

test("once the same question gets an answer a person agrees with, it takes the unmet one's place", () => {
  const saved = acceptItem([], unmet, "");
  const now = { ...unmet, query: { start: "order" }, status: "answered", reason: undefined };
  assert.equal(canAccept(run(saved), now), "");
  assert.equal(canAccept(run(saved), unmet), "这道已经是验收问题了");
  assert.deepEqual(acceptItem(saved, now, "按月"), [{ question: unmet.question, query: { start: "order" }, note: "按月" }]);
});

test("the summary names the questions that still cannot be answered", () => {
  const acceptance = { total: 3, answered: 2, items: [{ ...answered, changed: null }, { ...answered, changed: null }, { ...unmet, changed: null }] };
  assert.equal(acceptanceSummary(acceptance), "3 道里能答 2 道，1 道现在还答不了，第一次执行");
  assert.equal(acceptanceSummary({ total: 1, answered: 1, items: [{ ...answered, changed: null }] }), "1 道里能答 1 道，第一次执行");
});

test("a confirmation made for another purpose is said to be so", () => {
  const reference = { confirmed: true, purpose: "看清哪些客户经常延期" };
  assert.equal(purposeNote({ purpose: "盘点产品线", evaluation: { reference } }), "上次确认时的建模目的是“看清哪些客户经常延期”，和这次的不一样。上次的判断只是预先填好，不代表对这次的目的也成立，请逐项再看。");
  assert.equal(purposeNote({ purpose: "看清哪些客户经常延期", evaluation: { reference } }), "");
  assert.equal(purposeNote({ purpose: "盘点产品线", evaluation: { reference: { confirmed: true } } }), "");   // an older confirmation did not record its purpose
  assert.equal(purposeNote({ purpose: "盘点产品线", evaluation: {} }), "");
});
