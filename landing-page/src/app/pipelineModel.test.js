import assert from "node:assert/strict";
import test from "node:test";

import {
  addOperator, addStep, cardFlags, catalogView, copyOperator, countsText, doubledGroupLines, fanOutLines, fieldRef, friendlyError, insertAt, joinVerdictLines, kindLine, layout, markedIds, moveOperator, newOperator, newStep,
  operatorTitle, orphans, pipelineStateText, progressOf, removeOperator, removeStep, sameSpec, setOperator, simpleExpression, statRows, stepTitle, toggleMark,
  allIssues, runBlockReason, runResults, stepIssues, suggestJoinKeys, rowChangeText,
} from "./pipelineModel.js";

const SPEC = {
  steps: [
    { id: "o", type: "input", dataset: "订单" },
    { id: "t", type: "input", dataset: "售后工单" },
    { id: "j", type: "join", left: "o", right: "t", how: "left", on: [{ left: "订单号", right: "订单号" }] },
    { id: "g", type: "transform", from: "j", operators: [newOperator("filter"), newOperator("aggregate")] },
    { id: "out", type: "output", from: "g", name: "客户合计" },
    { id: "x", type: "input", dataset: "客户" },
  ],
};

test("a step stands one column right of the furthest step it reads, and an edge is drawn for each read", () => {
  const { nodes, edges, width, height } = layout(SPEC.steps);
  assert.deepEqual(Object.fromEntries(Object.entries(nodes).map(([id, n]) => [id, [n.col, n.row]])), { o: [0, 0], t: [0, 1], x: [0, 2], j: [1, 0], g: [2, 0], out: [3, 0] });
  assert.deepEqual(edges, [{ from: "o", to: "j" }, { from: "t", to: "j" }, { from: "j", to: "g" }, { from: "g", to: "out" }]);
  assert.equal(width, 4 * 208 + 3 * 56);
  assert.equal(height, 3 * 116 + 2 * 16);
  assert.deepEqual(layout([]), { nodes: {}, edges: [], size: { w: 208, h: 116, gx: 56, gy: 16 }, width: 0, height: 116 });
});

test("an engine message names the step by what it reads or does and the operator in Chinese, and leaves an id it does not know alone", () => {
  const steps = [...SPEC.steps.slice(0, 3), { id: "t1", type: "transform", from: "j", operators: [{ op: "calc", name: "比", expression: "a" }] }];
  assert.equal(friendlyError("步骤 t1 的第 1 个操作（calc）：表达式不对：括号不成对", steps), "计算列：表达式不对：括号不成对");
  assert.equal(friendlyError("步骤 j：读的步骤 zz 还没有定义", steps), "关联「订单 和 售后工单」：读的步骤 zz 还没有定义");
  assert.equal(friendlyError("步骤 nope：不对", steps), "步骤 nope：不对");
  assert.equal(friendlyError("步骤 o 的第 2 个操作（filter）：x", steps), "输入「订单」的第 2 个操作（数据过滤）：x");
  assert.equal(friendlyError(undefined, steps), "");
});

test("a step that feeds no output is an orphan once there is an output, and not before", () => {
  assert.deepEqual(orphans(SPEC.steps), ["x"]);
  assert.deepEqual(orphans(SPEC.steps.slice(0, 4)), []);
});

test("a new step reads the selected one; a join takes the nearest other input as its right side; ids are never reused", () => {
  const join = newStep(SPEC.steps.slice(0, 2), "join", "o");
  assert.deepEqual([join.id, join.left, join.right, join.how, join.null_keys], ["j1", "o", "t", "left", "no_match"]);
  assert.equal(newStep(SPEC.steps, "transform", "j").id, "t1");   // "t" is taken by an input; the prefix is the transform's own
  assert.equal(newStep([{ id: "t1", type: "transform", from: "a", operators: [] }], "transform", null).id, "t2");
  assert.equal(newStep(SPEC.steps, "output", null).from, "x");   // nothing selected: the last step
});

test("removing a step that another reads is refused and names the readers; a draft is never changed in place", () => {
  const before = JSON.stringify(SPEC);
  assert.deepEqual(removeStep(SPEC, "j").blocked, ["g"]);
  assert.equal(removeStep(SPEC, "j").spec, SPEC);
  const gone = removeStep(SPEC, "out");
  assert.deepEqual(gone.spec.steps.map((s) => s.id), ["o", "t", "j", "g", "x"]);
  const grown = addStep(SPEC, { id: "z", type: "input", dataset: "产品" });
  assert.equal(grown.steps.length, 7);
  const firstOutput = grown.steps.findIndex((s) => s.type === "output");
  assert.ok(grown.steps.findIndex((s) => s.id === "z") < firstOutput, "a new step goes in front of the first output so it can be read");
  assert.equal(addStep(SPEC, { id: "o2", type: "output", from: "x", name: "n" }).steps.at(-1).id, "o2");
  assert.equal(JSON.stringify(SPEC), before);
});

