import assert from "node:assert/strict";
import test from "node:test";

import {
  addOperator, addStep, cardFlags, catalogView, copyOperator, countsText, doubledGroupLines, fanOutLines, fieldRef, insertAt, joinVerdictLines, kindLine, layout, markedIds, moveOperator, newOperator, newStep,
  operatorTitle, orphans, pipelineStateText, progressOf, removeOperator, removeStep, sameSpec, setOperator, simpleExpression, statRows, stepTitle, toggleMark,
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

test("a step that feeds no output is an orphan once there is an output, and not before", () => {
  assert.deepEqual(orphans(SPEC.steps), ["x"]);
  assert.deepEqual(orphans(SPEC.steps.slice(0, 4)), []);
});

test("a new step reads the selected one; a join takes the nearest other input as its right side; ids are never reused", () => {
  const join = newStep(SPEC.steps.slice(0, 2), "join", "o");
  assert.deepEqual([join.id, join.left, join.right, join.how, join.null_keys], ["j1", "o", "t", "left", "no_match"]);
  assert.equal(newStep(SPEC.steps, "transform", "j").id, "t1");   // "t" is taken by an input; the prefix is the transform's own
  assert.equal(newStep([{ id: "t1", type: "transform", from: "a", operators: [] }], "transform", null).id, "t2");
  assert.equal(newStep([], "input", null, ["订单", "客户"]).dataset, "订单");
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
