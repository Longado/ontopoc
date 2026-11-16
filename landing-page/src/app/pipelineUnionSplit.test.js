import assert from "node:assert/strict";
import test from "node:test";

import { KIND_LABEL, cardFlags, inputsOf, kindLine, layout, newStep, operatorTitle, orphans, readableSteps, removeStep, splitLines, stepSummary, stepTitle, unionLines } from "./pipelineModel.js";

const STEPS = [
  { id: "o", type: "input", dataset: "订单" },
  { id: "s1", type: "split", from: "o", branches: [{ id: "大单", where: { all: [{ column: "金额", cmp: "ge", value: "20000" }] } }, { id: "其余", rest: true }] },
  { id: "u1", type: "union", inputs: ["大单", "其余"], missing: "error" },
  { id: "out1", type: "output", from: "u1", name: "合起来" },
];

test("a union reads its inputs and a split its one source; a branch is drawn as its split", () => {
  assert.equal(KIND_LABEL.union, "合并");
  assert.equal(KIND_LABEL.split, "拆分");
  assert.deepEqual(inputsOf(STEPS[2]), ["大单", "其余"]);
  assert.deepEqual(inputsOf(STEPS[1]), ["o"]);
  const drawn = layout(STEPS);
  assert.deepEqual(drawn.edges, [{ from: "o", to: "s1" }, { from: "s1", to: "u1" }, { from: "u1", to: "out1" }]);   // two branches into one union: one line
  assert.equal(drawn.nodes.u1.col, 2);
  assert.deepEqual(orphans(STEPS), []);   // the split feeds the output through its branches
});

test("titles and the list of what a step can read name the branches", () => {
  assert.equal(stepTitle(STEPS[2], STEPS), "大单、其余");
  assert.equal(stepTitle(STEPS[1], STEPS), "大单 / 其余");
  assert.equal(kindLine(STEPS[1]), "拆分");
  assert.deepEqual(readableSteps(STEPS.slice(0, 2)).map((r) => [r.id, r.label]), [["o", "输入：订单"], ["大单", "拆分的分支：大单"], ["其余", "拆分的分支：其余"]]);
});

test("a split cannot be removed while a step reads one of its branches", () => {
  assert.deepEqual(removeStep({ steps: STEPS }, "s1").blocked, ["u1"]);
});

test("new union and split steps start from the step selected", () => {
  const u = newStep(STEPS.slice(0, 1).concat({ id: "c", type: "input", dataset: "旧订单" }), "union", "c");
  assert.deepEqual([u.type, u.inputs, u.missing], ["union", ["c", "o"], "error"]);
  const s = newStep(STEPS.slice(0, 1), "split", "o");
  assert.equal(s.from, "o");
  assert.equal(s.branches.length, 2);
  assert.equal(s.branches[1].rest, true);
  assert.notEqual(s.branches[0].id, s.branches[1].id);
});

test("what a union and a split did, in words, and the card's warnings", () => {
  const union = { type: "union", rows_in: [57, 160], rows_out: 217, union: { filled_empty: { 编号: 160 }, same_rows: { count: 57, examples: [{ 订单号: "DD1" }] } } };
  assert.deepEqual(unionLines(union.union), ["57 行在不止一个输入里都有，后面求和会算两次", "编号：160 行没有这一列，留空"]);
  assert.deepEqual(cardFlags(union).map((f) => f.text), ["57 行重复"]);
  const split = { type: "split", rows_in: [160], split: { branches: [{ id: "大单", rows: 57, empty_condition: 2, also_matched: 0 }, { id: "超大单", rows: 0, empty_condition: 0, also_matched: 9 }], unassigned: 101 } };
  assert.deepEqual(splitLines(split.split), ["大单：57 行（2 行条件字段是空的，没进这个分支）", "超大单：0 行（9 行也满足，但已经进了前面的分支）", "101 行没进任何分支，不会往下走"]);
  assert.deepEqual(cardFlags(split).map((f) => f.text), ["101 行没进任何分支"]);
});

test("the confirm screen says what a union and a split do, branch by branch", () => {
  assert.deepEqual(stepSummary(STEPS[2], STEPS), ["把 大单、其余 的行接在一起，按列名对上", "有一步缺列就不合并"]);
  assert.deepEqual(stepSummary({ ...STEPS[2], missing: "empty", source_column: "来源" }, STEPS), ["把 大单、其余 的行接在一起，按列名对上", "缺的列留空", "加一列「来源」标出每行来自哪一步"]);
  assert.deepEqual(stepSummary(STEPS[1], STEPS), ["读 订单，每行进第一个满足条件的分支", `大单：${operatorTitle({ op: "filter", where: STEPS[1].branches[0].where })}`, "其余：其余的行"]);
});

test("a step added while a split is selected reads its branches, never the split itself", () => {
  const steps = STEPS.slice(0, 2);
  assert.deepEqual(newStep(steps, "union", "s1").inputs, ["大单", "其余"]);   // putting the branches back together
  assert.equal(newStep(steps, "transform", "s1").from, "大单");
  assert.equal(newStep(steps, "output", "s1").from, "大单");
  assert.equal(newStep(steps, "join", "s1").left, "大单");
  assert.equal(newStep(steps, "llm", "s1").from, "大单");
});
