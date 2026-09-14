import assert from "node:assert/strict";
import test from "node:test";

import { STATUS_LABELS, answerLines, questionSummary } from "./ontologyStudioModel.js";

test("each question says whether the ontology could answer it", () => {
  assert.deepEqual(STATUS_LABELS, { answered: "能回答", no_data: "数据里没有", ontology_gap: "本体缺这一块", query_limit: "查询写法表达不了（不是本体的问题）" });
});

test("answers read as short lines", () => {
  assert.deepEqual(answerLines({ status: "answered", answer: { total: 3 } }), ["共 3 个"]);
  assert.deepEqual(answerLines({ status: "answered", answer: { groups: [["苏州", 5], ["无锡", 2]], total_groups: 4, without_value: 1 } }),
    ["苏州：5", "无锡：2", "另有 2 组未列出", "1 个没有这个值"]);
  assert.deepEqual(answerLines({ status: "ontology_gap", reason: "本体里没有发票" }), []);
});

test("the question round summarises answered over asked", () => {
  assert.equal(questionSummary({ answered: 4, total: 6 }), "能回答 4 / 6 题");
  assert.equal(questionSummary(null), null);
});
