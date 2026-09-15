import assert from "node:assert/strict";
import test from "node:test";

import { serviceError } from "./ontologyStudioModel.js";

test("an outdated local service is told apart from other failures", () => {
  assert.match(serviceError(404, { error: "Unknown ontology endpoint" }), /重启建模服务/);
  assert.equal(serviceError(400, { error: "文件太大" }), "文件太大");
  assert.equal(serviceError(500, null), "服务返回 500");
});
