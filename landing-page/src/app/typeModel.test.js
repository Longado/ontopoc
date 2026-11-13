import assert from "node:assert/strict";
import test from "node:test";

import { codeCell, confirmersText, keyProblem, logText, stateLine, stateText, typePayload } from "./typeModel.js";

test("the chip says what a person needs to know: a model's draft is not an ordinary proposal", () => {
  assert.equal(stateText({ state: "proposed", model_draft: true }), "模型草稿");
  assert.equal(stateText({ state: "checked" }), "已检查");
  assert.equal(stateText({ state: "needs_look" }), "需再看");
  assert.equal(stateText({ state: null }), "还没有含义");
});

test("the proposer is told another builder must confirm; another builder is told they may", () => {
  const waiting = { state: "checked", proposed_by: "Ann", can_confirm: false, confirmers: ["Bob", "管理员"] };
  assert.equal(stateLine(waiting, "这个对象类型"), "Ann 提出，需要另一位构建者确认");
  assert.equal(confirmersText(waiting), "可以确认的人：Bob、管理员");
  const mine = { ...waiting, can_confirm: true };
  assert.equal(stateLine(mine, "这个对象类型"), "Ann 提出，等你或另一位构建者确认");
  assert.equal(confirmersText(mine), "");
});

test("a confirmation names who, when and on which dataset version; a type that needs another look still names who had confirmed it", () => {
  const confirmed = { state: "confirmed", confirmed_by: "Bob", confirmed_at: "2026-11-14T08:30:00+00:00", confirmed_on: { 订单: 1 } };
  assert.match(stateLine(confirmed, "x"), /^Bob 于 .+ 确认，依据 订单 第 1 版$/);
  assert.match(stateLine({ ...confirmed, state: "needs_look" }, "x"), /^原来是 Bob 于 .+ 确认，依据 订单 第 1 版；之后数据变了，要再看一次$/);
});

test("the log reads as sentences, with the reason a confirmation was sent back and whose upload it was", () => {
  assert.deepEqual(logText({ element: "meaning", column: "状态码", change: "needs_look", reason: "取值变了", caused_by: "Ann" }), { who: "系统", text: "“状态码”的含义需再看：取值变了（Ann 的上传）" });
  assert.deepEqual(logText({ element: "type", change: "confirmed", who: "Bob", self_confirmed: false }), { who: "Bob", text: "确认了对象类型" });
  assert.match(logText({ element: "type", change: "confirmed", who: "root", self_confirmed: true }).text, /两人确认没有生效/);
  assert.deepEqual(logText({ element: "dataset", change: "import v2: 160 rows in the file, 160 stored, 0 dropped", who: "Ann" }), { who: "Ann", text: "上传了第 2 版" });
  assert.deepEqual(logText({ element: "type", change: "checked", who: "Ann" }), { who: "Ann", text: "提出了对象类型" });
});

test("a code is shown with its meaning only while the meaning is confirmed", () => {
  const labels = { 2: "已取消" };
  assert.deepEqual(codeCell("2", { state: "confirmed", labels }), { value: "2", note: "已取消" });
  assert.deepEqual(codeCell("2", { state: "checked", labels }), { value: "2", note: "含义未确认" });
  assert.deepEqual(codeCell("2", { state: "needs_look", labels }), { value: "2", note: "含义需再看" });
  assert.deepEqual(codeCell("3", { state: "confirmed", labels }), { value: "3", note: "含义未确认" });
});

test("a decimal or yes/no key is refused before anything is sent", () => {
  assert.match(keyProblem({ name: "交付天数P50", type: "decimal" }), /小数/);
  assert.match(keyProblem({ name: "是否", type: "boolean" }), /是\/否/);
  assert.equal(keyProblem({ name: "订单号", type: "text" }), "");
});

test("the payload carries the key columns even when unticked, and only the meanings that were written", () => {
  const form = {
    english: " order ", name: "订单", description: "", dataset: "订单", key: ["订单号"],
    columns: [
      { name: "订单号", type: "text", include: false, label: "", declared: "text", enum: false },
      { name: "状态码", type: "integer", include: true, label: "状态", declared: "integer", enum: true, meanings: { 0: "已交付", 1: " ", 2: "已取消" } },
      { name: "金额", type: "integer", include: false, label: "", declared: "integer", enum: false },
    ],
  };
  const payload = typePayload(form);
  assert.deepEqual(payload.properties.map((p) => p.column), ["订单号", "状态码"]);
  assert.equal(payload.english_name, "order");
  assert.deepEqual(payload.enums, { 状态码: [{ value: "0", label: "已交付" }, { value: "2", label: "已取消" }] });
  assert.equal(payload.properties[1].name, "状态");
});
