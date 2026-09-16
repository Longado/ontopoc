import assert from "node:assert/strict";
import test from "node:test";

import { ACCEPTANCE_LABELS, acceptanceSummary, canAccept, savedAcceptance } from "./ontologyAcceptanceModel.js";

const item = (over = {}) => ({ question: "每个客户有多少订单？", query: { start: "order" }, status: "answered", ...over });

test("a broken query is named apart from the other ways an answer can be missing", () => {
  assert.equal(ACCEPTANCE_LABELS.broken, "查询失效");
  assert.equal(ACCEPTANCE_LABELS.answered, "能回答");
});

test("only a question a person has seen answered can be fixed, and at most three", () => {
  const run = (items) => ({ saved_as: "x.json", evaluation: { acceptance: items ? { items } : undefined } });
  assert.equal(canAccept(run(), item()), "");
  assert.equal(canAccept(run(), item({ status: "no_data" })), "只能把已经答出来的问题存为验收问题");
  assert.equal(canAccept(run(), item({ query: null })), "只能把已经答出来的问题存为验收问题");
  assert.equal(canAccept({ evaluation: {} }, item()), "这是示例结果，上传自己的文件后可以存");
  assert.equal(canAccept(run([item(), item(), item()]), item({ question: "别的问题" })), "验收问题最多 3 道，先去掉一道");
  assert.equal(canAccept(run([item()]), item()), "这道已经是验收问题了");
});

test("the saved list is what gets sent back, with the note a person wrote", () => {
  const run = { evaluation: { acceptance: { items: [item({ note: "按订单号计数", answer: { total: 3 }, previous: null, changed: null })] } } };
  assert.deepEqual(savedAcceptance(run), [{ question: "每个客户有多少订单？", query: { start: "order" }, note: "按订单号计数" }]);
  assert.deepEqual(savedAcceptance({ evaluation: {} }), []);
});

test("the summary says how many are answered and how many moved since last time", () => {
  const acceptance = { total: 3, answered: 2, items: [item({ changed: true }), item({ changed: false }), item({ status: "broken", changed: true })] };
  assert.equal(acceptanceSummary(acceptance), "3 道里能答 2 道，2 道和上次不一样");
  assert.equal(acceptanceSummary({ total: 1, answered: 1, items: [item({ changed: null })] }), "1 道里能答 1 道，第一次执行");
});
