import assert from "node:assert/strict";
import test from "node:test";

import { answerTags, filterCards, filterQuestions, filled, rowsCsv, stabilityRows, typeMix } from "./visualModel.js";

test("how full a column is, as a share a bar can draw", () => {
  assert.deepEqual(filled({ empty: 13158 }, 28653), { share: 54, empty: 13158, rows: 28653 });
  assert.deepEqual(filled({ empty: 0 }, 150), { share: 100, empty: 0, rows: 150 });
  assert.deepEqual(filled({ empty: 150 }, 150), { share: 0, empty: 150, rows: 150 });
  assert.equal(filled({ empty: 1 }, 0), null);   // nothing read, nothing to draw
});

test("a table's columns summed up by type, most common first", () => {
  assert.deepEqual(typeMix([{ type: "VARCHAR" }, { type: "INTEGER" }, { type: "VARCHAR" }, { type: null }]),
    [["VARCHAR", 2], ["INTEGER", 1], ["全空", 1]]);
});

test("each object and relation in the three builds, as how many of them had it", () => {
  const ontology = { object_types: [{ key: "a", label: "甲" }, { key: "b", label: "乙" }], relations: [{ key: "r", from: "a", to: "b", label: "属于" }] };
  const s = { runs: 3, types: { a: 3, b: 2 }, relations: { r: 1 }, elsewhere: { types: [{ label: "丙", count: 1 }], relations: [] } };
  assert.deepEqual(stabilityRows(ontology, s), [
    { label: "甲", kind: "对象", present: 3, runs: 3, here: true },
    { label: "乙", kind: "对象", present: 2, runs: 3, here: true },
    { label: "甲 属于 乙", kind: "关系", present: 1, runs: 3, here: true },
    { label: "丙", kind: "对象", present: 1, runs: 3, here: false },
  ]);
});

const cards = [{ key: "a", label: "公司", renamed: null, verdict: "ok" }, { key: "b", label: "董監事任職", renamed: "任职", verdict: null }, { key: "c", label: "法人", renamed: null, verdict: "wrong" }];

test("object cards narrow by a name, under either name, and by the person's verdict", () => {
  assert.deepEqual(filterCards(cards, "任", "all").map((c) => c.key), ["b"]);
  assert.deepEqual(filterCards(cards, "", "none").map((c) => c.key), ["b"]);
  assert.deepEqual(filterCards(cards, " ", "wrong").map((c) => c.key), ["c"]);
});

test("questions narrow to the answered ones or the ones that could not be answered", () => {
  const items = [{ status: "answered" }, { status: "query_limit" }, { status: "ontology_gap" }];
  assert.equal(filterQuestions(items, "answered").length, 1);
  assert.equal(filterQuestions(items, "unanswered").length, 2);
  assert.equal(filterQuestions(items, "all").length, 3);
});

test("what an answer counted is said in a few tags, not a paragraph", () => {
  assert.deepEqual(answerTags({ answer: { measure: { op: "sum", field: "金额", counted: 150, skipped: 3 } } }), ["合计 · 金额", "读到 150 个值", "跳过 3 个"]);
  assert.deepEqual(answerTags({ answer: { share: { field: "状态", equals: "逾期" }, groups: [] } }), ["占比 · 状态 = 逾期"]);
  assert.deepEqual(answerTags({ answer: { total: 3 } }), []);
});

test("rows become a CSV a spreadsheet opens, quoting what needs it", () => {
  assert.equal(rowsCsv(["編號", "名稱"], [{ 編號: "03795904", 名稱: "台灣電力, 股份" }, { 編號: "2" }]),
    '﻿編號,名稱\r\n03795904,"台灣電力, 股份"\r\n2,\r\n');
  assert.equal(rowsCsv(["a"], [{ a: 'say "hi"' }]), '﻿a\r\n"say ""hi"""\r\n');
});
