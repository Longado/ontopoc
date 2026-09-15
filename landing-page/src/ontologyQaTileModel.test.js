import assert from "node:assert/strict";
import test from "node:test";

import { overviewTiles } from "./ontologyGraphModel.js";

test("the questions tile counts the questions people asked, not only the model's round", () => {
  const item = (status) => ({ status });
  const run = { file: { kind: "table" }, saved_as: "x.json", ontology: { object_types: [], relations: [] },
    evaluation: { data_fit: null, questions: { answered: 6, total: 6, items: Array(6).fill(item("answered")) },
      asked: [{ items: [item("answered")] }, { items: [item("ontology_gap")] }, { error: "模型请求失败" }] } };
  const qa = overviewTiles(run).find((t) => t.key === "qa");
  assert.equal(qa.value, "能回答 7 / 8");
  assert.equal(qa.tone, "warn");
  assert.equal(qa.hint, "1 题答不了，点开看原因");
});
