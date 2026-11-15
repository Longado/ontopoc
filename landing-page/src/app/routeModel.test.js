import assert from "node:assert/strict";
import test from "node:test";

import { readFileSync } from "node:fs";
import { ADMIN_NAV, NAV, PAGES, PLANNED, hrefFor, mayOpen, navKeyOf, parseRoute } from "./routeModel.js";

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
  for (const hash of ["#/constructor", "#/nothing", "#/pipelines/x/nope", "#/pipelines/x/runs/0", "#/pipelines/x/runs/2/extra", "#/datasets/x/nope", "#/datasets/x/preview/extra", "#/datasets/%E0%A4%A"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
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

test("a pipeline opens on its steps; its runs, one run, its history and its confirm screen have addresses of their own", () => {
  assert.deepEqual(parseRoute("#/pipelines"), { page: "pipelines" });
  assert.deepEqual(parseRoute("#/pipelines/new"), { page: "pipelinenew" });
  assert.deepEqual(parseRoute("#/pipelines/%E5%AE%A2%E6%88%B7%E5%90%88%E8%AE%A1"), { page: "pipeline", name: "客户合计", view: "edit" });
  assert.deepEqual(parseRoute("#/pipelines/x/runs"), { page: "pipeline", name: "x", view: "runs" });
  assert.deepEqual(parseRoute("#/pipelines/x/runs/12"), { page: "pipeline", name: "x", view: "run", run: 12 });
  assert.deepEqual(parseRoute("#/pipelines/x/history"), { page: "pipeline", name: "x", view: "history" });
  assert.deepEqual(parseRoute("#/pipelines/x/confirm"), { page: "pipeline", name: "x", view: "confirm" });
  for (const route of [{ page: "pipelines" }, { page: "pipelinenew" }, { page: "pipeline", name: "a/b", view: "edit" }, { page: "pipeline", name: "x", view: "runs" }, { page: "pipeline", name: "x", view: "run", run: 3 }, { page: "pipeline", name: "x", view: "confirm" }]) {
    assert.deepEqual(parseRoute(hrefFor(route)), route);
  }
  assert.equal(navKeyOf({ page: "pipeline", name: "x", view: "runs" }), "pipelines");
});

test("a page not built yet has an address of its own and says what it will do", () => {
  assert.equal(parseRoute("#/nowhere").page !== "planned", true);
  assert.equal(navKeyOf({ page: "qa", id: 3 }), "qa");
  assert.equal(navKeyOf({ page: "planned", key: "sources" }), "sources");
  for (const { items } of NAV) for (const i of items) assert.ok(i.built || i.key in PLANNED, i.key);   // nothing in the sidebar leads nowhere
});

test("the sidebar groups what the product has, and marks what is built", () => {
  assert.deepEqual(NAV.map((g) => g.label ?? null), [null, "数据", "本体", "应用", null]);
  assert.deepEqual(NAV.flatMap((g) => g.items.map((i) => i.label)), ["问答", "任务", "数据集", "管道", "数据源", "调度", "对象类型", "关系", "待确认", "智能体", "看板", "血缘"]);
  assert.equal(navKeyOf({ page: "dataset", name: "x" }), "datasets");
});

test("the boards and the agent page are built: a viewer reads boards, only builders see the agent page", () => {
  assert.deepEqual(NAV.flatMap((g) => g.items).filter((i) => ["agents", "boards"].includes(i.key)).map((i) => [i.key, i.built, i.builders]), [["agents", true, true], ["boards", true, false]]);
  assert.deepEqual(parseRoute("#/agents"), { page: "agents" });
  assert.deepEqual(parseRoute("#/boards"), { page: "boards" });
  assert.deepEqual(parseRoute("#/boards/new"), { page: "boardnew" });
  assert.deepEqual(parseRoute("#/boards/4"), { page: "board", id: 4 });
  assert.deepEqual(parseRoute("#/boards/4/edit"), { page: "boardedit", id: 4 });
  for (const hash of ["#/boards/0", "#/boards/x", "#/boards/4/other", "#/boards/new/edit", "#/agents/x"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
  for (const route of [{ page: "agents" }, { page: "boards" }, { page: "boardnew" }, { page: "board", id: 4 }, { page: "boardedit", id: 4 }]) assert.deepEqual(parseRoute(hrefFor(route)), route);
  assert.equal(navKeyOf({ page: "board", id: 4 }), "boards");
  assert.equal(navKeyOf({ page: "boardedit", id: 4 }), "boards");
  assert.equal(navKeyOf({ page: "agents" }), "agents");
});

test("one object has an address under its type; the explorer's query rides in the address of the objects tab", () => {
  assert.deepEqual(parseRoute("#/types/order/objects/12"), { page: "object", id: "order", n: 12 });
  assert.deepEqual(parseRoute("#/types/order/objects/0"), { page: "notfound" });
  assert.deepEqual(parseRoute("#/types/order/props/12"), { page: "notfound" });
  assert.equal(navKeyOf({ page: "object", id: "order", n: 12 }), "types");
  const q = JSON.stringify({ type: "customer", pivot: { relation: "r", side: "from", source: { type: "order" } } });
  const route = { page: "type", id: "customer", tab: "objects", pageNo: 2, q };
  assert.deepEqual(parseRoute(hrefFor(route)), route);
  assert.deepEqual(parseRoute(hrefFor({ page: "object", id: "order", n: 12 })), { page: "object", id: "order", n: 12 });
  assert.deepEqual(parseRoute("#/types/order/props?q=%7B%7D"), { page: "type", id: "order", tab: "props", pageNo: 1 });   // only the objects tab reads a query
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

test("the screen that confirms what one dataset version moved has an address under 待确认, and the name survives the round trip", () => {
  const route = { page: "confirmgroup", dataset: "订单 2026/10", version: 2 };
  assert.equal(hrefFor(route), "#/confirm/group/%E8%AE%A2%E5%8D%95%202026%2F10/2");
  assert.deepEqual(parseRoute(hrefFor(route)), route);
  assert.equal(navKeyOf(route), "confirm");
  for (const hash of ["#/confirm/group/订单", "#/confirm/group/订单/0", "#/confirm/group/订单/x", "#/confirm/other/订单/2"]) assert.deepEqual(parseRoute(hash), { page: "notfound" }, hash);
});

const ADDRESSES = ["#/qa", "#/qa/3", "#/datasets", "#/datasets/x", "#/tasks", "#/types", "#/types/new", "#/types/x/edit", "#/types/x/props", "#/types/x/objects/2",
  "#/relations", "#/relations/new", "#/relations/x", "#/relations/x/edit", "#/lineage", "#/confirm", "#/confirm/group/x/2", "#/pipelines", "#/pipelines/new",
  "#/pipelines/x", "#/sources", "#/sources/x", "#/schedules", "#/permissions", "#/account", "#/users", "#/boards", "#/boards/new", "#/boards/3", "#/boards/3/edit", "#/agents"];

test("every page an address can open has one entry in the page table, and the table has no page no address opens", () => {
  const opened = new Set(ADDRESSES.map((a) => parseRoute(a).page));
  for (const page of opened) assert.ok(PAGES[page], `no entry for ${page}`);
  assert.deepEqual(Object.keys(PAGES).filter((p) => p !== "planned").sort(), [...opened].sort());
});

test("who may open which page comes from the table", () => {
  const viewer = { role: "viewer" }, builder = { role: "builder" }, admin = { role: "admin" };
  for (const page of ["qa", "datasets", "types", "type", "relations", "lineage", "boards", "board", "account"]) assert.ok(mayOpen(page, viewer), page);
  for (const page of ["boardnew", "boardedit", "agents", "confirm", "confirmgroup", "pipelines", "pipelinenew", "pipeline", "sources", "source", "schedules"]) {
    assert.ok(!mayOpen(page, viewer), page);
    assert.ok(mayOpen(page, builder), page);
  }
  for (const page of ["permissions", "users"]) assert.deepEqual([mayOpen(page, builder), mayOpen(page, admin)], [false, true], page);
  assert.ok(Object.keys(PAGES).every((page) => mayOpen(page, admin)));
});

test("the shell draws a view for every page in the table and for no other", () => {
  const shell = readFileSync(new URL("./Shell.jsx", import.meta.url), "utf8");
  const block = shell.slice(shell.indexOf("const VIEWS = {"), shell.indexOf("};", shell.indexOf("const VIEWS = {")));
  const drawn = [...block.matchAll(/^\s+(\w+): /gm)].map((m) => m[1]);
  assert.deepEqual(drawn.sort(), Object.keys(PAGES).sort());
});
