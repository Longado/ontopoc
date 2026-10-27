import assert from "node:assert/strict";
import test from "node:test";

import { askedItem, dropFor, openItemsEmpty } from "./openItemsModel.js";

const unasked = { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, removed_measure: 4176392.96, not_in_question: true };
const paid = (over = {}) => ({ question: "累计付了多少钱？", status: "answered",
  query: { start: "financial_transaction", where: [{ field: "period_end_date", equals: "2024-12-31" }, { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" }] },
  evidence: { filters: [{ field: "period_end_date", equals: "2024-12-31", before: 1921, after: 1455 }, unasked] }, ...over });
const run = (evaluation) => ({ ontology: { object_types: [{ key: "financial_transaction", label: "财务支出行" }], relations: [], status: "auto_built_verified" }, evaluation });
const open = { kind: "model_filter", question: "累计付了多少钱？", filter: { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION", before: 1455, after: 1444, removed_measure: 4176392.96 } };

test("a question is read where the service reads it: the fixed one first, else the last time it was asked", () => {
  const older = paid({ answer: { total: 1 } }), latest = paid({ answer: { total: 2 } }), fixed = paid({ answer: { total: 3 } });
  assert.equal(askedItem(run({ asked: [{ items: [older] }, { items: [latest] }], acceptance: { items: [fixed] } }), "累计付了多少钱？"), fixed);
  assert.equal(askedItem(run({ asked: [{ items: [older] }, { items: [latest] }] }), "累计付了多少钱？"), latest);
  assert.equal(askedItem(run({ asked: [{ items: [older] }, { error: "模型没有返回", items: [] }] }), "累计付了多少钱？"), older);
  assert.equal(askedItem(run({ asked: [{ items: [older] }] }), "没问过的题"), null);
  assert.equal(askedItem(run({}), "累计付了多少钱？"), null);
});

test("the button on a model-filter item drops the entry of the question's own query that the item is about", () => {
  assert.deepEqual(dropFor(run({ asked: [{ items: [paid()] }] }), open), { field: "awarding_subagency", equals: "BUREAU OF RECLAMATION" });
});

test("there is nothing to drop when the question or the condition is no longer there, or the item is another kind", () => {
  const asked = run({ asked: [{ items: [paid()] }] });
  assert.equal(dropFor(asked, { ...open, question: "别的题" }), null);
  assert.equal(dropFor(asked, { ...open, filter: { ...open.filter, equals: "别的值" } }), null);
  assert.equal(dropFor(asked, { ...open, kind: "merged" }), null);
  assert.equal(dropFor(asked, { kind: "model_filter" }), null);
});

test("an empty list does not read as nothing wrong when the ontology never passed verification", () => {
  assert.equal(openItemsEmpty(run({})), "代码没有找到要和客户确认的事。");
  const failed = { ...run({}), ontology: { ...run({}).ontology, status: "needs_review" } };
  assert.equal(openItemsEmpty(failed), "本体还没通过核验，代码先不列要确认的事。");
});
