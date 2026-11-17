import assert from "node:assert/strict";
import test from "node:test";
import { exampleQuestions, kpiCards, greeting, needsSetup, setupSteps, todoItems, updatedText } from "./homeModel.js";

const T = (id, name, state = "confirmed") => ({ id, name, state });

test("the workspace is not ready with no dataset, or with no confirmed type", () => {
  assert.equal(needsSetup({ datasets: [], types: [] }), true);
  assert.equal(needsSetup({ datasets: [{ name: "a" }], types: [T("a", "A", "proposed")] }), true);
  assert.equal(needsSetup({ datasets: [{ name: "a" }], types: [T("a", "A")] }), false);
});

test("four steps; the first undone one is next, the rest are not started", () => {
  const none = setupSteps({ datasets: [], types: [], users: [{}], sources: [], role: "admin" });
  assert.deepEqual(none.map((s) => s.key), ["data", "type", "confirm", "invite"]);
  assert.deepEqual(none.map((s) => s.state), ["next", "todo", "todo", "todo"]);
  const some = setupSteps({ datasets: [{ name: "a" }], types: [T("a", "A", "proposed")], users: [{}], sources: [], role: "builder" });
  assert.deepEqual(some.map((s) => s.state), ["done", "done", "next", "todo"]);
  const all = setupSteps({ datasets: [{ name: "a" }], types: [T("a", "A")], users: [{}, {}], sources: [], role: "admin" });
  assert.deepEqual(all.map((s) => s.state), ["done", "done", "done", "done"]);
});

test("each step has a button to the page that does it; an admin may also connect a database", () => {
  const steps = setupSteps({ datasets: [], types: [], users: [{}], sources: [], role: "admin" });
  assert.deepEqual(steps.map((s) => s.button.href), ["#/datasets", "#/types/new", "#/confirm", "#/users"]);
  assert.match(steps[0].text, /数据库/);
  assert.ok(steps.every((s) => s.title && s.text && s.button.label));
});

test("a builder cannot list users: the invite step asks an admin and has no button", () => {
  const steps = setupSteps({ datasets: [], types: [], users: null, sources: null, role: "builder" });
  assert.equal(steps[3].button, null);
  assert.match(steps[3].text, /管理员/);
  assert.equal(steps[0].button.href, "#/datasets");
});

test("example questions come from confirmed types and relations, at most six", () => {
  const types = [T("o", "订单"), T("c", "客户"), T("p", "产品", "proposed")];
  const relations = [{ from_name: "订单", to_name: "客户", state: "confirmed" }, { from_name: "订单", to_name: "产品", state: "proposed" }];
  assert.deepEqual(exampleQuestions(types, relations), ["订单一共有多少", "客户一共有多少", "按客户统计订单数量"]);
  assert.deepEqual(exampleQuestions([], []), []);
  const many = Array.from({ length: 9 }, (_, i) => T(`t${i}`, `类${i}`));
  assert.equal(exampleQuestions(many, []).length, 6);
});

test("the greeting follows the hour and names the person", () => {
  const at = (h) => new Date(2026, 10, 16, h, 0);
  assert.equal(greeting(at(8), "陈总"), "陈总，早上好");
  assert.equal(greeting(at(13), "陈总"), "陈总，下午好");
  assert.equal(greeting(at(21), "陈总"), "陈总，晚上好");
  assert.equal(greeting(at(2), ""), "晚上好");
});

test("data is as new as the newest dataset", () => {
  assert.equal(updatedText([]), "");
  const text = updatedText([{ updated_at: "2026-11-15T01:00:00+00:00" }, { updated_at: "2026-11-16T10:30:00+00:00" }]);
  assert.match(text, /^数据更新于 /);
});

test("the to-do list counts what waits for confirming, failed runs and unread notices; nothing waiting gives an empty list", () => {
  assert.deepEqual(todoItems({ unread: 0, queue: 0, failedRuns: 0 }), []);
  const items = todoItems({ unread: 2, queue: 5, failedRuns: 1, mayBuild: true });
  assert.deepEqual(items.map((i) => [i.key, i.count, i.href]), [["queue", 5, "#/confirm"], ["failed", 1, "#/tasks"], ["notices", 2, "#/notices"]]);
  assert.deepEqual(todoItems({ unread: 2, queue: 5, failedRuns: 1, mayBuild: false }).map((i) => i.key), ["notices"]);
});

const U = (id, last_login_at = null) => ({ id, last_login_at });

test("inviting colleagues counts only once someone other than me has signed in", () => {
  const base = { datasets: [{ name: "a" }], types: [T("a", "A")], role: "admin", meId: 1 };
  const waiting = setupSteps({ ...base, users: [U(1, "2026-11-16"), U(2)] });
  assert.equal(waiting[3].state, "next");
  assert.match(waiting[3].note, /已建 1 个同事账号，还没有人登录过/);
  const done = setupSteps({ ...base, users: [U(1, "2026-11-16"), U(2, "2026-11-16T10:00:00")] });
  assert.equal(done[3].state, "done");
  assert.equal(setupSteps({ ...base, users: [U(1, "x")] })[3].note, undefined);
});

test("step 3 says so when this person cannot confirm, and offers an invite and the queue", () => {
  const base = { datasets: [{ name: "a" }], types: [T("a", "A", "proposed")], users: [U(1)], role: "admin", meId: 1 };
  const stuck = setupSteps({ ...base, canConfirm: false })[2];
  assert.match(stuck.text, /你不能确认/);
  assert.equal(stuck.button.label, "邀请一位建设者");
  assert.equal(stuck.button.href, "#/users");
  assert.equal(stuck.extra.href, "#/confirm");
  const able = setupSteps({ ...base, canConfirm: true })[2];
  assert.equal(able.button.href, "#/confirm");
  assert.equal(able.extra, undefined);
  const builder = setupSteps({ ...base, role: "builder", canConfirm: false })[2];
  assert.match(builder.text, /管理员/);
  assert.equal(builder.button.href, "#/confirm");
});

test("with exactly one dataset, creating a type opens with it chosen", () => {
  const one = setupSteps({ datasets: [{ name: "订 单" }], types: [], users: [U(1)], role: "admin", meId: 1 });
  assert.equal(one[1].button.href, "#/types/new?dataset=%E8%AE%A2%20%E5%8D%95");
  const two = setupSteps({ datasets: [{ name: "a" }, { name: "b" }], types: [], users: [U(1)], role: "admin", meId: 1 });
  assert.equal(two[1].button.href, "#/types/new");
});

test("number cards come from confirmed types that have rows, each with when the data is from and a link", () => {
  const types = [{ id: "order", name: "订单", state: "confirmed", rows: 12345, dataset: "orders" }, { id: "c", name: "客户", state: "proposed", rows: 3, dataset: "c" },
    { id: "p", name: "产品", state: "confirmed", rows: null, dataset: null }, { id: "r", name: "退货", state: "confirmed", rows: 0, dataset: "orders" }];
  const datasets = [{ name: "orders", updated_at: "2026-11-16T10:30:00+00:00" }];
  const cards = kpiCards(types, datasets);
  assert.deepEqual(cards.map((c) => [c.label, c.value, c.href]), [["订单", "12,345", "#/types/order/objects"], ["退货", "0", "#/types/r/objects"]]);
  assert.match(cards[0].asOf, /^数据截至 /);
  assert.equal(kpiCards(types, datasets, 1).length, 1);
  assert.deepEqual(kpiCards([], []), []);
});
