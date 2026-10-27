import assert from "node:assert/strict";
import test from "node:test";

import { answerLines, groupFigure, measureOf } from "./ontologyStudioModel.js";

const measure = (over = {}) => ({ field: "金额", op: "sum", value: 4631003200, counted: 3000, skipped: 0, ...over });

test("a total says what it added and how many values it read", () => {
  assert.deepEqual(answerLines({ status: "answered", answer: { total: 3000, measure: measure() } }),
    ["“金额”合计 4,631,003,200（读到 3000 个值）"]);
});

test("skipped values are named in the same line, never silently treated as zero", () => {
  assert.deepEqual(answerLines({ status: "answered", answer: { total: 10, measure: measure({ op: "average", value: 12.5, counted: 8, skipped: 2 }) } }),
    ["“金额”平均 12.5（读到 8 个值，2 个不是数字或为空，没算进去）"]);
});

test("a grouped total shows each group's number and the whole", () => {
  const lines = answerLines({ status: "answered", answer: { groups: [["USA", 523.06], ["Canada", 303.96]], total_groups: 2, without_value: 0, measure: measure({ value: 827.02, counted: 412 }) } });
  assert.deepEqual(lines, ["USA：523.06", "Canada：303.96", "全部合计 827.02（读到 412 个值）"]);
});

// A period-to-date column grouped by its period: each group is right, and the groups must not be added up, so the answer carries no overall figure.
const periods = {
  query: { start: "financial_transaction", group_by: ["period_end_date"], measure: { field: "gross_outlay", op: "sum" } },
  answer: { groups: [["2024-12-31", 144393033.61, 1213], ["2024-11-30", 24998153.82, 190]], total_groups: 2, without_value: 0 },
};

test("a grouped total with no overall figure shows each group's number and the values behind it, and no whole", () => {
  assert.deepEqual(answerLines({ status: "answered", ...periods }), ["2024-12-31：144,393,033.61（1213 个值）", "2024-11-30：24,998,153.82（190 个值）"]);
  const more = answerLines({ status: "answered", query: periods.query, answer: { ...periods.answer, total_groups: 5, without_value: 4, unread_groups: { count: 1, examples: ["2024-10-31"] } } });
  assert.deepEqual(more.slice(2), ["另有 3 组未列出", "另有 1 组一个能读成数字的值都没有，不算作 0，没有排进来（例如 2024-10-31）", "4 个没有这个值"]);
  assert.ok(![...answerLines({ status: "answered", ...periods }), ...more].some((l) => l.includes("全部")));
});

test("the measure of an answer is its own, else the question's when the answer is grouped and carries none", () => {
  assert.deepEqual(measureOf({ status: "answered", ...periods }), { field: "gross_outlay", op: "sum" });
  assert.deepEqual(measureOf({ query: { measure: { derived: "金额", op: "average" } }, answer: { groups: [] } }), { field: "金额", op: "average" });
  assert.equal(measureOf({ query: periods.query, answer: { total: 4 } }), null);   // not grouped and no measure on it: nothing was added up
  assert.equal(measureOf({ query: periods.query, answer: null }), null);   // refused: there is no answer to describe
  assert.equal(measureOf({ query: { start: "x" }, answer: { groups: [["甲", 2]] } }), null);
  assert.equal(measureOf({ query: periods.query, answer: { groups: [], measure: measure() } }).value, 4631003200);
});

test("a measure read from the question names its column without the table, as the answer's own measure does", () => {
  const asked = (field) => ({ query: { measure: { field, op: "sum" } }, answer: { groups: [] } });
  assert.deepEqual(measureOf(asked("financial_rows.gross_outlay")), { field: "gross_outlay", op: "sum" });
  assert.deepEqual(measureOf(asked("gross_outlay")), { field: "gross_outlay", op: "sum" });
  assert.equal(measureOf(asked("awards.items[].price")).field, "items[].price");   // only the table is dropped from a path inside a list
  assert.equal(measureOf(asked("items[].price")).field, "items[].price");   // a bare path inside a list has no table to drop
  assert.equal(measureOf({ query: { measure: { derived: "含税.金额", op: "sum" } }, answer: { groups: [] } }).field, "含税.金额");   // a derived measure's name is its own
});

test("the figure beside a bar is a share with its denominator, a measure with its values, or the count", () => {
  assert.equal(groupFigure({ status: "answered", ...periods }, periods.answer.groups[0]), "144,393,033.61（1213 个值）");
  assert.equal(groupFigure({ answer: { groups: [], measure: measure() } }, ["USA", 523.06]), "523.06");
  assert.equal(groupFigure({ answer: { groups: [], share: { field: "状态", equals: "逾期" } } }, ["甲", 2, 10]), "2 / 10（20%）");
  assert.equal(groupFigure({ answer: { groups: [] } }, ["甲", 7]), 7);
});
