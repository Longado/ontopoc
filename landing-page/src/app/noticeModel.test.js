import assert from "node:assert/strict";
import test from "node:test";
import { noticeLink } from "./noticeModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("a notice about a definition that went back links to it: to confirm it when this person may, else only to open it", () => {
  assert.deepEqual(noticeLink({ definition: { kind: "type", id: "order", state: "needs_look", can_confirm: true } }), { href: "#/types/order/props", label: "去确认" });
  assert.deepEqual(noticeLink({ definition: { kind: "meaning", id: "order", column: "状态码", state: "needs_look", can_confirm: false } }), { href: "#/types/order/props", label: "打开看看" });
  assert.equal(noticeLink({ definition: { kind: "relation", id: "order_customer", can_confirm: true } }).href, "#/relations/order_customer");
  assert.equal(noticeLink({ definition: { kind: "view", id: "order", can_confirm: false } }).href, "#/types/order/views");
  assert.equal(noticeLink({ definition: { kind: "pipeline", id: "清洗订单", can_confirm: true } }).href, `#/pipelines/${encodeURIComponent("清洗订单")}/confirm`);
});

test("a notice from an action carries no link", () => {
  assert.equal(noticeLink({ action: "改交付天数", record: 3, text: "…" }), null);
  assert.equal(noticeLink({ action: "改交付天数", record: 3, definition: null }), null);
});
