import assert from "node:assert/strict";
import test from "node:test";

import { consensusLines, overviewTiles } from "./ontologyGraphModel.js";

const run = (stability) => ({
  file: { kind: "table" }, saved_as: "x.json",
  ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }, { key: "engineer", label: "售后工程师" }], relations: [{ key: "r1" }] },
  evaluation: { data_fit: null, stability },
});

test("the stability tile counts objects every run agrees on", () => {
  const tile = (s) => overviewTiles(run(s)).find((t) => t.key === "stability");
  const shaky = tile({ runs: 3, failed: 0, types: { customer: 3, order: 3, engineer: 1 }, relations: { r1: 3 }, elsewhere: { types: [], relations: [] } });
  assert.deepEqual([shaky.value, shaky.tone, shaky.hint], ["2 / 3 个对象三次都有", "warn", "虚线框的对象不是每次都有"]);
  const steady = tile({ runs: 3, failed: 0, types: { customer: 3, order: 3, engineer: 3 }, relations: { r1: 3 }, elsewhere: { types: [], relations: [] } });
  assert.deepEqual([steady.value, steady.tone, steady.hint], ["三次搭的都一样", "ok", "对象和关系每次都有"]);
});

test("the stability card says what varies and whether a run failed", () => {
  const s = { runs: 2, failed: 1, types: { customer: 2, order: 2, engineer: 1 }, relations: { r1: 2 },
    elsewhere: { types: [{ label: "产品", count: 1 }], relations: [{ label: "订单 — 产品", count: 1 }] } };
  const lines = consensusLines(run(s).ontology, s);
  assert.deepEqual(lines, [
    "另外一次没有成功，只比了 2 次",
    "每次都有：客户、订单",
    "不是每次都有：售后工程师（2 次里 1 次）",
    "这次没有、别的某次有：产品（2 次里 1 次）；关系 订单 — 产品（2 次里 1 次）",
  ]);
});
