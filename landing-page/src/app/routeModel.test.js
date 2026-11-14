import assert from "node:assert/strict";
import test from "node:test";

import { ADMIN_NAV, NAV, PLANNED, hrefFor, navKeyOf, parseRoute } from "./routeModel.js";

test("the empty address is the Q&A page, a saved answer has an address, and the list address is the dataset list", () => {
  assert.deepEqual(parseRoute(""), { page: "qa", id: null });
  assert.deepEqual(parseRoute("#/"), { page: "qa", id: null });
  assert.deepEqual(parseRoute("#/qa"), { page: "qa", id: null });
  assert.deepEqual(parseRoute("#/qa/12"), { page: "qa", id: 12 });
  assert.deepEqual(parseRoute("#/qa/x"), { page: "notfound" });
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
  assert.deepEqual(ADMIN_NAV.flatMap((g) => g.items.map((i) => [g.label, i.label, i.built])), [["设置", "用户", true], ["设置", "权限", true]]);
});

test("hrefFor is the inverse of parseRoute", () => {
  for (const route of [{ page: "datasets" }, { page: "qa", id: null }, { page: "qa", id: 7 }, { page: "tasks" }, { page: "account" }, { page: "users" }, { page: "dataset", name: "订单 (试)", tab: "preview", version: 3, pageNo: 2 }, { page: "dataset", name: "a/b", tab: "versions", version: null, pageNo: 1 },
    { page: "types" }, { page: "typenew" }, { page: "typeedit", id: "order" }, { page: "type", id: "order", tab: "props", pageNo: 1 }, { page: "type", id: "order", tab: "objects", pageNo: 3 },
    { page: "relations" }, { page: "relations", list: true }, { page: "lineage" }, { page: "relationnew" }, { page: "relation", id: "order_customer" }, { page: "relationedit", id: "order_customer" }, { page: "confirm" }, { page: "permissions" }]) {
    assert.deepEqual(parseRoute(hrefFor(route)), route);
  }
});

test("a page not built yet has an address of its own and says what it will do", () => {
  assert.deepEqual(parseRoute("#/pipelines"), { page: "planned", key: "pipelines" });
  assert.equal(hrefFor({ page: "planned", key: "boards" }), "#/boards");
  assert.equal(navKeyOf({ page: "qa", id: 3 }), "qa");
  assert.equal(navKeyOf({ page: "planned", key: "agents" }), "agents");
  for (const { items } of NAV) for (const i of items) assert.ok(i.built || i.key in PLANNED, i.key);   // nothing in the sidebar leads nowhere
});

test("the sidebar groups what the product has, and marks what is built", () => {
  assert.deepEqual(NAV.map((g) => g.label ?? null), [null, "数据", "本体", "应用", null]);
  assert.deepEqual(NAV.flatMap((g) => g.items.map((i) => i.label)), ["问答", "任务", "数据集", "管道", "数据源", "对象类型", "关系", "待确认", "智能体", "看板", "血缘"]);
  assert.deepEqual(NAV.flatMap((g) => g.items).filter((i) => i.built).map((i) => i.key), ["qa", "tasks", "datasets", "types", "relations", "confirm", "lineage"]);
  assert.deepEqual(NAV.flatMap((g) => g.items).filter((i) => i.builders).map((i) => i.key), ["tasks", "confirm"]);   // 任务 and 待确认 are for builders
  assert.equal(navKeyOf({ page: "dataset", name: "x" }), "datasets");
});

test("an object type opens on its properties; the tab and the page of objects come from the address", () => {
  assert.deepEqual(parseRoute("#/types/order"), { page: "type", id: "order", tab: "props", pageNo: 1 });
  assert.deepEqual(parseRoute("#/types/order/objects?p=2"), { page: "type", id: "order", tab: "objects", pageNo: 2 });
  assert.deepEqual(parseRoute("#/types/order/log"), { page: "type", id: "order", tab: "log", pageNo: 1 });
  assert.deepEqual(parseRoute("#/types/new"), { page: "typenew" });
  for (const hash of ["#/types/order/nope", "#/types/order/props/extra", "#/types/new/edit/x"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
  assert.equal(navKeyOf({ page: "type", id: "order" }), "types");
  assert.equal(navKeyOf({ page: "typenew" }), "types");
});

test("relations, the 待确认 queue and the permissions page have addresses; a relation is never called new", () => {
  assert.deepEqual(parseRoute("#/relations/order_customer"), { page: "relation", id: "order_customer" });
  assert.deepEqual(parseRoute("#/relations/new"), { page: "relationnew" });
  assert.deepEqual(parseRoute("#/relations/order_customer/edit"), { page: "relationedit", id: "order_customer" });
  for (const hash of ["#/relations/a/b", "#/relations/a/edit/x", "#/confirm/x", "#/permissions/x"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
  assert.equal(navKeyOf({ page: "relation", id: "x" }), "relations");
  assert.equal(navKeyOf({ page: "lineage" }), "lineage");
  assert.deepEqual(parseRoute("#/relations?view=list"), { page: "relations", list: true });
  assert.deepEqual(parseRoute("#/relations?view=graph"), { page: "relations" });
  assert.deepEqual(parseRoute("#/lineage/x"), { page: "notfound" });
  assert.equal(navKeyOf({ page: "permissions" }), "permissions");
});