test("operators are added, replaced, copied after themselves, moved and removed in a new list each time", () => {
  let spec = addOperator(SPEC, "g", newOperator("dedupe"));
  assert.deepEqual(spec.steps[3].operators.map((o) => o.op), ["filter", "aggregate", "dedupe"]);
  spec = copyOperator(spec, "g", 0);
  assert.deepEqual(spec.steps[3].operators.map((o) => o.op), ["filter", "filter", "aggregate", "dedupe"]);
  spec.steps[3].operators[1].where.all[0].column = "状态码";
  assert.equal(spec.steps[3].operators[0].where.all[0].column, "");   // the copy is its own
  spec = moveOperator(spec, "g", 3, -1);
  assert.deepEqual(spec.steps[3].operators.map((o) => o.op), ["filter", "filter", "dedupe", "aggregate"]);
  assert.equal(moveOperator(spec, "g", 0, -1).steps[3].operators[0].op, "filter");   // the first cannot go up
  spec = setOperator(spec, "g", 2, { op: "dedupe", keys: ["a"], keep: "last", order_by: "b" });
  spec = removeOperator(spec, "g", 0);
  assert.equal(spec.steps[3].operators.length, 3);
  assert.equal(SPEC.steps[3].operators.length, 2);
  assert.ok(sameSpec(SPEC, JSON.parse(JSON.stringify(SPEC))));
  assert.ok(!sameSpec(SPEC, spec));
});

test("each card says what it holds in words", () => {
  assert.equal(stepTitle(SPEC.steps[0]), "订单");
  assert.equal(stepTitle(SPEC.steps[2], SPEC.steps), "订单 和 售后工单");
  assert.equal(stepTitle(SPEC.steps[2]), "o 和 t");
  assert.equal(kindLine(SPEC.steps[2]), "关联，保留左边全部");
  assert.equal(kindLine(SPEC.steps[4]), "输出");
  assert.equal(stepTitle({ ...SPEC.steps[0], version: 2 }), "订单 第 2 版");
  assert.equal(stepTitle(SPEC.steps[3]), "数据过滤、分组统计");
  assert.equal(operatorTitle({ op: "cast", column: "金额文本", to: "decimal", thousands: true }), "「金额文本」转成小数（千分位）");
  assert.equal(operatorTitle({ op: "aggregate", group_by: ["客户编号"], aggregations: [{ fn: "sum", column: "金额", as: "合计" }, { fn: "count" }] }), "按 客户编号 分组：合计、计数");
  assert.equal(operatorTitle({ op: "dedupe", keys: ["订单号"], keep: "last", order_by: "承诺版本" }), "按 订单号 排重，留最后条（按「承诺版本」）");
  assert.equal(operatorTitle(newOperator("filter")), "留下满足条件的行（1 个条件）");
});

test("the picker lists the categories that exist and filters by category and search", () => {
  const catalog = [{ op: "filter", name: "数据过滤", category: "常用", text: "按条件留下行" }, { op: "aggregate", name: "分组统计", category: "汇总", text: "求和、计数" }, { op: "cast", name: "字段转换", category: "类型", text: "转成日期" }];
  assert.deepEqual(catalogView(catalog, null, "").categories, ["常用", "类型", "汇总"]);
  assert.deepEqual(catalogView(catalog, "汇总", "").items.map((c) => c.op), ["aggregate"]);
  assert.deepEqual(catalogView(catalog, null, "计数").items.map((c) => c.op), ["aggregate"]);
  assert.deepEqual(catalogView(catalog, "常用", "计数").items, []);
});

