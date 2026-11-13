import assert from "node:assert/strict";
import test from "node:test";

import { cardEntry, decidedHow, isTyping, movedIndex, reopenedLine, replyAsks, replyForKey, replyProblem, replyRoute, stackLine } from "./reviewStackModel.js";

const reply = (id, needs_text = false) => ({ id, label: id, needs_text });
const unlinked = { id: "unlinked:a", kind: "unlinked", replies: [reply("expected"), reply("incomplete"), reply("not_applicable"), reply("exception", true)] };
const repeated = { id: "repeated_key:c.客户", kind: "repeated_key", replies: [reply("keep_both"), reply("keep_latest"), reply("data_error"), reply("exception", true)] };
const code = { id: "code_meaning:订单.状态码", kind: "code_meaning", replies: [reply("confirm"), reply("not_applicable"), reply("exception", true)] };
const gaps = { id: "data_gaps", kind: "data_gaps", replies: [reply("confirm", true), reply("not_applicable"), reply("exception", true)] };
const form = (over = {}) => ({ text: "", basis: "", column: "", ...over });

test("the progress line says what is left and what is decided, and when everything is decided how many", () => {
  assert.equal(stackLine(7, 4), "还剩 7 件，已定 4 件");
  assert.equal(stackLine(1, 0), "还剩 1 件，已定 0 件");
  assert.equal(stackLine(0, 5), "都定了，共 5 件");
  assert.equal(stackLine(0, 0), "");
});

test("keys 1 to 4 pick the reply in that place on this card and no other key picks one", () => {
  assert.equal(replyForKey(unlinked, "1").id, "expected");
  assert.equal(replyForKey(unlinked, "4").id, "exception");
  assert.equal(replyForKey(code, "3").id, "exception");
  assert.equal(replyForKey(code, "4"), null);   // a card with three replies has no fourth
  assert.equal(replyForKey(unlinked, "5"), null);
  assert.equal(replyForKey(unlinked, "a"), null);
  assert.equal(replyForKey({ id: "x", kind: "unjudged" }, "1"), null);   // settled by doing something: no replies
});

test("J goes on and K goes back, and both stop at the ends", () => {
  assert.equal(movedIndex(0, "j", 3), 1);
  assert.equal(movedIndex(2, "j", 3), 2);
  assert.equal(movedIndex(1, "k", 3), 0);
  assert.equal(movedIndex(0, "k", 3), 0);
  assert.equal(movedIndex(1, "x", 3), 1);
  assert.equal(movedIndex(0, "j", 0), 0);
});

test("a key typed into a box is the box's", () => {
  assert.equal(isTyping({ tagName: "INPUT" }), true);
  assert.equal(isTyping({ tagName: "TEXTAREA" }), true);
  assert.equal(isTyping({ tagName: "SELECT" }), true);
  assert.equal(isTyping({ tagName: "BUTTON" }), false);
  assert.equal(isTyping({ tagName: "DIV", isContentEditable: true }), true);
  assert.equal(isTyping(null), false);
});

test("a code's confirmation and its 'not a code' go to the code endpoints, a repeat rule to its own, everything else to the card", () => {
  assert.equal(replyRoute(code, reply("confirm")), "code");
  assert.equal(replyRoute(code, reply("not_applicable")), "code");
  assert.equal(replyRoute(code, reply("exception")), "card");
  assert.equal(replyRoute(repeated, reply("keep_latest")), "repeat");
  assert.equal(replyRoute(repeated, reply("exception")), "card");
  assert.equal(replyRoute(unlinked, reply("expected")), "card");
  assert.equal(replyRoute(unlinked, reply("not_applicable")), "card");
});

test("an exception and a 'wrong' reply need their words, a repeat rule needs none, a card reply may add some", () => {
  assert.deepEqual(replyAsks(unlinked, reply("exception", true)), { label: "原因", required: true });
  assert.deepEqual(replyAsks(unlinked, reply("wrong", true)), { label: "对的是什么", required: true });
  assert.deepEqual(replyAsks(gaps, reply("confirm", true)), { label: "客户怎么答的", required: true });
  assert.deepEqual(replyAsks(unlinked, reply("incomplete")), { label: "补充说明（选填）", required: false });
  assert.equal(replyAsks(repeated, reply("keep_both")), null);
  assert.equal(replyAsks(code, reply("confirm")), null);
});

test("what stops a reply: no confirmer, a name over 40 characters, missing reason, a 'latest' rule with no column", () => {
  const exception = reply("exception", true);
  assert.equal(replyProblem(unlinked, exception, form({ text: "测试数据" }), ""), "先填确认人");
  assert.equal(replyProblem(unlinked, exception, form({ text: "测试数据" }), "王".repeat(41)), "确认人最多 40 个字");
  assert.equal(replyProblem(unlinked, exception, form(), "王工"), "先写原因");
  assert.equal(replyProblem(unlinked, exception, form({ text: "  " }), "王工"), "先写原因");
  assert.equal(replyProblem(unlinked, exception, form({ text: "测试数据" }), "王工"), "");
  assert.equal(replyProblem(unlinked, reply("not_applicable"), form(), "王工"), "");
  assert.equal(replyProblem(repeated, reply("keep_latest"), form(), "王工"), "选一列，按它的大小定哪一行最新");
  assert.equal(replyProblem(repeated, reply("keep_latest"), form({ column: "更新日期" }), "王工"), "");
  assert.equal(replyProblem(repeated, reply("keep_both"), form(), "王工"), "");
  assert.equal(replyProblem(code, reply("confirm"), form(), "王工"), "");
});

test("a kind's own choice is sent as a choice and a general reply as a reply, with the words and the source only when written", () => {
  assert.deepEqual(cardEntry(unlinked, reply("incomplete"), form({ text: " 只导了一季 " })), { id: "unlinked:a", choice: "incomplete", text: "只导了一季" });
  assert.deepEqual(cardEntry(unlinked, reply("exception", true), form({ text: "测试数据", basis: "10-27 会议" })), { id: "unlinked:a", reply: "exception", text: "测试数据", basis: "10-27 会议" });
  assert.deepEqual(cardEntry(unlinked, reply("not_applicable"), form()), { id: "unlinked:a", reply: "not_applicable" });
  assert.deepEqual(cardEntry(gaps, reply("confirm", true), form({ text: "下周补" })), { id: "data_gaps", reply: "confirm", text: "下周补" });
});

test("how a decision was made is said, and nothing is said for an answer that does not carry it", () => {
  assert.equal(decidedHow({ mode: "single" }), "逐件判断");
  assert.equal(decidedHow({ mode: "bulk" }), "批量确认");
  assert.equal(decidedHow({}), "");
  assert.equal(decidedHow(undefined), "");
});

test("an old decision brought back says who made it, what it was, and what changed", () => {
  assert.equal(reopenedLine({ by: "王工", says: "已知例外", text: "是测试单", changes: ["多了取值：9", "取值 2：上次 16 行（共 160 行），现在 80 行（共 224 行）"] }),
    "王工 上次记为“已知例外”（是测试单），现在数据变了：多了取值：9；取值 2：上次 16 行（共 160 行），现在 80 行（共 224 行）。");
  assert.equal(reopenedLine({ by: "王工", says: "不适用", text: "", changes: ["多了内容：x"] }), "王工 上次记为“不适用”，现在数据变了：多了内容：x。");
});
