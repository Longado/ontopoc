import assert from "node:assert/strict";
import test from "node:test";

import { draftOf, draftProblem, emptyComponent, emptyDraft, expiryText, payloadOf, refreshText, scopeText, shareLink, specOf } from "./boardModel.js";

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
  assert.deepEqual(specOf(draft).components[0].chart, { kind: "number", group: null, measure: null, fn: "count", bins: 10 });
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
