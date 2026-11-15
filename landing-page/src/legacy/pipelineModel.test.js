import assert from "node:assert/strict";
import test from "node:test";

import { fanOutLines, formProblem, joinRules, nodeLines, pipelineOf, pipelineSources, pipelineTables, setChoice, storedPipelineTables, sourceLabel, startForm } from "./pipelineModel.js";

const tables = [{ name: "订单", rows: 160, columns: ["订单号", "客户编号", "金额"] }, { name: "售后工单", rows: 45, columns: ["工单号", "订单号"] }, { name: "产品", rows: 12, columns: ["产品编号"] }];
const views = [{ name: "有效订单", state: "confirmed", columns: [{ name: "订单号" }, { name: "状态码_含义" }] }, { name: "订单", state: "confirmed", columns: [{ name: "订单号" }] }, { name: "坏的", state: "unavailable", columns: [] }];
const sources = pipelineSources(tables, views);
const form = { left: "表:订单", right: "表:售后工单", leftKey: "订单号", rightKey: "订单号", how: "left" };
const result = { nodes: [
  { id: "left", type: "input", rows_in: [160], rows_out: 160 }, { id: "right", type: "input", rows_in: [45], rows_out: 45 },
  { id: "joined", type: "join", rows_in: [160, 45], rows_out: 169, join: { how: "left", left_rows: 160, matched_left: 160, extra_rows: 9,
    fan_out: { columns: ["订单号"], repeated_keys: 9, examples: [{ key: { 订单号: "DD20260047" }, left_rows: 1, right_rows: 2 }], double_counted: [{ column: "金额", without: 2726470, with: 2883740 }] } } },
  { id: "out", type: "output", rows_in: [169], rows_out: 169 }] };

test("a view and a table with the same name are two inputs, each said as what it is", () => {
  assert.deepEqual(sources.map((s) => sourceLabel(sources, s.id)), ["表 订单", "表 售后工单", "表 产品", "视图 有效订单", "视图 订单"]);   // an unavailable view is not offered
  assert.deepEqual(sources.find((s) => s.id === "视图:有效订单").columns, ["订单号", "状态码_含义"]);
});

test("the form starts on the first two inputs that share a column, joined on it, and a choice drops a key the new input lacks", () => {
  assert.deepEqual(startForm(sources), form);
  assert.deepEqual(startForm([sources[2]]), { left: "表:产品", right: "", leftKey: "", rightKey: "", how: "left" });
  assert.deepEqual(setChoice(form, sources, { right: "表:产品" }), { ...form, right: "表:产品", rightKey: "" });
  assert.equal(formProblem({ ...form, rightKey: "" }), "两边各选一列来对");
  assert.equal(formProblem({ ...form, right: "视图:订单" }), "");               // a table and a view of the same name are different
  assert.equal(formProblem({ ...form, right: form.left }), "左右要是两个不同的输入");
  assert.equal(formProblem(form), "");
});

test("only tables stored in the workspace with their columns can be joined", () => {
  const listed = pipelineTables([{ name: "订单", rows: 160, checks: { rowsIn: 160 }, fields: [{ path: "订单号" }] }, { name: "坏表", rows: 3, checks: { error: "x" }, fields: [{ path: "a" }] }, { name: "旧", rows: 1, checks: null, fields: null }]);
  assert.deepEqual(listed, [{ name: "订单", rows: 160, columns: ["订单号"] }]);
});

test("a blocked draft has no field list: the workspace's list of stored tables gives the columns", () => {
  assert.deepEqual(storedPipelineTables([{ name: "订单", columns: [{ name: "订单号", orderable: false }, { name: "金额", orderable: true }] }]), [{ name: "订单", columns: ["订单号", "金额"] }]);
  assert.deepEqual(storedPipelineTables(undefined), []);
});

test("the pipeline is plain data: an input per side (a table, or a view named as one), the join, an output", () => {
  assert.deepEqual(pipelineOf(form, sources).steps.map((s) => s.type), ["input", "input", "join", "output"]);
  assert.deepEqual(pipelineOf(form, sources).steps.slice(0, 2), [{ id: "left", type: "input", dataset: "订单" }, { id: "right", type: "input", dataset: "售后工单" }]);
  assert.deepEqual(pipelineOf({ ...form, left: "视图:订单" }, sources).steps[0], { id: "left", type: "input", view: "订单" });
  assert.deepEqual(pipelineOf(form, sources).steps[2], { id: "joined", type: "join", left: "left", right: "right", how: "left", on: [{ left: "订单号", right: "订单号" }] });
});

test("every step says its rows in and out, and a join that made more rows says why", () => {
  assert.deepEqual(nodeLines(result, form, sources).map((l) => l.text), ["表 订单：160 行", "表 售后工单：45 行", "连接（保留表 订单的全部行）：160 行 + 45 行 → 169 行", "输出：169 行，只在这里看，没有写进任何表"]);
  assert.deepEqual(nodeLines(result, form, sources).map((l) => Boolean(l.flagged)), [false, false, true, false]);
  assert.deepEqual(fanOutLines(result.nodes[2], form, sources), [
    "169 行比表 订单自己的 160 行多了 9 行：「订单号」在表 售后工单里有 9 个值重复，表 订单的一行连上了好几行。",
    "例如 DD20260047（表 订单里 1 行，表 售后工单里 2 行）等",
    "表 订单的这些数加起来会重复计算：金额 2,726,470 → 2,883,740"]);
  assert.deepEqual(fanOutLines({ ...result.nodes[1], join: { fan_out: null } }, form, sources), []);
  const inner = { ...result.nodes[2], rows_out: 45, join: { ...result.nodes[2].join, matched_left: 36 } };
  assert.match(fanOutLines(inner, { ...form, how: "inner" }, sources)[0], /^对得上的 36 行表 订单变成了 45 行，多了 9 行/);
});

test("the other direction, near matches and empty keys are said too, and the rules for keys and the row cap are always stated", () => {
  const join = { ...result.nodes[2].join, extra_rows: 0, fan_out: null,
    right_fan_out: { columns: ["订单号"], repeated_keys: 37, examples: [{ key: { 订单号: "DD20260002" }, left_rows: 2, right_rows: 1 }], double_counted: [{ column: "金额", without: 100, with: 150 }] },
    near_matches: [{ left: "订单号", right: "订单号", count: 2, examples: [" DD1", "DD2 "] }], left_blank: 3, right_blank: 0 };
  assert.deepEqual(fanOutLines({ ...result.nodes[2], join }, form, sources), [
    "表 订单在「订单号」上有 37 个值重复，表 售后工单的一行被连了好几次：表 售后工单的这些数加起来会重复计算：金额 100 → 150",
    "例如 DD20260002（表 订单里 2 行，表 售后工单里 1 行）等",
    "表 订单的「订单号」有 2 个值，去掉前后空格或按数字读就能对上表 售后工单的「订单号」，但这里按原文对，没对上（例如 “ DD1”、“DD2 ”）",
    "表 订单有 3 行的对接列是空的，空值不参与对接"]);
  assert.equal(joinRules(1000000), "对列时按原文逐字比：前后空格、1 和 1.0 都算不同；空值不参与对接。一次连接最多产生 1,000,000 行，超过就不运行。");
});
