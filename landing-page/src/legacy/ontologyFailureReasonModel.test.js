import assert from "node:assert/strict";
import test from "node:test";

import { consensusLines } from "./ontologyGraphModel.js";

test("a failed extra run says why", () => {
  const ontology = { object_types: [{ key: "a", label: "合同" }], relations: [] };
  const s = { runs: 2, failed: 1, failures: [{ codes: ["time_field_invalid"] }], types: { a: 2 }, relations: {}, elsewhere: { types: [], relations: [] } };
  assert.equal(consensusLines(ontology, s, { time_field_invalid: "时间字段不对" })[0], "另外一次没有成功（时间字段不对），只比了 2 次");
  const crashed = { ...s, failures: [{ error: "TimeoutError: read timed out" }] };
  assert.equal(consensusLines(ontology, crashed, {})[0], "另外一次没有成功（模型请求出错），只比了 2 次");
});
