import assert from "node:assert/strict";
import test from "node:test";

import { headlineStands, draftOf, draftProblem, emptyComponent, emptyDraft, expiryText, paramsIn, paramValues, payloadOf, refreshText, scopeText, shareLink, specOf } from "./boardModel.js";

const SAVED = {
  name: "订单看板", scope: "named", visible_to: [3], visible_names: ["Vera"], expires_at: "2026-12-01", refresh_seconds: 300,
  spec: { filters: [{ field: "状态码", label: "状态" }], components: [
    { id: "c1", title: "有效订单", query: { type: "order", view: "有效订单", filters: [], rows: null, pivot: null }, chart: { kind: "number", group: null, measure: null, fn: "count", bins: 10 } },
    { id: "c2", title: "最近", query: { type: "order", view: null, filters: [{ field: "金额", op: "gt", value: "5" }], rows: null, pivot: null }, chart: { kind: "rows" } }] },
};

test("who may open a board, when it ends and how often it reads, in words", () => {
  assert.equal(scopeText({ scope: "private" }), "只有我");
  assert.equal(scopeText({ scope: "everyone" }), "所有登录的人");
  assert.equal(scopeText(SAVED), "指定的人：Vera");
  assert.equal(scopeText({ scope: "named" }), "指定的人");   // a reader is not given the names
  assert.equal(expiryText({ expires_at: null }), "不过期");
  assert.equal(expiryText({ expires_at: "2026-12-01", expired: false }), "到 2026-12-01");
  assert.match(expiryText({ expires_at: "2026-11-01", expired: true }), /已过期，只有主人和管理员/);
  assert.equal(refreshText(0), "只在打开时读");
  assert.equal(refreshText(300), "每 5 分钟");
  assert.equal(refreshText(45), "每 45 秒");
});

test("the share link is the board's own address, not a copy of its data", () => {
  assert.equal(shareLink("http://127.0.0.1:5302", 4), "http://127.0.0.1:5302/#/boards/4");
});

test("a saved board becomes the form's draft and the draft becomes what the service reads, with the conditions kept", () => {
  const draft = draftOf(SAVED);
  assert.deepEqual(draft.components.map((c) => [c.id, c.type, c.view, c.kind]), [["c1", "order", "有效订单", "number"], ["c2", "order", "", "rows"]]);
  assert.deepEqual(specOf(draft).components[1], SAVED.spec.components[1]);
  assert.deepEqual(specOf(draft).components[0].chart, { kind: "number", group: null, measure: null, fn: "count", bins: 10, top: null, order: null });
  const ranked = { ...SAVED, spec: { ...SAVED.spec, components: [{ ...SAVED.spec.components[0], chart: { kind: "bar", group: "via:order_customer:客户名称", measure: "金额", fn: "sum", bins: 10, top: 10, order: "desc" } }] } };
  assert.deepEqual(specOf(draftOf(ranked)).components[0].chart, ranked.spec.components[0].chart);   // the top N and the order survive the form
  assert.deepEqual(specOf(draft).filters, SAVED.spec.filters);
  const sent = payloadOf(draft);
  assert.deepEqual([sent.scope, sent.visible_to, sent.expires_at, sent.refresh_seconds], ["named", [3], "2026-12-01", 300]);
  assert.deepEqual(payloadOf({ ...draft, scope: "everyone" }).visible_to, []);   // people named before are not sent once the scope is not "named"
  assert.equal(payloadOf({ ...draft, expires_at: "" }).expires_at, null);
});

test("the form says what is missing before it can be saved", () => {
  assert.equal(draftProblem(emptyDraft()), "要写看板的名字");
  assert.equal(draftProblem({ ...emptyDraft(), name: "x" }), "至少加一个组件");
  assert.equal(draftProblem({ ...emptyDraft(), name: "x", components: [emptyComponent("order", 1)] }), "第 1 个组件要写标题");
  assert.equal(draftProblem({ ...emptyDraft(), name: "x", scope: "named", components: [{ ...emptyComponent("order", 1), title: "t" }] }), "指定的人至少选一位");
  assert.equal(draftProblem({ ...emptyDraft(), name: "x", components: [{ ...emptyComponent("order", 1), title: "t" }] }), "");
});

test("the line at the top of a board stands out when anything on it is grey, waits for a confirmation or is closed to the reader", () => {
  assert.equal(headlineStands({ grey: [], waiting: [], unavailable: [] }), false);
  assert.equal(headlineStands({ grey: ["a"], waiting: [], unavailable: [] }), true);
  assert.equal(headlineStands({ grey: [], waiting: ["a"], unavailable: [] }), true);
  assert.equal(headlineStands({ grey: [], waiting: [], unavailable: ["a"] }), true);
});

const WITH_QUERY = {
  ...SAVED,
  spec: { filters: [], params: [{ name: "who", label: "客户", default: "KH001" }], components: [
    { id: "c1", title: "某客户的订单", text: "SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who", chart: { kind: "query" } },
    SAVED.spec.components[0]] },
};

test("a query card and the board's parameters go through the form unchanged", () => {
  const draft = draftOf(WITH_QUERY);
  assert.deepEqual([draft.components[0].kind, draft.components[0].text], ["query", WITH_QUERY.spec.components[0].text]);
  assert.deepEqual(specOf(draft).components[0], WITH_QUERY.spec.components[0]);   // no type, view or chart fields on a query card
  assert.deepEqual(specOf(draft).components[1], specOf(draftOf(SAVED)).components[0]);
  assert.deepEqual(specOf(draft).params, WITH_QUERY.spec.params);
  assert.deepEqual(specOf(draftOf(SAVED)).params, []);   // a board saved before parameters has none
  assert.deepEqual(specOf({ ...draft, params: [{ name: " who ", label: "", default: " KH001 " }] }).params, [{ name: "who", label: "who", default: "KH001" }]);
});

test("the form says what a query card or a parameter still needs", () => {
  const base = { ...emptyDraft(), name: "x", components: [{ ...emptyComponent("order", 1), kind: "query", text: "", title: "t" }] };
  assert.equal(draftProblem(base), "第 1 个组件要写查询");
  const using = { ...base, components: [{ ...base.components[0], text: "SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who" }] };
  assert.equal(draftProblem(using), "查询里用到 $who，要在参数里加上它和默认值");
  assert.equal(draftProblem({ ...using, params: [{ name: "who", label: "", default: "" }] }), "参数 $who 要写默认值");
  assert.equal(draftProblem({ ...using, params: [{ name: "who", label: "", default: "KH001" }, { name: "who", label: "", default: "x" }] }), "参数名 $who 重复了");
  assert.equal(draftProblem({ ...using, params: [{ name: "who", label: "", default: "KH001" }] }), "");
});

test("the $names a query uses, and the values a board is worked out with", () => {
  assert.deepEqual(paramsIn("SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who AND o.金额 >= $最少 AND o.x <> $who"), ["who", "最少"]);
  assert.deepEqual(paramsIn("SELECT count(o) FROM (o:订单) WHERE o.备注 = '$not' -- $nor"), []);   // inside a quoted value or a comment it is not a parameter
  assert.deepEqual(paramValues([{ name: "who", default: "KH001" }, { name: "min", default: "1" }], { who: "KH026", min: "", other: "x" }), { who: "KH026" });
});

test("a saved card switched to a query in the form has an empty query, not none", () => {
  const card = draftOf(SAVED).components[0];
  assert.equal(card.text, "");
  assert.equal(draftProblem({ ...draftOf(SAVED), visible_to: [3], components: [{ ...card, kind: "query" }] }), "第 1 个组件要写查询");
});
