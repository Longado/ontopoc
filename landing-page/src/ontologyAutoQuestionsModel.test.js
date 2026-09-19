import assert from "node:assert/strict";
import test from "node:test";

import { progressSteps } from "./ontologyStudioModel.js";
import { qaPlaceFor } from "./workspaceModel.js";

const before = [{ stage: "read" }, { stage: "propose", detail: { attempt: 1 } }, { stage: "verify", detail: { attempt: 1, errors: 0 } }, { stage: "evaluate" }];
const detail = (events) => progressSteps(events, "table").find((s) => s.key === "evaluate").detail;

test("the evaluate step says it is answering the question written as the purpose", () => {
  assert.equal(detail([...before, { stage: "questions" }]), "数据体检已完成，正在回答你在建模目的里写的问题");
});

test("waiting for the stability runs does not claim questions were answered when none were asked", () => {
  assert.equal(detail([...before, { stage: "stability" }]), "正在等另外两次建模，比对哪些每次都有");
});

test("the questions chip opens where the answers are: the person's questions first, the model's round only when it is all there is", () => {
  assert.equal(qaPlaceFor({ evaluation: { asked: [{ items: [{ from_purpose: true }] }] } }), "ask");
  assert.equal(qaPlaceFor({ evaluation: { questions: { items: [{}] } } }), "model");
  assert.equal(qaPlaceFor({ evaluation: {} }), "ask");
});
