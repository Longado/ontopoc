import assert from "node:assert/strict";
import test from "node:test";

import { serviceBlock, serviceError, serviceReady } from "./ontologyStudioModel.js";

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

test("a step that only saves is ready once a saved run and the service are there, key or no key", () => {
  assert.equal(serviceReady({ saved_as: "x.json" }, "no-key", false), true);
  assert.equal(serviceReady({ saved_as: "x.json" }, "no-key", true), false);
  assert.equal(serviceReady({ saved_as: "x.json" }, "ready", true), true);
  assert.equal(serviceReady({ saved_as: "x.json" }, "offline", false), false);
  assert.equal(serviceReady({}, "ready", false), false);   // an example result is not on the service
  assert.equal(serviceReady(null, "ready", false), false);
});
