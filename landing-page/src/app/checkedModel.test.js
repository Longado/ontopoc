import assert from "node:assert/strict";
import test from "node:test";

import { answerNumber, cardNumber, checkDetail, checkLine, checkWord, summaryText } from "./checkedModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");

const STANDING = { confirmed: true, lines: [] };

test("the four marks of a checked number, in a word", () => {
  assert.deepEqual(["same", "moved", "refused", "differs"].map(checkWord), ["一致", "变了", "拒答", "不一致"]);
});

test("a builder reads the team's number and its source; a viewer only who checked it and when", () => {
  const full = { status: "same", trusted: 119810, then: 119810, now: 119810, note: "财务 10 月报表", by: "Bob", at: "2026-11-20T08:00:00+00:00", moved: [] };
  const line = checkLine(full);
  assert.match(line, /^团队的数 119,810 · 财务 10 月报表 · Bob · /);
  assert.match(line, /2026/);
  const viewer = checkLine({ status: "same", by: "Bob", at: "2026-11-20T08:00:00+00:00" });
  assert.match(viewer, /^Bob · /);
  assert.doesNotMatch(viewer, /团队的数|财务/);
});

test("what moved, what refuses and what differs is said plainly, and nothing for a match or for a viewer", () => {
  assert.equal(checkDetail({ status: "same", trusted: 5, then: 5, now: 5, moved: [] }), "");
  assert.equal(checkDetail({ status: "moved", trusted: 119810, then: 119810, now: 118400, moved: [{ kind: "dataset", name: "订单", from: 1, to: 2 }, { kind: "definition", name: "有效订单", from: 3, to: 4 }] }),
    "核对时 OntoPoc 算的是 119,810，现在是 118,400；从那以后变了：订单 第 1 版 → 第 2 版、有效订单 第 3 版 → 第 4 版");
  assert.equal(checkDetail({ status: "moved", trusted: 7, then: 7, now: 8, moved: [] }), "核对时 OntoPoc 算的是 7，现在是 8");
  assert.equal(checkDetail({ status: "refused", trusted: 7, then: 7, now: null, reason: "含义「订单.状态码」：需要再看", moved: [] }), "现在拒答：含义「订单.状态码」：需要再看");
  assert.equal(checkDetail({ status: "differs", trusted: 162960, then: 119810, now: 119810, moved: [] }), "OntoPoc 算的是 119,810，和团队的数不一样（核对时就不一样）");
  assert.equal(checkDetail({ status: "moved", by: "Bob", at: "2026-11-20" }), "");   // a viewer is sent no numbers
  assert.equal(checkDetail({ status: "refused", trusted: 7, then: 7, now: null, reason: "含义「订单.状态码」：需要再看", moved: [] }, { reasonShown: true }), "现在拒答，原因见上面的灰色说明");   // a grey card already says why
});

test("the line at the top of a board, only when something was checked or a filter keeps the checks apart", () => {
  assert.equal(summaryText({ total: 3, same: 1, moved: 1, refused: 0, differs: 1, text: "3 个数核对过：1 一致、1 变了、0 拒答、1 不一致" }), "3 个数核对过：1 一致、1 变了、0 拒答、1 不一致");
  assert.equal(summaryText({ total: 0, same: 0, moved: 0, refused: 0, differs: 0, text: "" }), "");
  assert.equal(summaryText(undefined), "");
});

test("a card or an answer can be checked only when it shows one number that stands on confirmed definitions", () => {
  const ok = { status: "ok", chart: { kind: "number" }, result: { value: 107, standing: STANDING, rows_limited: false } };
  assert.equal(cardNumber(ok), 107);
  assert.equal(cardNumber({ ...ok, result: { ...ok.result, standing: { confirmed: false, lines: [] } } }), null);
  assert.equal(cardNumber({ ...ok, result: { ...ok.result, rows_limited: true } }), null);
  assert.equal(cardNumber({ ...ok, chart: { kind: "bar" } }), null);
  assert.equal(cardNumber({ ...ok, status: "waiting" }), null);
  assert.equal(cardNumber({ status: "ok", chart: { kind: "query" }, result: { status: "answered", answer: { total: 16 }, standing: STANDING } }), 16);
  assert.equal(cardNumber({ status: "ok", chart: { kind: "query" }, result: { status: "answered", answer: { total: 2, groups: [] }, standing: STANDING } }), null);
  assert.equal(answerNumber({ id: 4, status: "answered", answer: { total: 160, measure: { value: 1115 } } }), 1115);
  assert.equal(answerNumber({ id: 4, status: "answered", answer: { total: 160, measure: { value: null } } }), null);
  assert.equal(answerNumber({ id: 4, status: "answered", answer: { total: 160, matched: 16, share: { field: "状态码", equals: "2" } } }), null);
  assert.equal(answerNumber({ id: 4, status: "refused" }), null);
  assert.equal(answerNumber({ id: 4, status: "answered", answer: { total: 16 }, limited_by_rule: [{ type: "order" }] }), null);
  assert.equal(answerNumber({ status: "answered", answer: { total: 16 } }), null);   // a query that was not kept is no saved answer
});
