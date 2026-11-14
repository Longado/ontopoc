import assert from "node:assert/strict";
import test from "node:test";

import { askedItem, codeBody, codeGuess, codeProblem, codeStart, codeWhyWeak, dropFor, meaningNote, openItemsEmpty, relabelGroups, repeatBody, reviewStamp, shownCode } from "./openItemsModel.js";

const unasked = { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, removed_measure: 4176392.96, not_in_question: true };
const paid = (over = {}) => ({ question: "累计付了多少钱？", status: "answered",
  query: { start: "financial_transaction", where: [{ field: "period_end_date", equals: "2024-12-31" }, { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" }] },
  evidence: { filters: [{ field: "period_end_date", equals: "2024-12-31", before: 1921, after: 1455 }, unasked] }, ...over });
const run = (evaluation) => ({ ontology: { object_types: [{ key: "financial_transaction", label: "财务支出行" }], relations: [], status: "auto_built_verified" }, evaluation });
const open = { kind: "model_filter", question: "累计付了多少钱？", filter: { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, removed_measure: 4176392.96 } };

test("a question is read where the service reads it: the fixed one first, else the last time it was asked", () => {
  const older = paid({ answer: { total: 1 } }), latest = paid({ answer: { total: 2 } }), fixed = paid({ answer: { total: 3 } });
  assert.equal(askedItem(run({ asked: [{ items: [older] }, { items: [latest] }], acceptance: { items: [fixed] } }), "累计付了多少钱？"), fixed);
  assert.equal(askedItem(run({ asked: [{ items: [older] }, { items: [latest] }] }), "累计付了多少钱？"), latest);
  assert.equal(askedItem(run({ asked: [{ items: [older] }, { error: "模型没有返回", items: [] }] }), "累计付了多少钱？"), older);
  assert.equal(askedItem(run({ asked: [{ items: [older] }] }), "没问过的题"), null);
  assert.equal(askedItem(run({}), "累计付了多少钱？"), null);
});

test("the button on a model-filter item drops the entry of the question's own query that the item is about", () => {
  assert.deepEqual(dropFor(run({ asked: [{ items: [paid()] }] }), open), { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" });
});

test("there is nothing to drop when the question or the condition is no longer there, or the item is another kind", () => {
  const asked = run({ asked: [{ items: [paid()] }] });
  assert.equal(dropFor(asked, { ...open, question: "别的题" }), null);
  assert.equal(dropFor(asked, { ...open, filter: { ...open.filter, equals: "别的值" } }), null);
  assert.equal(dropFor(asked, { ...open, kind: "merged" }), null);
  assert.equal(dropFor(asked, { kind: "model_filter" }), null);
});

test("an empty list does not read as nothing wrong when the ontology never passed verification", () => {
  assert.equal(openItemsEmpty(run({})), "代码没有找到要和客户确认的事。");
  const failed = { ...run({}), ontology: { ...run({}).ontology, status: "needs_review" } };
  assert.equal(openItemsEmpty(failed), "本体还没通过核验，代码先不列要确认的事。");
});

test("an empty list that the client has answered in full says so instead of that nothing was found", () => {
  assert.equal(openItemsEmpty(run({}), 3), "要确认的事都已有客户答复（3 件，见下方）。");
  assert.equal(openItemsEmpty(run({}), 0), "代码没有找到要和客户确认的事。");
  assert.equal(openItemsEmpty(run({}), undefined), "代码没有找到要和客户确认的事。");
  const failed = { ...run({}), ontology: { ...run({}).ontology, status: "needs_review" } };
  assert.equal(openItemsEmpty(failed, 3), "本体还没通过核验，代码先不列要确认的事。");
});

test("a condition already dropped and worked out again has nothing left to drop, only the new answer to look at", () => {
  const asked = run({ asked: [{ items: [paid()] }] });
  assert.deepEqual(dropFor(asked, open), { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" });
  assert.equal(dropFor(asked, { ...open, requeried: true }), null);
});

const codeItem = () => ({ kind: "code_meaning", id: "code_meaning:订单.状态码", column: { values: [
  { value: "0", rows: 96, confirmed: null, preselected: false, recommendation: { label: "已交付", description: "", basis: "数据里没看出规律", strong: false } },
  { value: "1", rows: 48, confirmed: null, preselected: false, recommendation: null },
  { value: "2", rows: 16, confirmed: null, preselected: true, recommendation: { label: "已取消", description: "客户取消", basis: "这 16 行的「交付天数」全是空的", strong: true } },
  { value: "3", rows: 9, confirmed: { label: "补货", description: "" }, preselected: false, recommendation: null }] } });

test("a code form starts with what was confirmed and the guesses the data backs, and leaves the weak guesses unselected", () => {
  assert.deepEqual(codeStart(codeItem()), { 0: { label: "", description: "" }, 1: { label: "", description: "" },
    2: { label: "已取消", description: "客户取消" }, 3: { label: "补货", description: "" } });
});

test("a meaning that waits for a second look starts in the box, a confirmed one still wins, and the stamp says who and when", () => {
  const item = codeItem();
  item.column.values[1].waiting = { label: "已交付", description: "货已送到" };
  item.column.values[3].waiting = { label: "旧的", description: "" };
  const form = codeStart(item);
  assert.deepEqual([form[1], form[3]], [{ label: "已交付", description: "货已送到" }, { label: "补货", description: "" }]);
  assert.equal(reviewStamp({ confirmed_by: "王工", confirmed_at: "2026-11-12T08:30:00+00:00" }), "王工 2026-11-12 确认过，换了新数据后对不上");
  assert.equal(reviewStamp({}), "有人 确认过，换了新数据后对不上");
});

test("a weak guess is shown beside its value so one click can take it, a strong one needs no button", () => {
  const [zero, one, two] = codeItem().column.values;
  assert.equal(codeGuess(zero).label, "已交付");
  assert.equal(codeGuess(one), null);
  assert.equal(codeGuess(two), null);
});

test("the answer posted lists every value with what was written, and refuses nothing written at all", () => {
  const item = codeItem();
  const form = { ...codeStart(item), 0: { label: " 已交付 ", description: "" } };
  assert.deepEqual(codeBody(item, form), [{ value: "0", label: "已交付", description: "" }, { value: "1", label: "", description: "" },
    { value: "2", label: "已取消", description: "客户取消" }, { value: "3", label: "补货", description: "" }]);
  const blank = Object.fromEntries(item.column.values.map((v) => [v.value, { label: "", description: "" }]));
  const unconfirmed = { ...item, column: { ...item.column, values: item.column.values.map(({ confirmed, ...v }) => v) } };
  assert.equal(codeProblem(unconfirmed, blank), "至少给一个取值写上含义");
  assert.equal(codeProblem(item, blank), "");   // the item has meanings confirmed: all blank takes them back
  assert.equal(codeProblem(item, form), "");
  assert.equal(codeProblem(item, { ...form, 0: { label: "x".repeat(41), description: "" } }), "取值 0 的含义最多 40 个字");
});

test("a repeated-key choice is posted as its rule, with the column only for keep-latest", () => {
  assert.deepEqual(repeatBody({ rule: "keep_both", column: "x" }), { rule: "keep_both" });
  assert.deepEqual(repeatBody({ rule: "keep_latest", column: "更新日期" }), { rule: "keep_latest", column: "更新日期" });
});

const meanings = { "订单.状态码": { labels: { 2: "已取消" } }, "客户.客户等级": { labels: {} } };

test("a weak guess says whether it is the row count or the lack of a pattern", () => {
  assert.match(codeWhyWeak({ why_weak: "few_rows" }, 3), /这个取值有 3 行.*不到 20/);
  assert.match(codeWhyWeak({ why_weak: "no_pattern" }, 96), /没有别的列/);
  assert.doesNotMatch(codeWhyWeak({ why_weak: "no_pattern" }, 96), /太少/);
});

test("a code is shown with its meaning, or as unconfirmed, and anything else as written", () => {
  assert.equal(shownCode(meanings, "订单.状态码", "2"), "2 = 已取消");
  assert.equal(shownCode(meanings, "订单.状态码", "1"), "1（含义未确认）");
  assert.equal(shownCode(meanings, "订单.金额", "100"), "100");
});

test("a stored answer grouped by a code shows the codes as meanings, once, whichever way the field was written", () => {
  const item = { query: { start: "order", group_by: [{ via: [], field: "状态码" }] } };
  const groups = [["0", 96], ["2", 16]];
  assert.deepEqual(relabelGroups(item, groups, meanings), [["0（含义未确认）", 96], ["2 = 已取消", 16]]);
  assert.deepEqual(relabelGroups(item, relabelGroups(item, groups, meanings), meanings), [["0（含义未确认）", 96], ["2 = 已取消", 16]]);
  assert.deepEqual(relabelGroups({ query: { group_by: [{ field: "订单.状态码" }, { field: "订单.金额" }] } }, [["2 · 100", 1]], meanings), [["2 = 已取消 · 100", 1]]);
  assert.equal(relabelGroups({ query: { group_by: [{ field: "订单.金额" }] } }, groups, meanings), groups);
  const later = { "订单.状态码": { labels: { 0: "已交付", 2: "已取消" } } };   // meanings confirmed after the answer was worked out
  assert.deepEqual(relabelGroups(item, [["0（含义未确认）", 96], ["2（含义未确认）", 16]], later), [["0 = 已交付", 96], ["2 = 已取消", 16]]);
});

test("an attribute that is a code column carries its meanings, or says nobody confirmed them", () => {
  assert.equal(meaningNote(meanings, "订单", "状态码"), "2 = 已取消");
  assert.equal(meaningNote(meanings, "客户", "客户等级"), "含义未确认");
  assert.equal(meaningNote(meanings, "订单", "金额"), "");
});
