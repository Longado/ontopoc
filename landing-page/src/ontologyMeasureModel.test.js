import assert from "node:assert/strict";
import test from "node:test";

import { answerLines } from "./ontologyStudioModel.js";

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
