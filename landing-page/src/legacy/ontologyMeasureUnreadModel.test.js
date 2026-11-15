import assert from "node:assert/strict";
import test from "node:test";

import { answerLines } from "./ontologyStudioModel.js";

const measure = { field: "Count of MORT Measures Worse", op: "average", value: 0.098, counted: 947, skipped: 311 };

test("each measured group says how many values it was computed from, so an average of one does not read as a pattern", () => {
  const lines = answerLines({ answer: { groups: [["联邦政府医院", 2, 1], ["地方医院", 0.29, 73]], total_groups: 2, without_value: 0, measure } });
  assert.deepEqual(lines.slice(0, 2), ["联邦政府医院：2（1 个值）", "地方医院：0.29（73 个值）"]);
});

test("groups with nothing readable are named as unknown, not listed as zero", () => {
  const lines = answerLines({ answer: { groups: [["地方医院", 0.29, 73]], total_groups: 1, without_value: 0, measure,
    unread_groups: { count: 14, examples: ["儿童医院", "精神病院"] } } });
  assert.ok(lines.includes("另有 14 组一个能读成数字的值都没有，不算作 0，没有排进来（例如 儿童医院、精神病院）"));
});

test("results saved before groups carried their counts still read as they did", () => {
  assert.equal(answerLines({ answer: { groups: [["甲", 100]], total_groups: 1, without_value: 0, measure } })[0], "甲：100");
});

test("a total of nothing readable says so instead of printing a number", () => {
  const lines = answerLines({ answer: { total: 3, measure: { field: "金额", op: "sum", value: null, counted: 0, skipped: 3 } } });
  assert.deepEqual(lines, ["“金额”没有一个能读成数字的值（3 个不是数字或为空）"]);
});
