import assert from "node:assert/strict";
import test from "node:test";
import { setLocale } from "./i18n/index.js";
import { OPERATOR_PARAMS, OP_NAME, columnFrom, extractProblems, newOperator, operatorTitle, stepIssues, stepSummary, stepTitle } from "./pipelineModel.js";

const OP = { op: "extract", column: "statement", separator: "=", part: 1, as: "variable" };
const STEP = { id: "t", type: "transform", from: "in", operators: [OP] };

test("extract starts empty on part 1 and says what is still missing, in both languages", () => {
  assert.deepEqual(newOperator("extract"), { op: "extract", column: "", separator: "", part: 1, as: "" });
  setLocale("zh");
  assert.deepEqual(stepIssues({ ...STEP, operators: [newOperator("extract")] }), ["拆分取段：还没选列", "拆分取段：还没写分隔符", "拆分取段：还没写新列的名字"]);
  assert.deepEqual(stepIssues(STEP), []);
  setLocale("en");
  assert.deepEqual(stepIssues({ ...STEP, operators: [newOperator("extract")] }), ["Extract part: choose a column", "Extract part: write the separator", "Extract part: name the new column"]);
});

test("extract is named and said in a sentence in both languages: the part, the separator as written, the new column", () => {
  setLocale("zh");
  assert.equal(OP_NAME.extract, "拆分取段");
  assert.equal(stepTitle(STEP), "拆分取段");
  assert.equal(operatorTitle(OP), "「statement」按“=”拆开，取第 1 段，写进「variable」");
  assert.equal(operatorTitle({ ...OP, part: "last" }), "「statement」按“=”拆开，取最后一段，写进「variable」");
  assert.deepEqual(stepSummary(STEP, [{ id: "in", type: "input", dataset: "injections" }]).slice(1), ["「statement」按“=”拆开，取第 1 段，写进「variable」"]);
  assert.equal(OPERATOR_PARAMS.extract.length, 3);
  assert.match(OPERATOR_PARAMS.extract.join(" "), /原样/);
  setLocale("en");
  assert.equal(OP_NAME.extract, "Extract part");
  assert.equal(operatorTitle(OP), "Part 1 of “statement” split on “=”, into “variable”");
  assert.equal(operatorTitle({ ...OP, part: "last" }), "The last part of “statement” split on “=”, into “variable”");
  assert.match(OPERATOR_PARAMS.extract.join(" "), /literal/);
});

test("the form refuses what the service refuses before it is sent: a separator of 1 to 10 characters, a part from 1 to 100 or the last", () => {
  setLocale("en");
  assert.deepEqual(extractProblems(OP), []);
  assert.deepEqual(extractProblems({ ...OP, separator: "x".repeat(11) }), ["The separator is 1 to 10 characters"]);
  assert.deepEqual(extractProblems({ ...OP, part: 0 }), ["The part is a whole number from 1 to 100, or the last"]);
  assert.deepEqual(extractProblems({ ...OP, part: "last" }), []);
  assert.deepEqual(extractProblems({ ...OP, separator: " " }), []);   // a space is a separator like any other
  setLocale("zh");
  assert.deepEqual(extractProblems({ ...OP, separator: "" }), []);   // not written yet: stepIssues says so
  assert.deepEqual(extractProblems({ ...OP, part: 101 }), ["第几段要写 1 到 100 的整数，或最后一段"]);
});

test("a column extracted from another says where it came from, and the others read as before", () => {
  const extracted = { name: "variable", type: "text", extracted: { column: "statement", origin: "injections.statement", separator: "=", part: 1 } };
  setLocale("zh");
  assert.equal(columnFrom(extracted), "injections.statement 按“=”拆开的第 1 段");
  assert.equal(columnFrom({ ...extracted, extracted: { ...extracted.extracted, origin: null, part: "last" } }), "statement 按“=”拆开的最后一段");
  assert.equal(columnFrom({ name: "a", origin: "订单.a" }), "订单.a");
  assert.equal(columnFrom({ name: "n", aggregation: { fn: "sum", column: "金额" } }), "sum (金额)");
  assert.equal(columnFrom({ name: "n", aggregation: { fn: "count", column: null } }), "count (整行)");
  assert.equal(columnFrom({ name: "c" }), "");
  setLocale("en");
  assert.equal(columnFrom(extracted), "part 1 of injections.statement split on “=”");
});
