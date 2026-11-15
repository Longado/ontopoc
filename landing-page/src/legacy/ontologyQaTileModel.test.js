import assert from "node:assert/strict";
import test from "node:test";

import { overviewTiles, questionPanelCount } from "./ontologyGraphModel.js";

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

test("a question asked again or worked out again counts once, by its latest answer", () => {
  const item = (question, status) => ({ question, status });
  const run = { file: { kind: "table" }, saved_as: "x.json", ontology: { object_types: [], relations: [] },
    evaluation: { data_fit: null, questions: { answered: 6, total: 6, items: Array(6).fill({ status: "answered" }) },
      asked: [{ items: [item("付了多少钱？", "answered"), item("谁是母公司？", "ontology_gap")] }, { items: [item("付了多少钱？", "answered")] }, { items: [item("谁是母公司？", "no_data")] }] } };
  assert.equal(overviewTiles(run).find((t) => t.key === "qa").value, "能回答 7 / 8");
  const worse = { ...run, evaluation: { ...run.evaluation, asked: [{ items: [item("付了多少钱？", "answered")] }, { items: [item("付了多少钱？", "no_data")] }] } };
  assert.equal(overviewTiles(worse).find((t) => t.key === "qa").value, "能回答 6 / 7");
});

test("each questions panel counts only its own questions", () => {
  const item = (question, status) => ({ question, status });
  const run = { file: { kind: "table" }, saved_as: "x.json", ontology: { object_types: [], relations: [] },
    evaluation: { data_fit: null, questions: { answered: 5, total: 6, items: Array(6).fill(item("q", "answered")) },
      asked: [{ items: [item("付了多少钱？", "answered")] }, { items: [item("谁是母公司？", "ontology_gap")] }] } };
  assert.equal(questionPanelCount(run, "mine"), "能回答 1 / 2");
  assert.equal(questionPanelCount(run, "model"), "能回答 5 / 6");
  const none = { ...run, evaluation: { ...run.evaluation, questions: null, asked: [] } };
  assert.equal(questionPanelCount(none, "mine"), null);
  assert.equal(questionPanelCount(none, "model"), "还没出题");
});
