import assert from "node:assert/strict";
import test from "node:test";

import { meaningsSummary, tabCounts, typeSub, usesSummary } from "./typeModel.js";

const USES = { used_by: [{ kind: "views", label: "视图", count: 1, items: [] }, { kind: "actions", label: "行为", count: 3, items: [] }, { kind: "relations", label: "关系", count: 4, items: [] }, { kind: "answers", label: "回答", count: 2, items: [] }] };

test("each tab of a type carries the number of what is in it (W3)", () => {
  const type = { properties: [1, 2, 3, 4, 5, 6, 7], rows: 160 };
  assert.deepEqual(tabCounts(type, USES), { props: 7, derived: 0, views: 1, actions: 3, objects: 160 });
  assert.deepEqual(tabCounts(type, null), { props: 7, objects: 160 });   // uses not loaded yet: only what the type itself knows
});

test("what uses a type is one line that expands: the counts, nothing for kinds nobody uses", () => {
  assert.equal(usesSummary(USES), "视图 1 · 行为 3 · 关系 4 · 回答 2");
  assert.equal(usesSummary({ used_by: [] }), "");
  assert.equal(usesSummary(null), "");
});

test("the line under a type's title: source and version, then how many objects", () => {
  assert.equal(typeSub({ dataset: "订单", dataset_version: 2, rows: 160 }), "来源 订单 第 2 版 · 160 个对象");
  assert.equal(typeSub({ dataset: "订单", dataset_version: 2, rows: 40, rows_limited: true }), "来源 订单 第 2 版 · 你能看到 40 个对象");
  assert.equal(typeSub({ dataset: "订单", dataset_version: 2, rows: 160 }, "3 天前，Ann"), "来源 订单 第 2 版（上传于 3 天前，Ann）· 160 个对象");
});

test("a code column's meanings in one line for the section head", () => {
  const values = [{ value: "0", label: "已交付" }, { value: "1", label: "生产中" }, { value: "2", label: "" }];
  assert.equal(meaningsSummary({ values }), "3 个取值，2 个写了含义");
  assert.equal(meaningsSummary({ values: [] }), "没有取值");
});
