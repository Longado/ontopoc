import assert from "node:assert/strict";
import test from "node:test";

import { progressSteps } from "./ontologyStudioModel.js";

const e = (stage, detail = {}) => ({ stage, detail });
const view = (steps) => steps.map((s) => `${s.key}:${s.status}${s.detail ? `(${s.detail})` : ""}`);

test("a table build walks read, propose, verify and evaluate, and says when code sent the model back", () => {
  assert.deepEqual(view(progressSteps([e("read")], "table")), ["read:done", "model:active", "verify:pending", "evaluate:pending"]);
  assert.deepEqual(view(progressSteps([e("read"), e("propose", { attempt: 1 })], "table")),
    ["read:done", "model:active(第 1 次)", "verify:pending", "evaluate:pending"]);
  assert.deepEqual(view(progressSteps([e("read"), e("propose", { attempt: 1 }), e("verify", { attempt: 1, errors: 3 }), e("propose", { attempt: 2 })], "table")),
    ["read:done", "model:active(第 2 次)", "verify:done(第 1 次退回 3 处问题，模型重做)", "evaluate:pending"]);
  assert.deepEqual(view(progressSteps([e("read"), e("propose", { attempt: 1 }), e("verify", { attempt: 1, errors: 0 }), e("evaluate")], "table")),
    ["read:done", "model:done(第 1 次)", "verify:done(第 1 次通过)", "evaluate:active"]);
  assert.deepEqual(view(progressSteps([e("read"), e("evaluate"), e("done")], "table")).map((s) => s.split(":")[1].slice(0, 4)), ["done", "done", "done", "done"]);
});

test("a document build counts its chunks", () => {
  const steps = progressSteps([e("read"), e("chunk", { index: 2, total: 5 })], "document");
  assert.deepEqual(view(steps), ["read:done", "model:active(第 2 / 5 段)", "verify:pending", "evaluate:pending"]);
  assert.equal(steps[1].label, "逐段提取概念和关系");
});
