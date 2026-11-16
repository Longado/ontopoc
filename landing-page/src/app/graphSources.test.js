import assert from "node:assert/strict";
import test from "node:test";

import { KIND_LABEL, SIZE, cameFromText, sourceLines } from "./graphModel.js";

test("a source is a node of its own on the lineage", () => {
  assert.equal(KIND_LABEL.source, "数据源");
  assert.ok(SIZE.source.w > 0 && SIZE.source.h > 0);
});

test("a dataset says where its current version came from, in words", () => {
  assert.equal(cameFromText({ kind: "upload" }), "上传的");
  assert.equal(cameFromText({ kind: "source", source: "订单库", table: "orders" }), "从 订单库 拉取");   // short enough for the node
  assert.equal(cameFromText({ kind: "source", source: "订单库", table: "orders" }, true), "从 订单库 的表 orders 拉取");   // the panel names the table
  assert.equal(cameFromText({ kind: "source" }), "从数据源拉取");   // a viewer is not told which
  assert.equal(cameFromText({ kind: "pipeline", pipeline: "客户合计" }), "管道 客户合计 写的");
  assert.equal(cameFromText({ kind: "pipeline" }), "管道写的");
  assert.equal(cameFromText({ kind: "action", action: "改状态" }), "行为 改状态 改过");
  assert.equal(cameFromText({ kind: "other" }), "");
  assert.equal(cameFromText(undefined), "");
});

test("a source node says its kind, whether it works and how many datasets it fills", () => {
  assert.deepEqual(sourceLines({ kind_label: "PostgreSQL", status: "ok", status_label: "正常", tables: [{ table: "orders", dataset: "订单" }] }), [{ text: "PostgreSQL，正常" }, { text: "填 1 个数据集" }]);
  assert.deepEqual(sourceLines({ kind_label: "MySQL", status: "failed", status_label: "失败", tables: [] }), [{ text: "MySQL，失败", cause: true }, { text: "还没有读进数据集的表" }]);
});
