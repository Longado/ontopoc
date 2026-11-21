import assert from "node:assert/strict";
import test from "node:test";

import { readFileSync } from "node:fs";
import { ADMIN_NAV, NAV, PAGES, PLANNED, afterSignIn, hrefFor, mayOpen, navFor, navKeyOf, navLabelOf, parseRoute } from "./routeModel.js";
import { setLocale, t } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("the empty address is the home page; the Q&A page, a saved answer and the dataset list have addresses", () => {
  assert.deepEqual(parseRoute(""), { page: "home" });
  assert.deepEqual(parseRoute("#/"), { page: "home" });
  assert.deepEqual(parseRoute("#/home"), { page: "home" });
  assert.deepEqual(parseRoute("#/home/x"), { page: "notfound" });
  assert.deepEqual(parseRoute(hrefFor({ page: "home" })), { page: "home" });
  assert.equal(navKeyOf({ page: "home" }), "home");
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
  assert.deepEqual(ADMIN_NAV.flatMap((g) => g.items.map((i) => [g.label, i.label, i.built])), [["设置", "工作区", true], ["设置", "用户", true], ["设置", "权限", true]]);
});

test("hrefFor is the inverse of parseRoute", () => {
  for (const route of [{ page: "datasets" }, { page: "qa", id: null }, { page: "qa", id: 7 }, { page: "tasks" }, { page: "account" }, { page: "users" }, { page: "dataset", name: "订单 (试)", tab: "preview", version: 3, pageNo: 2 }, { page: "dataset", name: "a/b", tab: "versions", version: null, pageNo: 1 },
    { page: "types" }, { page: "typenew" }, { page: "typeedit", id: "order" }, { page: "type", id: "order", tab: "props", pageNo: 1 }, { page: "type", id: "order", tab: "objects", pageNo: 3 },
    { page: "relations" }, { page: "relations", list: true }, { page: "relations", map: true }, { page: "lineage" }, { page: "relationnew" }, { page: "relation", id: "order_customer" }, { page: "relationedit", id: "order_customer" }, { page: "confirm" }, { page: "permissions" }]) {
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

test("a question asked from the home page rides in the address of the Q&A page", () => {
  assert.deepEqual(parseRoute("#/qa?ask=%E8%AE%A2%E5%8D%95%20%E4%B8%80%E5%85%B1%E6%9C%89%E5%A4%9A%E5%B0%91"), { page: "qa", id: null, ask: "订单 一共有多少" });
  assert.deepEqual(parseRoute("#/qa?ask="), { page: "qa", id: null });
  assert.deepEqual(parseRoute(hrefFor({ page: "qa", id: null, ask: "按客户统计订单" })), { page: "qa", id: null, ask: "按客户统计订单" });
});

test("a page not built yet has an address of its own and says what it will do", () => {
  assert.equal(parseRoute("#/nowhere").page !== "planned", true);
  assert.equal(navKeyOf({ page: "qa", id: 3 }), "qa");
  assert.equal(navKeyOf({ page: "planned", key: "sources" }), "sources");
  for (const { items } of NAV) for (const i of items) assert.ok(i.built || i.key in PLANNED, i.key);   // nothing in the sidebar leads nowhere
});

test("the sidebar groups what the product has, and marks what is built: the gate's daily work (定义) before the data that feeds it", () => {
  assert.deepEqual(NAV.map((g) => g.label ?? null), [null, "定义", "数据", "智能体"]);
  assert.deepEqual(NAV.flatMap((g) => g.items.map((i) => i.label)), ["首页", "助手", "看板", "消息", "待确认", "对象类型", "关系", "血缘", "数据集", "数据源", "管道", "调度", "AI 工具接入"]);
  for (const g of [...NAV, ...ADMIN_NAV].filter((g) => g.label)) assert.ok(g.hint && g.icon, g.label);   // a one-line grey explainer and an icon under each group
  for (const i of [...NAV, ...ADMIN_NAV].flatMap((g) => g.items)) assert.ok(i.icon, i.key);
  assert.equal(navKeyOf({ page: "dataset", name: "x" }), "datasets");
});

test("a viewer sees the main line and the definitions they may read, a builder the review queue first, the data and the agents, an admin settings too", () => {
  const names = (user, has) => navFor(user, has).map((g) => [g.label ?? null, g.items.map((i) => i.label)]);
  assert.deepEqual(names({ role: "viewer" }), [[null, ["首页", "助手", "看板"]], ["定义", ["对象类型", "关系", "血缘"]], ["数据", ["数据集"]]]);   // read-only pages the service serves a viewer; 数据集 stays, as it shipped for viewers
  assert.deepEqual(names({ role: "builder" }).map((g) => g[0]), [null, "定义", "数据", "智能体"]);
  assert.deepEqual(names({ role: "admin" }).map((g) => g[0]), [null, "定义", "数据", "智能体", "设置"]);
  assert.deepEqual(names({ role: "admin" })[4][1], ["工作区", "用户", "权限"]);
  assert.deepEqual(names({ role: "builder" })[1][1], ["待确认", "对象类型", "关系", "血缘"]);   // the queue first; 血缘 says why a definition went back, so it lives here
  assert.deepEqual(names({ role: "builder" })[2][1], ["数据集", "数据源", "管道", "调度"]);   // no 任务: the page stays at its address
  assert.deepEqual(navFor(null).map((g) => g.label ?? null), [null]);
  for (const role of ["viewer", "builder", "admin"]) for (const g of navFor({ role }, { notices: true })) for (const i of g.items) assert.equal(mayOpen(i.key, { role }), true, `${role} ${i.key}`);   // nothing offered leads to a refusal
});

test("消息 is in the sidebar only for someone who has received a notice; the page stays at its address and in the top bar", () => {
  const main = (user, has) => navFor(user, has)[0].items.map((i) => i.key);
  for (const role of ["viewer", "builder", "admin"]) {
    assert.deepEqual(main({ role }), ["home", "qa", "boards"], role);
    assert.deepEqual(main({ role }, { notices: true }), ["home", "qa", "boards", "notices"], role);
  }
  assert.equal(mayOpen("notices", { role: "viewer" }), true);
  assert.deepEqual(parseRoute("#/notices"), { page: "notices" });
});

test("the task list is not in the sidebar but its page and address stay", () => {
  assert.ok(!NAV.flatMap((g) => g.items).some((i) => i.key === "tasks"));
  assert.deepEqual(parseRoute("#/tasks"), { page: "tasks" });
  assert.equal(hrefFor({ page: "tasks" }), "#/tasks");
  assert.equal(mayOpen("tasks", { role: "builder" }), true);
  assert.equal(navKeyOf({ page: "tasks" }), null);
});

test("every page stays reachable from some item or by its address", () => {
  const keys = new Set([...NAV, ...ADMIN_NAV].flatMap((g) => g.items.map((i) => i.key)));
  for (const [page, { nav }] of Object.entries(PAGES)) assert.ok(nav === null || keys.has(nav), page);
});

test("the boards and the agent page are built: a viewer reads boards, only builders see the agent page", () => {
  assert.deepEqual(NAV.flatMap((g) => g.items).filter((i) => ["agents", "boards"].includes(i.key)).map((i) => [i.key, i.built, i.builders]), [["boards", true, false], ["agents", true, true]]);
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
  assert.deepEqual(parseRoute("#/relations?view=map"), { page: "relations", map: true });
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

const ADDRESSES = ["#/home", "#/qa", "#/qa/3", "#/datasets", "#/datasets/x", "#/tasks", "#/notices", "#/types", "#/types/new", "#/types/x/edit", "#/types/x/props", "#/types/x/objects/2",
  "#/relations", "#/relations/new", "#/relations/x", "#/relations/x/edit", "#/lineage", "#/confirm", "#/confirm/group/x/2", "#/pipelines", "#/pipelines/new",
  "#/pipelines/x", "#/sources", "#/sources/x", "#/schedules", "#/permissions", "#/account", "#/users", "#/settings", "#/boards", "#/boards/new", "#/boards/3", "#/boards/3/edit", "#/agents"];

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

test("a route's sidebar word names the place in the recent list", () => {
  assert.equal(navLabelOf({ page: "qa", id: 3 }), "助手");
  assert.equal(navLabelOf({ page: "pipeline", name: "x", view: "edit" }), "管道");
  assert.equal(navLabelOf({ page: "account" }), "");
});

test("the settings page has an address, is for admins, and lives under its sidebar item", () => {
  assert.deepEqual(parseRoute("#/settings"), { page: "settings" });
  assert.deepEqual(parseRoute("#/settings/x"), { page: "notfound" });
  assert.equal(hrefFor({ page: "settings" }), "#/settings");
  assert.equal(navKeyOf({ page: "settings" }), "settings");
  assert.equal(mayOpen("settings", { role: "builder" }), false);
  assert.equal(mayOpen("settings", { role: "admin" }), true);
});

test("a fresh sign-in lands on the home page; an expired session returns to where the person was", () => {
  for (const hash of ["", "#/", "#/qa", "#/types/order/props", "#/home"]) assert.equal(afterSignIn(hash, false), "#/home", hash);
  assert.equal(afterSignIn("#/qa/3", true), "#/qa/3");
  assert.equal(afterSignIn("", true), "#/home");
});

test("a viewer cannot open the pages that make or change definitions, nor the task list: refused at the address, not after filling a form", () => {
  const viewer = { role: "viewer" }, builder = { role: "builder" };
  for (const page of ["typenew", "typeedit", "relationnew", "relationedit", "tasks"]) {
    assert.equal(mayOpen(page, viewer), false, page);
    assert.equal(mayOpen(page, builder), true, page);
  }
});

test("the words for a page one may not open do not say builders may open an admin's page; the guest banner says what really happens", () => {
  for (const locale of ["zh", "en"]) {
    setLocale(locale);
    try {
      assert.doesNotMatch(t("shell.forbidden.title") + t("shell.forbidden.text"), /建设者或管理员|builder or admin|builders or admins/i, locale);
      assert.doesNotMatch(t("auth.guest.banner"), /每天重置|resets daily/i, locale);
      assert.match(t("auth.guest.banner"), /24/, locale);
    } finally {
      setLocale("zh");
    }
  }
});
