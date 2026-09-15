import assert from "node:assert/strict";
import test from "node:test";

import { progressSteps } from "./ontologyStudioModel.js";

test("the evaluate step says when the question round is running", () => {
  const steps = progressSteps([{ stage: "read" }, { stage: "propose", detail: { attempt: 1 } }, { stage: "verify", detail: { attempt: 1, errors: 0 } },
    { stage: "evaluate" }, { stage: "questions" }], "table");
  const evaluate = steps.find((s) => s.key === "evaluate");
  assert.equal(evaluate.status, "active");
  assert.equal(evaluate.detail, "数据体检已完成，正在出题并用数据回答");
});
