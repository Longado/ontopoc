import assert from "node:assert/strict";
import test from "node:test";
import { demoQuestions, exampleQuestions, gateStatus, kpiCards, greeting, needsSetup, setupSteps, startCards, tallyView, todoItems, updatedText } from "./homeModel.js";
import { setLocale, t } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

const T = (id, name, state = "confirmed") => ({ id, name, state });

test("a builder's gate line counts confirmed and needs-another-look types and relations, and what waits for them; a viewer gets none", () => {
  const types = [T("a", "A"), T("b", "B", "needs_look"), T("c", "C", "proposed"), T("d", "D", "rejected")];
  const relations = [{ id: "r1", state: "confirmed" }, { id: "r2", state: "needs_look" }];
  const line = gateStatus({ types, relations, queue: 2, mayBuild: true });
  assert.deepEqual(line.map((x) => [x.key, x.count, x.href]), [["confirmed", 2, "#/types"], ["look", 2, "#/types"], ["queue", 2, "#/confirm"]]);
  assert.deepEqual(line.map((x) => x.text), ["已确认 2", "需再看 2", "等你确认 2"]);
  assert.equal(gateStatus({ types, relations, queue: 0, mayBuild: false }), null);   // a viewer is not told about definitions they cannot read (D9)
  assert.equal(gateStatus({ types: [], relations: [], queue: 0, mayBuild: true }), null);   // nothing defined yet: the setup checklist speaks instead
  setLocale("en");
  try {
    assert.deepEqual(gateStatus({ types, relations, queue: 1, mayBuild: true }).map((x) => x.text), ["2 confirmed", "2 need another look", "1 waiting for you"]);
  } finally {
    setLocale("zh");
  }
});

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
  const all = setupSteps({ datasets: [{ name: "a" }], types: [T("a", "A")], users: [{ id: 1, last_login_at: "x" }, { id: 2, last_login_at: "y" }], meId: 1, sources: [], role: "admin" });
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

test("quick actions are for builders only: upload data, new pipeline, new object type, review queue", async () => {
  const { quickActions } = await import("./homeModel.js");
  assert.deepEqual(quickActions(false), []);
  assert.deepEqual(quickActions(true).map((a) => a.href), ["#/datasets", "#/pipelines/new", "#/types/new", "#/confirm"]);
  assert.ok(quickActions(true).every((a) => a.key && a.label && a.icon));
});

test("the question tally: the last 7 days by outcome with the answered share, the 7 days before, and what held questions back", () => {
  const zero = { asked: 0, answered: 0, refused: 0, unanswered: 0 };
  assert.equal(tallyView(null), null);   // a viewer is not sent one
  assert.equal(tallyView({ last_7_days: zero, previous_7_days: zero, held_back: [] }), null);   // nothing asked: nothing to show
  const v = tallyView({
    last_7_days: { asked: 10, answered: 6, refused: 3, unanswered: 1 }, previous_7_days: { asked: 4, answered: 4, refused: 0, unanswered: 0 },
    held_back: [{ id: "meaning:order.状态码", kind: "meaning", name: "订单.状态码", questions: 3 }, { id: "type:order", kind: "type", name: "订单", questions: 1 }],
  });
  assert.deepEqual(v.figures.map((f) => [f.key, f.value]), [["asked", "10"], ["answered", "6"], ["refused", "3"], ["unanswered", "1"]]);
  assert.equal(v.figures[1].note, "占 60%");
  assert.equal(v.before, "再往前 7 天：问了 4 个，答了 4 个");
  assert.deepEqual(v.held.map((h) => [h.count, h.text, h.href]), [[3, "含义「订单.状态码」拦下了 3 个问题", "#/confirm"], [1, "对象类型「订单」拦下了 1 个问题", "#/confirm"]]);
  // a quiet week after a busy one still shows, with no share to work out
  const quiet = tallyView({ last_7_days: zero, previous_7_days: { asked: 4, answered: 4, refused: 0, unanswered: 0 }, held_back: [] });
  assert.deepEqual([quiet.figures[0].value, quiet.figures[1].note, quiet.held], ["0", "", []]);
});

// the demo workspace as a guest's type list shows it: Order confirmed, Customer waiting for a second look (name and who only)
const DEMO = [T("order", "Order"), { id: "customer", name: "Customer", state: "needs_look", waiting: true, waiting_for: ["demo-admin"] }];

test("a guest on the demo is offered three questions with three outcomes: an answer, a refusal for the type that waits, another answer", () => {
  assert.deepEqual(demoQuestions(DEMO), ["有效订单的总金额是多少？", "按 Customer 城市看有效订单金额", "已送达的订单有几笔？"]);   // the refused one says the type's name, which is how the service finds it
  assert.deepEqual(demoQuestions([T("order", "Order"), T("customer", "Customer")]), ["有效订单的总金额是多少？", "已送达的订单有几笔？"]);   // nothing waits: no refusal to show
  assert.equal(demoQuestions([T("ticket", "Ticket")]), null);   // not the demo's workspace: the usual examples
  assert.equal(demoQuestions([]), null);
  setLocale("en");
  try {
    assert.deepEqual(demoQuestions(DEMO), ["What is the total amount of valid orders?", "Valid order amount by customer city", "How many orders were delivered?"]);
  } finally {
    setLocale("zh");
  }
});

test("a guest's start cards: the board, why it can be trusted (the confirmed view), and the refusal asked for real, not a page elsewhere", () => {
  const cards = startCards({ dashboards: [{ id: 7 }] }, DEMO);
  assert.deepEqual(cards.map((c) => c.key), ["orders", "trust", "refuse"]);
  assert.equal(cards[0].href, "#/boards/7");
  assert.equal(cards[1].href, "#/types/order/views");
  assert.equal(cards[2].href, `#/qa?ask=${encodeURIComponent("按 Customer 城市看有效订单金额")}`);
  assert.ok(cards.every((c) => !c.external && !c.href.startsWith("http")));
  assert.match(t("home.start.refuse.text"), /Customer/);
  const plain = startCards(null, [T("ticket", "Ticket")]);   // not the demo's workspace: the boards list and the README as before
  assert.equal(plain[0].href, "#/boards");
  assert.equal(plain[2].external, true);
});