test("a field is written as it is when it reads as one word and in brackets otherwise; the simple form writes the same expression a person would", () => {
  assert.equal(fieldRef("金额"), "金额");
  assert.equal(fieldRef("下单 日期"), "[下单 日期]");
  assert.equal(fieldRef("2026销量"), "[2026销量]");
  assert.equal(fieldRef("and"), "[and]");
  assert.equal(simpleExpression({ left: "金额", op: "*", right: "1.1", rightIsField: false }), "金额 * 1.1");
  assert.equal(simpleExpression({ left: "金额", op: "-", right: "折扣", rightIsField: true }), "金额 - 折扣");
  assert.equal(simpleExpression({ left: "金额", op: "-", right: "abc", rightIsField: false }), "");
  assert.equal(simpleExpression({ left: "", op: "-", right: "1", rightIsField: false }), "");
  assert.deepEqual(insertAt("金额 + ", 5, 5, "round(数值, 2)"), { text: "金额 + round(数值, 2)", caret: 5 + "round(数值, 2)".length });
  assert.deepEqual(insertAt("abc", 1, 2, "X"), { text: "aXc", caret: 2 });
});

const JOIN_NODE = { id: "j", type: "join", rows_in: [160, 45], rows_out: 169, join: { how: "left", extra_rows: 9, left_unmatched: 124, fan_out: { double_counted: [{ column: "金额", without: 100000, with: 120000 }] }, right_fan_out: null } };
const GROUP_NODE = { id: "g", type: "transform", rows_in: [169], rows_out: 30, failures: { cast_failures: 3 }, operators: [{ affected: 0 }, { groups: 30, double_counted: [{ column: "金额", as: "合计", fn: "sum", groups: 1, examples: [{ group: { 客户编号: "KH099" }, with: 15820, true: 12670 }] }] }] };

test("a join card shows both inputs and flags the extra rows and the sums counted twice; a group card names the customer", () => {
  assert.equal(countsText(JOIN_NODE), "160 + 45 行 → 169 行");
  assert.equal(countsText(GROUP_NODE), "169 行 → 30 行");
  assert.equal(countsText({ type: "input", rows_in: [160], rows_out: 160 }), "160 行");
  assert.deepEqual(cardFlags(JOIN_NODE).map((f) => f.level), ["warn", "warn", "note"]);
  assert.deepEqual(fanOutLines(JOIN_NODE.join), ["左边「金额」的合计从 100,000 变成 120,000"]);
  assert.deepEqual(doubledGroupLines(GROUP_NODE.operators[1]), ["KH099：合计算成 15,820，每行只算一次是 12,670"]);
  assert.deepEqual(cardFlags(GROUP_NODE).map((f) => f.text), ["1 组的合计重复计算了行", "3 个值没转成功"]);
  assert.deepEqual(cardFlags({ type: "output", rows_in: [3], rows_out: 3, operators: [], output: { status: { state: "error", text: "错误 (5/7)：缺 a、b" }, duplicate_keys: { count: 4 }, empty_keys: 2 } }).map((f) => f.level), ["bad", "bad", "bad"]);
});

test("a join's verdict says what matched, what was multiplied and what would only match after cleaning", () => {
  const join = { ...JOIN_NODE.join, left_rows: 160, matched_left: 36, left_blank: 0, right_blank: 2, null_keys: "no_match", fan_out: { repeated_keys: 9, double_counted: [{ column: "金额", without: 100, with: 120 }] },
    near_matches: [{ left: "订单号", right: "订单号", count: 3, examples: ["A1", "A2", "A3", "A4"] }] };
  assert.deepEqual(joinVerdictLines(join), [
    "左边 160 行，36 行对上了，124 行没有对上",
    "多出 9 行：9 个键在右边有不止一行",
    "左边「金额」的合计从 100 变成 120",
    "键是空的：左边 0 行，右边 2 行（空值不匹配）",
    "「订单号」有 3 个值去掉空格或按数字读就能和「订单号」对上，例如 A1、A2、A3",
  ]);
  assert.deepEqual(joinVerdictLines(null), []);
});

test("marks belong to one definition version: an edit clears them, and the progress counts only the steps changed", () => {
  const changes = [{ id: "j", change: "MOD" }, { id: "out", change: "ADD" }];
  let marks = toggleMark(null, 3, "j");
  assert.deepEqual(progressOf(changes, marks, 3), { seen: 1, total: 2 });
  marks = toggleMark(marks, 3, "out");
  assert.deepEqual(progressOf(changes, marks, 3), { seen: 2, total: 2 });
  assert.deepEqual(markedIds(marks, 4), []);   // the definition was edited: nothing is marked seen
  assert.deepEqual(markedIds(toggleMark(marks, 3, "j"), 3), ["out"]);
});

test("a pipeline that needs another look says why", () => {
  assert.equal(pipelineStateText({ state: "needs_look", cause_word: "定义改了" }), "需再看：定义改了");
  assert.equal(pipelineStateText({ state: "needs_look" }), "需再看");
  assert.equal(pipelineStateText({ state: "confirmed" }), "已确认");
});

