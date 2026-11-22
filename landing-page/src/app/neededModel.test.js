import assert from "node:assert/strict";
import test from "node:test";

import { adoptable, blockingText, canConfirm, confirmHint, distinctText, expectPayload, expectText, outcomeWord, planText, resultLines, runAllowed, stateText } from "./neededModel.js";
import { setLocale } from "./i18n/index.js";

const LISTING = { questions: [{}, {}, {}], limits: { questions: 30, repeats: 5 }, budget: { calls: 300, hours: 24, used: 12, left: 288 }, can_run: { ok: true, why: null } };

test("before a run the page says how many model calls it makes at most and where that sits", () => {
  setLocale("zh");
  assert.equal(planText(LISTING, 2), "这次运行问 3 个问题，每个问 2 次：最多调用模型 6 次。所有运行在任意 24 小时内最多调用模型 300 次，还剩 288 次；运行不占你每小时能问的问题数。");
  setLocale("en");
  assert.equal(planText(LISTING, 1), "This run asks 3 questions, each once: at most 3 model calls. All runs together may make 300 model calls in any 24 hours, and 288 are left. A run does not use the questions you may ask an hour.");
  assert.equal(planText(LISTING, 3), "This run asks 3 questions, each 3 times: at most 9 model calls. All runs together may make 300 model calls in any 24 hours, and 288 are left. A run does not use the questions you may ask an hour.");
});

test("a run that does not fit is said before it is started; the service's own reason comes first", () => {
  setLocale("en");
  assert.deepEqual(runAllowed(LISTING, 5), { ok: true, why: null });
  assert.deepEqual(runAllowed({ ...LISTING, budget: { ...LISTING.budget, left: 8 } }, 3), { ok: false, why: "This run could make 9 model calls and runs have 8 left in 24 hours. Ask fewer times, or run it later." });
  assert.deepEqual(runAllowed({ ...LISTING, can_run: { ok: false, why: "The list is running now." } }, 1), { ok: false, why: "The list is running now." });
});

test("what a question should give, and where its expectation stands", () => {
  setLocale("zh");
  assert.equal(expectText(null), "还没写应该给出什么");
  assert.equal(expectText({ kind: "number", value: 119810 }), "应该是 119,810");
  assert.equal(expectText({ kind: "refused" }), "应该拒答");
  assert.equal(stateText({ state: "none" }), "等人写期望");
  assert.equal(stateText({ state: "proposed", written_by: "Ann" }), "Ann 提出，等另一位确认");
  assert.match(stateText({ state: "confirmed", confirmed_by: "Bob", confirmed_at: "2026-11-22T08:00:00+00:00" }), /^Bob 确认 · 2026/);
  assert.match(stateText({ state: "confirmed", confirmed_by: "Ann", confirmed_at: "2026-11-22T08:00:00+00:00", self_confirmed: true }), /自己确认/);
  assert.equal(stateText({ state: "needs_look", look: [{ kind: "dataset", name: "订单", from: 1, to: 2 }] }), "需要再看：确认之后变了：订单 第 1 版 → 第 2 版");
  setLocale("en");
  assert.equal(expectText({ kind: "number", value: 16 }), "Should be 16");
  assert.equal(stateText({ state: "proposed", written_by: "Ann" }), "Proposed by Ann, waiting for another person to confirm");
  assert.equal(stateText({ state: "needs_look", look: [{ kind: "definition", name: "订单", from: 2, to: 3 }, { kind: "dataset", name: "客户", from: null, to: 1 }] }),
    "Needs another look: changed since it was confirmed: 订单 version 2 → 3, 客户 new since");
});

test("the person who wrote an expectation does not confirm it while two-person confirmation is on", () => {
  setLocale("en");
  assert.equal(canConfirm({ state: "proposed", mine: false }, true), true);
  assert.equal(canConfirm({ state: "needs_look", mine: false }, true), true);
  assert.equal(canConfirm({ state: "proposed", mine: true }, true), false);
  assert.equal(canConfirm({ state: "proposed", mine: true }, false), true);
  assert.equal(canConfirm({ state: "confirmed", mine: false }, true), false);
  assert.equal(canConfirm({ state: "none", mine: false }, true), false);
  assert.equal(confirmHint({ state: "proposed", mine: true }, true), "You wrote this, so someone else confirms it.");
  assert.equal(confirmHint({ state: "proposed", mine: false }, true), "");
});

test("each outcome in a word, in both languages", () => {
  setLocale("zh");
  assert.deepEqual(["passes", "differs", "refused", "no_expectation", "needs_look", "not_run"].map(outcomeWord), ["通过", "不一致", "拒答", "还没有期望", "需要再看", "没有问"]);
  setLocale("en");
  assert.deepEqual(["passes", "differs", "refused", "no_expectation", "needs_look", "not_run"].map(outcomeWord), ["Passes", "Differs", "Refused", "No expectation yet", "Needs another look", "Not asked"]);
});

