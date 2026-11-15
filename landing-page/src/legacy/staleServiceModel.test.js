import assert from "node:assert/strict";
import test from "node:test";

import { staleNote } from "./ontologyStudioModel.js";

test("a service still running old code is named plainly, with what to do", () => {
  assert.equal(staleNote({ model_ready: true, running: "a1", on_disk: "b2", stale: true }),
    "建模服务还在跑旧代码：它启动之后，后端文件改过。重启建模服务再用，不然看到的是改之前的行为。");
  assert.equal(staleNote({ model_ready: true, running: "a1", on_disk: "a1", stale: false }), "");
  assert.equal(staleNote({ model_ready: true }), "");   // an older service that does not report it
});
