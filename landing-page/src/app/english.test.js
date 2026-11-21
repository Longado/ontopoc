import assert from "node:assert/strict";
import test from "node:test";
import { roleLabel, searchPlaceholder, statusText } from "./authModel.js";
import { exampleQuestions, greeting, kpiCards, setupSteps, todoItems } from "./homeModel.js";
import { getLocale, setLocale } from "./i18n/index.js";
import { NAV, TAB_LABEL, navFor } from "./routeModel.js";
import { pageEntries, buildEntries } from "./searchModel.js";
import { workspaceRows } from "./settingsModel.js";
import { statusOf } from "./statusModel.js";

setLocale("en");   // the default; these tests pin the English product copy

test("the six states are Draft / Pending review / Confirmed / Needs review / Sent back / Failed", () => {
  const word = (raw) => statusOf(raw).label;
  assert.deepEqual(["draft", "proposed", "confirmed", "needs_look", "rejected", "failed"].map(word), ["Draft", "Pending review", "Confirmed", "Needs review", "Sent back", "Failed"]);
  assert.equal(statusOf("running").label, "Running");
  assert.equal(statusOf("interrupted").hint, "Interrupted");
});

test("roles are Admin / Builder / Viewer", () => {
  assert.deepEqual(["admin", "builder", "viewer"].map(roleLabel), ["Admin", "Builder", "Viewer"]);
  assert.equal(statusText({ disabled: true }), "Disabled");
  assert.equal(searchPlaceholder({ role: "viewer" }), "Search boards, questions…");
});

test("the sidebar speaks English, and the labels follow a language switch", () => {
  const admin = navFor({ role: "admin" }, { notices: true });
  assert.deepEqual(admin.map((g) => g.label ?? "(main)"), ["(main)", "Definitions", "Data", "Agents", "Settings"]);
  assert.deepEqual(admin.flatMap((g) => g.items.map((i) => i.label)), [
    "Home", "Assistant", "Boards", "Notifications", "Review queue", "Object types", "Relations", "Lineage", "Datasets", "Sources", "Pipelines", "Schedules", "AI tool access", "Workspace", "Users", "Permissions",
  ]);
  assert.equal(TAB_LABEL.fields, "Fields");
  assert.match(NAV[1].hint, /confirmed it on the current data/);
  setLocale("zh");
  assert.equal(NAV[2].items[0].label, "数据集");
  assert.equal(TAB_LABEL.fields, "字段");
  setLocale("en");
  assert.equal(getLocale(), "en");
});

test("the home page copy: example questions use the type's name, the greeting is English", () => {
  const types = [{ id: "o", name: "orders", state: "confirmed", rows: 1200, dataset: "d" }, { id: "c", name: "customers", state: "confirmed" }];
  const relations = [{ from_name: "orders", to_name: "customers", state: "confirmed" }];
  assert.deepEqual(exampleQuestions(types, relations), ["How many orders are there?", "How many customers are there?", "Orders by customers"]);
  // a type named in Chinese is asked about by its English name in the English UI, never "How many 订单 are there?"
  const zhNamed = [{ id: "order", name: "订单", state: "confirmed" }, { id: "customer", name: "客户", state: "confirmed" }, { id: "commit_version", name: "订单承诺", state: "confirmed" }];
  const zhRel = [{ from: "order", to: "customer", from_name: "订单", to_name: "客户", state: "confirmed" }];
  assert.deepEqual(exampleQuestions(zhNamed, zhRel), ["How many orders are there?", "How many customers are there?", "How many commit versions are there?", "Orders by customer"]);
  // a singular English type name does not read "How many Order are there?"
  assert.deepEqual(exampleQuestions([{ id: "order", name: "Order", state: "confirmed" }], []), ["How many Order records are there?"]);
  assert.equal(greeting(new Date(2026, 10, 16, 9), "Ann"), "Good morning, Ann");
  assert.equal(greeting(new Date(2026, 10, 16, 20), ""), "Good evening");
  assert.equal(kpiCards(types, [])[0].value, "1,200");
  assert.deepEqual(todoItems({ unread: 1, queue: 2, failedRuns: 1, mayBuild: true }).map((i) => i.text), ["2 items waiting for your review", "1 run failed", "1 unread notification"]);
  assert.equal(setupSteps({ datasets: [], types: [], role: "admin" })[0].title, "Connect data");
});

test("the settings rows and search entries are English", () => {
  assert.equal(workspaceRows({ modelReady: true })[0].text, "Configured. Ask and AI suggestions are available.");
  assert.equal(pageEntries({ role: "viewer" }).at(-1).label, "My account");
  assert.equal(buildEntries({ datasets: [{ name: "Orders", rows: 1 }] })[0].sub, "1 row");
});
