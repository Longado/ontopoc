import assert from "node:assert/strict";
import test from "node:test";

import { STATUS_LABELS, answerLines, evidenceLines, evidenceTitle, questionSummary } from "./ontologyStudioModel.js";

test("each question says whether the ontology could answer it", () => {
  assert.deepEqual(STATUS_LABELS, { answered: "能回答", no_data: "数据里没有", ontology_gap: "本体缺这一块", query_limit: "这种问法还不支持", needs_derived: "待确认指标" });
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

test("a check pack reads as lines: what each filter removed, which one the model added, which groups merged objects", () => {
  const added = { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, examples: [], removed_measure: 4176392.96, not_in_question: true };
  const untouched = { field: "award_agency_id", equals: "1425", before: 1444, after: 1444, examples: [] };
  const merged = { group: "GREENBERRY INDUSTRIAL LLC", starts: 1, objects: 2, examples: ["P1", "P2"] };
  assert.deepEqual(evidenceLines({ evidence: { filters: [added, untouched], merged: [merged] } }), [
    "按“awarding_subagency”=“BUREAU OF RECLAMATION”筛掉 11 个（1,455 → 1,444），合计 4,176,392.96 没算进去；问题原文里没有这个条件，是模型加的，请核对",
    "按“award_agency_id”=“1425”一个也没筛掉",
    "“GREENBERRY INDUSTRIAL LLC”这一组里，有 1 个对象连到 2 个不同的对象（例如 P1、P2），已只数一次",
  ]);
});

test("examples of the removed objects follow the count, and a filter that removed nothing still says when the model added it", () => {
  assert.deepEqual(evidenceLines({ evidence: { filters: [{ field: "status", equals: "ACTIVE", before: 5, after: 3, examples: ["A3", "A8"] }] } }),
    ["按“status”=“ACTIVE”筛掉 2 个（5 → 3）（例如 A3、A8）"]);
  assert.deepEqual(evidenceLines({ evidence: { filters: [{ field: "a", equals: "1", before: 4, after: 4, examples: [], not_in_question: true }] } }),
    ["按“a”=“1”一个也没筛掉；问题原文里没有这个条件，是模型加的，请核对"]);
  assert.deepEqual(evidenceLines({ evidence: { merged: [{ group: "G", starts: 3, objects: 4, examples: ["x"] }] } }),
    ["“G”这一组里，有 3 个对象各连到不止一个不同的对象，最多 4 个（例如 x），已只数一次"]);
});

test("an item with no check pack has no lines, and the title warns only when a filter was not in the question", () => {
  assert.deepEqual(evidenceLines({ evidence: { folded: [{ field: "credit_limit", table: "invoices", objects: 2, examples: ["A", "C"] }] } }),
    ["“credit_limit”在 2 个对象上各有好几个一样的值（invoices 表，例如 A、C），每个对象只算了一次"]);
  assert.equal(evidenceLines({ evidence: { merged: [{ group: "G", starts: 1, objects: 2, examples: [] }], merged_total: 21 } }).at(-1), "另有 20 组也是这样，没有列出");
  assert.deepEqual(evidenceLines({ status: "answered", answer: { total: 3 } }), []);
  assert.deepEqual(evidenceLines({ evidence: { filters: [] } }), []);
  const f = (not_in_question) => ({ field: "a", equals: "1", before: 2, after: 1, examples: [], ...(not_in_question ? { not_in_question } : {}) });
  assert.equal(evidenceTitle({ evidence: { filters: [f(false), f(false)] } }), "核对");
  assert.equal(evidenceTitle({ evidence: { filters: [f(false), f(true)] } }), "核对：有一个筛选条件问题里没提");
  assert.equal(evidenceTitle({ evidence: { filters: [f(true), f(true)] } }), "核对：有 2 个筛选条件问题里没提");
});
