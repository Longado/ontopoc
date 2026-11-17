import assert from "node:assert/strict";
import test from "node:test";
import { afterUpload, updateWays, waysFor } from "./uploadModel.js";

test("on an empty workspace only a new dataset is offered; the updates are folded away", () => {
  assert.deepEqual(waysFor([]).primary.map((w) => w.kind), ["new"]);
  assert.deepEqual(waysFor([]).folded, []);
  const withData = waysFor(["订单"]);
  assert.deepEqual(withData.primary.map((w) => w.kind), ["new"]);
  assert.deepEqual(withData.folded.map((w) => w.kind), ["update_by_key", "overwrite"]);
  for (const w of withData.folded) assert.ok(w.consequence.length > 6);
});

test("a file that matches an existing name, or a preset target, opens the fold", () => {
  assert.equal(updateWays({ kind: null }).open, true);
  assert.equal(updateWays({ kind: "overwrite" }).open, true);
  assert.equal(updateWays({ kind: "new" }).open, false);
});

test("after an upload: view the dataset, or make an object type from it; nothing more for a pure update", () => {
  const made = afterUpload([{ name: "订单", mode: "new", rows: 160 }]);
  assert.deepEqual(made.map((a) => a.label), ["查看数据集", "用它建对象类型"]);
  assert.equal(made[0].href, "#/datasets/%E8%AE%A2%E5%8D%95/fields");
  assert.equal(made[1].href, "#/types/new");
  const two = afterUpload([{ name: "a", mode: "new" }, { name: "b", mode: "new" }]);
  assert.equal(two[0].href, "#/datasets");
  assert.equal(two[0].label, "查看数据集");
  const update = afterUpload([{ name: "订单", mode: "overwrite" }]);
  assert.deepEqual(update.map((a) => a.label), ["查看数据集"]);
});
