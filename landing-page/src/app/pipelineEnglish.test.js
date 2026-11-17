import assert from "node:assert/strict";
import test from "node:test";
import { setLocale } from "./i18n/index.js";
import { KIND_LABEL, aggAutoName, cardFlags, countsText, durationText, friendlyError, operatorTitle, rowChangeText, rowsText, runBlockReason, stepIssues, stepTitle } from "./pipelineModel.js";

setLocale("en");

test("labels, titles and counts read as English", () => {
  assert.equal(KIND_LABEL.join, "Join");
  assert.equal(stepTitle({ type: "join", left: "a", right: "b" }), "a + b");
  assert.equal(rowsText(1), "1 row");
  assert.equal(rowsText(1234), "1,234 rows");
  assert.equal(countsText({ type: "join", rows_in: [160, 9], rows_out: 169 }), "160 + 9 rows → 169 rows");
  assert.equal(rowChangeText({ type: "filter", rows_in: [100], rows_out: 59 }), "−41 rows");
  assert.equal(durationText(8), "8 ms");
  assert.equal(durationText(2500), "2.5 s");
});

test("issues, block reasons, operator sentences and default names are English", () => {
  assert.deepEqual(stepIssues({ type: "input" }), ["Choose a dataset"]);
  assert.equal(runBlockReason({ dirty: true, hasOutput: true }), "Save your changes first");
  assert.equal(runBlockReason({ dirty: false, hasOutput: true, todo: 2 }), "Finish setting up 2 items first");
  assert.equal(operatorTitle({ op: "filter", where: { all: [{ column: "a", cmp: "eq", value: 1 }] } }), "Keep rows that match (1 condition)");
  assert.equal(aggAutoName({ fn: "sum", column: "amount" }), "amount_sum");
  assert.deepEqual(cardFlags({ type: "join", join: { extra_rows: 9, left_unmatched: 0, how: "left" } }).map((f) => f.text), ["9 extra rows: the right side repeats a key"]);
});

test("the service's Chinese messages keep their shape and gain English names", () => {
  const steps = [{ id: "t1", type: "transform", from: "in1", operators: [{ op: "calc", name: "", expression: "" }] }];
  assert.equal(friendlyError("步骤 t1 的第 1 个操作（calc）：表达式不对", steps), "Calculated column：表达式不对");
});