test("one question that gave two numbers says how many asks gave the expected one and each answer", () => {
  setLocale("en");
  const result = { outcome: "differs", asked: 3, right: 2, expected: { kind: "number", value: 160 }, moved: [],
    distinct: [{ number: 160, status: "answered", times: 2 }, { number: 1234567.5, status: "answered", times: 1 }] };
  assert.equal(distinctText(result.distinct), "160 (2 times), 1,234,567.5 (once)");
  assert.deepEqual(resultLines(result), ["2 of 3 gave the expected number.", "Should be 160; the answers: 160 (2 times), 1,234,567.5 (once)."]);
  setLocale("zh");
  assert.deepEqual(resultLines(result), ["3 次里有 2 次给出了期望的数。", "应该是 160；回答：160（2 次）、1,234,567.5（1 次）。"]);
});

test("each outcome says what a person needs to see", () => {
  setLocale("en");
  assert.deepEqual(resultLines({ outcome: "passes", asked: 1, right: 1, expected: { kind: "number", value: 16 }, distinct: [{ number: 16, status: "answered", times: 1 }] }), ["1 of 1 gave the expected number."]);
  assert.deepEqual(resultLines({ outcome: "passes", asked: 2, right: 2, expected: { kind: "refused" }, distinct: [{ number: null, status: "refused", times: 2 }] }), ["2 of 2 were refused, as expected."]);
  const blocked = { outcome: "refused", asked: 1, right: 0, expected: { kind: "number", value: 144 }, distinct: [{ number: null, status: "refused", times: 1 }],
    reason: "…", blocking: [{ kind: "view", name: "有效订单", state: "checked", who_can_confirm: ["Bob", "管理员"] }] };
  assert.deepEqual(resultLines(blocked), ["Refused, not a wrong number. What blocks it: View “有效订单”: waiting for a second person to confirm; who can confirm: Bob, 管理员"]);
  assert.equal(blockingText({ kind: "meaning", name: "订单.状态码", state: "needs_look", who_can_confirm: [] }), "Meaning “订单.状态码”: needs another look");
  assert.deepEqual(resultLines({ ...blocked, blocking: [], reason: "No query came back." }), ["Refused, not a wrong number: No query came back."]);
  assert.deepEqual(resultLines({ outcome: "no_expectation", asked: 1, right: null, expected: null, distinct: [{ number: 54, status: "answered", times: 1 }],
    answer: { status: "answered", number: 54, query_text: "SELECT count(o) FROM (o:订单)" } }), ["The answer: 54. Check it against the data, then adopt it or write the right number.", "SELECT count(o) FROM (o:订单)"]);
  assert.deepEqual(resultLines({ outcome: "needs_look", asked: 1, right: 0, expected: { kind: "number", value: 16 }, distinct: [{ number: 17, status: "answered", times: 1 }],
    moved: [{ kind: "dataset", name: "订单", from: 1, to: 2 }] }), ["Should be 16; the answers: 17 (once).", "Changed since it was confirmed: 订单 version 1 → 2. The expectation goes back to be confirmed again; this is not counted as a failure."]);
  assert.deepEqual(resultLines({ outcome: "not_run", asked: 0, right: null, expected: null, distinct: [] }), ["Not asked: the run stopped before this question."]);
  assert.deepEqual(resultLines({ outcome: "passes", asked: 1, right: 1, expected: { kind: "number", value: 1 }, distinct: [], reworded: true }),
    ["1 of 1 gave the expected number.", "Asked before the question was reworded."]);
});

test("an answer can be adopted when every ask gave the same number", () => {
  assert.equal(adoptable({ outcome: "no_expectation", distinct: [{ number: 54, status: "answered", times: 2 }] }), 54);
  assert.equal(adoptable({ outcome: "no_expectation", distinct: [{ number: 54, status: "answered", times: 1 }, { number: 55, status: "answered", times: 1 }] }), null);
  assert.equal(adoptable({ outcome: "no_expectation", distinct: [{ number: null, status: "refused", times: 1 }] }), null);
  assert.equal(adoptable({ outcome: "differs", distinct: [{ number: 54, status: "answered", times: 1 }] }), null);
  assert.equal(adoptable(null), null);
});

test("the form's expectation becomes what the service reads", () => {
  assert.equal(expectPayload({ kind: "none", value: "" }), null);
  assert.deepEqual(expectPayload({ kind: "number", value: "1,234" }), { kind: "number", value: "1,234" });
  assert.deepEqual(expectPayload({ kind: "refused", value: "9" }), { kind: "refused" });
});