test("statistics before and after are compared per column and a column that came or went shows a dash", () => {
  const before = [{ name: "合计", nulls: 0, distinct: 30, min: 100, max: 5000 }];
  const after = [{ name: "合计", nulls: 0, distinct: 30, min: 100, max: 6000 }, { name: "行数", nulls: 0, distinct: 4, min: 1, max: 9 }];
  assert.deepEqual(statRows(before, after).map((r) => [r.name, r.changed, r.before === "—"]), [["合计", true, false], ["行数", true, true]]);
  assert.equal(statRows(before, before)[0].changed, false);
});

// --- the AI step and the assistant ---

import { aiNodeLine, applyDraft, estimateText, insertField, labelledRow, llmRunText, runCalls, offListLines, rememberPrompt, reviewText, stepSummary } from "./pipelineModel.js";

test("a new AI step reads the selected step, records the model and starts as a classification that ends in 其他", () => {
  const step = newStep([{ id: "t", type: "input" }], "llm", "t", [], "deepseek-flash");
  assert.deepEqual([step.id, step.type, step.from, step.model, step.template, step.categories], ["ai1", "llm", "t", "deepseek-flash", "classify", ["其他"]]);
  assert.equal(stepTitle({ ...step, name: "问题类别" }), "问题类别");
  assert.equal(stepTitle(step), "（还没写新列的名字）");
});

test("a run says how many rows answered, how many came from what was kept, and every kind of row that did not", () => {
  const report = { answered: 30, from_cache: 18, failed: 2, off_list: 1, unanswered: 0, skipped: 3, pending: 0 };
  assert.equal(llmRunText(report), "30 行答了（18 行用的是以前记下的），2 行失败，1 行答的不在列表里，3 行跳过（提示用到的列都是空的）");
  assert.equal(llmRunText({ ...report, failed: 0, off_list: 0, skipped: 0, from_cache: 0, pending: 5 }), "30 行答了，5 行还没跑");
  assert.deepEqual(offListLines({ off_list_answers: { 质量问题: 3 } }), ["答了「质量问题」，不在列表里：3 行"]);
});

test("the review reads 20 行里 17 行对上 and says when it is old, when no line is set and when it passed", () => {
  const base = { reviewable: true, labelled: 20, matched: 17, total: 20, current: true, min_match: 17, passed: true };
  assert.equal(reviewText(base), "20 行里 17 行对上，达到要求的 17 行");
  assert.equal(reviewText({ ...base, passed: false, min_match: 18 }), "20 行里 17 行对上，没达到要求的 18 行");
  assert.equal(reviewText({ ...base, current: false }), "20 行里 17 行对上（那是改提示之前的结果，要重跑）");
  assert.equal(reviewText({ ...base, min_match: null, passed: false }), "20 行里 17 行对上；还没定要对上几行才算通过");
  assert.equal(reviewText({ ...base, labelled: 10, total: 10, matched: 10, need_labelled: 20, passed: false }), "10 行里 10 行对上；至少要标注 20 行才能通过，现在 10 行");
  assert.equal(reviewText({ ...base, need_labelled: 20, need_match: 17 }), "20 行里 17 行对上，达到要求的 17 行");
  assert.deepEqual(labelledRow({ fields: { 问题描述: "发热" }, expected: "质量缺陷", ai: ["其他"], matched: false, who: "Ann" }), { text: "发热", expected: "质量缺陷", answered: "其他", matched: false, checked: true, who: "Ann" });
  assert.equal(labelledRow({ fields: { a: "x" }, expected: "是", ai: null, status: "absent", matched: false }).answered, "这一行不在现在的数据里");
  assert.equal(reviewText({ reviewable: true, labelled: 0 }), "还没有标注");
  assert.equal(reviewText({ reviewable: false }), "概括没有标准答案，不做样本审核");
  assert.equal(aiNodeLine({ name: "问题类别", review: base, cache: { current: 30 } }), "问题类别：20 行里 17 行对上，达到要求的 17 行；记下了 30 条答案");
});

