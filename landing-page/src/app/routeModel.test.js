import assert from "node:assert/strict";
import test from "node:test";

import { ADMIN_NAV, NAV, PLANNED, hrefFor, navKeyOf, parseRoute } from "./routeModel.js";

test("an empty address and the list address both mean the dataset list", () => {
  assert.deepEqual(parseRoute(""), { page: "datasets" });
  assert.deepEqual(parseRoute("#/"), { page: "datasets" });
  assert.deepEqual(parseRoute("#/datasets"), { page: "datasets" });
});

test("a dataset opens on its fields; the tab and the version come from the address", () => {
  assert.deepEqual(parseRoute("#/datasets/%E8%AE%A2%E5%8D%95"), { page: "dataset", name: "订单", tab: "fields", version: null, pageNo: 1 });
  assert.deepEqual(parseRoute("#/datasets/%E8%AE%A2%E5%8D%95/preview?v=2"), { page: "dataset", name: "订单", tab: "preview", version: 2, pageNo: 1 });
  assert.deepEqual(parseRoute("#/datasets/x/preview?v=2&p=3"), { page: "dataset", name: "x", tab: "preview", version: 2, pageNo: 3 });
  assert.equal(parseRoute("#/datasets/x/preview?p=0").pageNo, 1);
  assert.equal(parseRoute("#/datasets/x/preview?p=abc").pageNo, 1);
  assert.deepEqual(parseRoute("#/datasets/a%2Fb/versions"), { page: "dataset", name: "a/b", tab: "versions", version: null, pageNo: 1 });
  assert.equal(parseRoute("#/datasets/x/preview?v=abc").version, null);
});

test("addresses that mean nothing are not found, including a broken escape", () => {
  for (const hash of ["#/constructor", "#/nothing", "#/pipelines/x", "#/datasets/x/nope", "#/datasets/x/preview/extra", "#/datasets/%E0%A4%A"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
  assert.deepEqual(parseRoute("#/tasks"), { page: "tasks" });
  assert.deepEqual(parseRoute("#/tasks/x"), { page: "notfound" });
});

test("the account page and the users page have addresses; nothing hangs off them", () => {
  assert.deepEqual(parseRoute("#/account"), { page: "account" });
  assert.deepEqual(parseRoute("#/users"), { page: "users" });
  assert.deepEqual(parseRoute("#/users/1"), { page: "notfound" });
  assert.equal(navKeyOf({ page: "account" }), null);
  assert.equal(navKeyOf({ page: "users" }), "users");
  assert.deepEqual(ADMIN_NAV.flatMap((g) => g.items.map((i) => [g.label, i.label, i.built])), [["设置", "用户", true]]);
});

test("hrefFor is the inverse of parseRoute", () => {
  for (const route of [{ page: "datasets" }, { page: "tasks" }, { page: "account" }, { page: "users" }, { page: "dataset", name: "订单 (试)", tab: "preview", version: 3, pageNo: 2 }, { page: "dataset", name: "a/b", tab: "versions", version: null, pageNo: 1 }]) {
    assert.deepEqual(parseRoute(hrefFor(route)), route);
  }
});

test("a page not built yet has an address of its own and says what it will do", () => {
  assert.deepEqual(parseRoute("#/types"), { page: "planned", key: "types" });
  assert.equal(hrefFor({ page: "planned", key: "lineage" }), "#/lineage");
  assert.equal(PLANNED.types[1], "从数据集建对象类型，还没做");
  assert.equal(navKeyOf({ page: "planned", key: "qa" }), "qa");
  for (const { items } of NAV) for (const i of items) assert.ok(i.built || i.key in PLANNED, i.key);   // nothing in the sidebar leads nowhere
});

test("the sidebar groups what the product has, and marks what is built", () => {
  assert.deepEqual(NAV.map((g) => g.label ?? null), [null, "数据", "本体", "应用", null]);
  assert.deepEqual(NAV.flatMap((g) => g.items.map((i) => i.label)), ["首页", "任务", "数据集", "管道", "数据源", "对象类型", "关系", "待确认", "问答", "智能体", "看板", "血缘"]);
  assert.deepEqual(NAV.flatMap((g) => g.items).filter((i) => i.built).map((i) => i.key), ["tasks", "datasets"]);
  assert.equal(navKeyOf({ page: "dataset", name: "x" }), "datasets");
});
