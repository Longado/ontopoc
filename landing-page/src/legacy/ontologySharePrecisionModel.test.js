import assert from "node:assert/strict";
import test from "node:test";

import { answerLines, sharePercent } from "./ontologyStudioModel.js";

test("a small share is not rounded up to a whole percent", () => {
  assert.equal(sharePercent(2, 300), "0.67");   // not "1"
  assert.equal(sharePercent(1, 3), "33");
  assert.equal(sharePercent(300, 300), "100");
  assert.equal(sharePercent(0, 300), "0");
});

test("the share line carries the same figure as the bars", () => {
  const lines = answerLines({ answer: { total: 300, matched: 2, share: { field: "有条件批准", equals: "Y" } } });
  assert.deepEqual(lines, ["共 300 个，其中 2 个“有条件批准”为“Y”（0.67%）"]);
});