test("the estimate names calls and characters and claims no money when the service has no price", () => {
  assert.equal(estimateText({ calls: 30, chars_in: 1200, cost: null }), "要调用 30 次，约 1,200 字发给模型；服务没有配单价，没有估价");
  assert.equal(estimateText({ calls: 30, chars_in: 1200, cost: 0.05 }), "要调用 30 次，约 1,200 字发给模型；约 0.05 元");
  assert.equal(estimateText({ calls: 30, chars_in: 1200, cost: null, cap: 500 }), "要调用 30 次，约 1,200 字发给模型；服务没有配单价，没有估价；一次运行最多 500 次");
  assert.deepEqual(runCalls({ a: { estimate: { calls: 300, cap: 500 } }, b: { estimate: { calls: 250, cap: 500 } } }), { calls: 550, cap: 500, over: true });
  assert.equal(runCalls({}), null);
});

test("applying a draft appends its steps to the spec as ordinary steps and leaves the spec it was given alone; recent prompts keep one of each, newest first", () => {
  const spec = { steps: [{ id: "o", type: "input" }] };
  const next = applyDraft(spec, [{ id: "ai1", step: { id: "ai1", type: "transform", from: "o", operators: [] } }]);
  assert.deepEqual(next.steps.map((s) => s.id), ["o", "ai1"]);
  assert.equal(spec.steps.length, 1);
  const list = rememberPrompt([{ text: "a" }, { text: "b" }], { text: "a" }, 2);
  assert.deepEqual(list.map((e) => e.text), ["a", "b"]);
  assert.deepEqual(rememberPrompt([{ text: "x" }, { text: "y" }], { text: "z" }, 2).map((e) => e.text), ["z", "x"]);
});

test("a column goes into the prompt at the caret, written in braces so any name works", () => {
  assert.deepEqual(insertField("看 ", 2, 2, "问题描述"), { text: "看 ${问题描述}", caret: 9 });
  assert.equal(insertField("看 X 吧", 2, 3, "列").text, "看 ${列} 吧");
});

test("an AI step shows on the confirm screen with its template and what it reads, and the card says how many rows have no answer yet", () => {
  const step = { id: "c", type: "llm", from: "t", model: "m", name: "类别", template: "classify", column: "描述", categories: ["甲", "其他"] };
  assert.deepEqual(stepSummary(step, [{ id: "t", type: "input", dataset: "工单" }]), ["读 工单，让 AI 写「类别」（分类）", "模型 m", "按「描述」分成：甲、其他"]);
  assert.deepEqual(cardFlags({ type: "llm", llm: { pending: 4 }, failures: { ai_failed: 2 } }).map((f) => f.text), ["4 行 AI 还没跑", "2 行 AI 没答成"]);
});

test("a new input step is empty: no dataset is picked for the person", () => {
  assert.equal(newStep([], "input", null, ["交付统计", "订单"]).dataset, "");
  assert.equal(newStep(SPEC.steps, "input", "o", ["交付统计"]).id, "in1");
});

test("a step that is not set up yet lists what is missing, in plain words, and a complete one lists nothing", () => {
  assert.deepEqual(stepIssues({ id: "in2", type: "input", dataset: "" }), ["还没选数据集"]);
  assert.deepEqual(stepIssues({ id: "in2", type: "input", dataset: "订单" }), []);
  assert.deepEqual(stepIssues({ id: "j", type: "join", left: "o", right: "t", on: [{ left: "", right: "" }] }), ["关联的列没选齐"]);
  assert.deepEqual(stepIssues({ id: "j", type: "join", left: "o", right: null, on: [{ left: "a", right: "a" }] }), ["右边还没选"]);
  const filter = { op: "filter", where: { all: [{ column: "", cmp: "eq", value: "" }, { column: "状态", cmp: "eq", value: "" }, { column: "状态", cmp: "is_null" }, { column: "金额", cmp: "gt", value: "5" }] } };
  assert.deepEqual(stepIssues({ id: "t", type: "transform", from: "j", operators: [filter] }), ["数据过滤：条件 1 没选列", "数据过滤：条件 2 未填"]);
  assert.deepEqual(stepIssues({ id: "t", type: "transform", from: "j", operators: [] }), ["还没有操作"]);
  assert.deepEqual(stepIssues({ id: "out", type: "output", from: "g", name: "" }), ["还没写数据集的名字"]);
  assert.deepEqual(stepIssues({ id: "t", type: "transform", from: "j", operators: [{ op: "calc", name: "", expression: "" }] }), ["计算列：还没写新列的名字", "计算列：还没写表达式"]);
  assert.deepEqual(allIssues([{ id: "in2", type: "input", dataset: "" }, SPEC.steps[0]]), { in2: ["还没选数据集"] });
});

