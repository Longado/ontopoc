import assert from "node:assert/strict";
import test from "node:test";

import { NAV, hrefFor, navKeyOf, parseRoute } from "./routeModel.js";

test("an empty address and the list address both mean the dataset list", () => {
  assert.deepEqual(parseRoute(""), { page: "datasets" });
  assert.deepEqual(parseRoute("#/"), { page: "datasets" });
  assert.deepEqual(parseRoute("#/datasets"), { page: "datasets" });
});

test("a dataset opens on its fields; the tab and the version come from the address", () => {
  assert.deepEqual(parseRoute("#/datasets/%E8%AE%A2%E5%8D%95"), { page: "dataset", name: "订单", tab: "fields", version: null });
  assert.deepEqual(parseRoute("#/datasets/%E8%AE%A2%E5%8D%95/preview?v=2"), { page: "dataset", name: "订单", tab: "preview", version: 2 });
  assert.deepEqual(parseRoute("#/datasets/a%2Fb/versions"), { page: "dataset", name: "a/b", tab: "versions", version: null });
  assert.equal(parseRoute("#/datasets/x/preview?v=abc").version, null);
});

test("addresses that mean nothing are not found, including a broken escape", () => {
  for (const hash of ["#/pipelines", "#/datasets/x/nope", "#/datasets/x/preview/extra", "#/datasets/%E0%A4%A"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
  assert.deepEqual(parseRoute("#/tasks"), { page: "tasks" });
  assert.deepEqual(parseRoute("#/tasks/x"), { page: "notfound" });
});

test("hrefFor is the inverse of parseRoute", () => {
  for (const route of [{ page: "datasets" }, { page: "tasks" }, { page: "dataset", name: "订单 (试)", tab: "preview", version: 3 }, { page: "dataset", name: "a/b", tab: "versions", version: null }]) {
    assert.deepEqual(parseRoute(hrefFor(route)), route);
  }
});

test("the sidebar groups what the product has, and only built pages have an address", () => {
  assert.deepEqual(NAV.map((g) => g.label ?? null), [null, "数据", "本体", "应用", null]);
  assert.deepEqual(NAV.flatMap((g) => g.items.map((i) => i.label)), ["首页", "任务", "数据集", "管道", "数据源", "对象类型", "关系", "待确认", "问答", "智能体", "看板", "血缘"]);
  assert.deepEqual(NAV.flatMap((g) => g.items).filter((i) => i.href).map((i) => i.key), ["tasks", "datasets"]);
  assert.equal(navKeyOf({ page: "dataset", name: "x" }), "datasets");
});
