import assert from "node:assert/strict";
import test from "node:test";

import { serviceBlock, serviceError } from "./ontologyStudioModel.js";

test("an outdated local service is told apart from other failures", () => {
  assert.match(serviceError(404, { error: "Unknown ontology endpoint" }), /重启建模服务/);
  assert.equal(serviceError(400, { error: "文件太大" }), "文件太大");
  assert.equal(serviceError(500, null), "服务返回 500");
});

test("a step that only saves needs the service, a step that calls the model also needs the key, and each says which is missing", () => {
  assert.equal(serviceBlock("ready", false), "");
  assert.equal(serviceBlock("ready", true), "");
  assert.equal(serviceBlock("no-key", false), "");
  assert.equal(serviceBlock("no-key", true), "本机服务没有配模型 key，这一步要调用模型");
  assert.equal(serviceBlock("offline", false), "连不上本机建模服务");
  assert.equal(serviceBlock("offline", true), "连不上本机建模服务");
  assert.equal(serviceBlock("checking", false), "连不上本机建模服务");
});
