import assert from "node:assert/strict";
import test from "node:test";

import { jobOutcome, jobStartedAt } from "./ontologyStudioModel.js";

test("a job still running has no outcome yet; a finished one hands back its run", () => {
  assert.equal(jobOutcome({ state: "running", events: [] }), null);
  const run = { saved_as: "20260918T093140990Z-4e8f95ba.json" };
  assert.deepEqual(jobOutcome({ state: "done", result: run }), { result: run });
});

test("a job cut off by a restart ends with the service's own words, not a spinner", () => {
  const said = "建模服务在这次建模途中重启过，这次作业中断了。请重新上传文件。";
  assert.deepEqual(jobOutcome({ state: "interrupted", error: said }), { error: said });
  assert.deepEqual(jobOutcome({ state: "failed", error: "模型请求失败" }), { error: "模型请求失败" });
  assert.deepEqual(jobOutcome({ state: "failed" }), { error: "建模失败" });
});

test("after a refresh the clock counts from when the job reported its first step", () => {
  assert.equal(jobStartedAt([{ stage: "read", at: "2026-09-18T09:31:40+00:00" }], 5), Date.parse("2026-09-18T09:31:40Z"));
  assert.equal(jobStartedAt([], 5), 5);   // nothing reported yet: count from now
});
