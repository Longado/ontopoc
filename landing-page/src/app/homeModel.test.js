import assert from "node:assert/strict";
import test from "node:test";
import { exampleQuestions, greeting, needsSetup, setupSteps, todoItems, updatedText } from "./homeModel.js";

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
  assert.deepEqual(exampleQuestions(types, relations), ["订单 一共有多少", "客户 一共有多少", "按客户统计订单"]);
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