test("an engine message is said in plain words: no empty quotes, no word twice, the condition named by its number", () => {
  const steps = [{ id: "in1", type: "input", dataset: "订单" }, { id: "t", type: "transform", from: "in1", operators: [{ op: "filter", where: { all: [{ column: "a", cmp: "eq", value: "1" }, { column: "", cmp: "eq", value: "x" }] } }] }];
  assert.equal(friendlyError("步骤 t 的第 1 个操作（filter）：没有列「」", steps), "数据过滤：条件 2 没选列");
  assert.equal(friendlyError("步骤 t 的第 1 个操作（filter）：没有列「」", [steps[0], { ...steps[1], operators: [{ op: "filter" }] }]), "数据过滤：条件 1 没选列");
  assert.equal(friendlyError("步骤 t 的第 1 个操作（filter）：没有列「金额」，是不是「金额数」？", steps), "数据过滤：没有列「金额」，是不是「金额数」？");
  assert.equal(friendlyError("步骤 t 的第 1 个操作（filter）：没选列", steps), "数据过滤：条件 2 没选列");   // what the service says now
  const two = [steps[0], { ...steps[1], operators: [steps[1].operators[0], { op: "aggregate", group_by: [], aggregations: [] }] }];
  assert.equal(friendlyError("步骤 t 的第 2 个操作（aggregate）：已经有叫「行数」的列", two), "分组统计（第 2 个操作）：已经有叫「行数」的列");
  assert.equal(friendlyError("步骤 j：读的步骤里没有列「」", steps), "步骤 j：读的步骤里没选列");
  assert.equal(friendlyError("步骤 in1：数据集「」不存在", steps), "输入「订单」：数据集还没选");
});

test("the join suggests the same-name key, the key-like one first, and says which to put in", () => {
  const left = [{ name: "订单号", type: "text" }, { name: "客户编号", type: "text" }, { name: "金额", type: "integer" }, { name: "状态", type: "text" }];
  const right = [{ name: "工单号", type: "text" }, { name: "订单号", type: "text" }, { name: "客户编号", type: "text" }, { name: "金额", type: "text" }, { name: "状态", type: "text" }];
  const { best, others } = suggestJoinKeys(left, right);
  assert.deepEqual(best, { left: "订单号", right: "订单号" });
  assert.deepEqual(others, [{ left: "客户编号", right: "客户编号" }]);
  assert.deepEqual(suggestJoinKeys([{ name: "a", type: "text" }], [{ name: "b", type: "text" }]), { best: null, others: [] });
  assert.deepEqual(suggestJoinKeys([{ name: "状态", type: "text" }], [{ name: "状态", type: "text" }]), { best: null, others: [] });   // a same-name column that does not look like a key is not put in
});

test("the run button says why it cannot run", () => {
  assert.equal(runBlockReason({ dirty: true, hasOutput: true, todo: 0 }), "有改动还没保存，先保存");
  assert.equal(runBlockReason({ dirty: false, hasOutput: false, todo: 0 }), "要有一个输出步骤才能运行");
  assert.equal(runBlockReason({ dirty: false, hasOutput: true, todo: 2 }), "还有 2 处没配好，先配好");
  assert.equal(runBlockReason({ dirty: false, hasOutput: true, todo: 0, running: true }), "正在运行");
  assert.equal(runBlockReason({ dirty: false, hasOutput: true, todo: 0 }), "");
});

test("a card says how many rows a step added or dropped", () => {
  assert.equal(rowChangeText({ type: "transform", rows_in: [160], rows_out: 120 }), "−40 行");
  assert.equal(rowChangeText({ type: "join", rows_in: [160, 40], rows_out: 169 }), "+9 行");
  assert.equal(rowChangeText({ type: "transform", rows_in: [5], rows_out: 5 }), "行数不变");
  assert.equal(rowChangeText({ type: "input", rows_in: [], rows_out: 5 }), "");
  assert.equal(rowChangeText(undefined), "");
});

test("a run's result is kept for each card: rows out, and failed or not", () => {
  const run = { status: "success", duration_ms: 5, id: 4, nodes: [{ id: "o", type: "input", rows_in: [], rows_out: 9 }, { id: "g", type: "transform", rows_in: [9], rows_out: 2, failures: { cast_failures: 1 } }] };
  assert.deepEqual(runResults(run), { o: { rows: 9, warn: false }, g: { rows: 2, warn: true } });
  assert.deepEqual(runResults(null), {});
});

test("an input with no dataset yet is titled as not chosen, not as an empty string", () => {
  assert.equal(stepTitle({ id: "in2", type: "input", dataset: "" }), "（还没选）");
});
