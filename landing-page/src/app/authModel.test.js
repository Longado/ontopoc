import test from "node:test";
import assert from "node:assert/strict";
import { canBuild, isAdmin, roleLabel, searchPlaceholder, statusText, twoPersonText } from "./authModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

test("only a builder or an admin changes data", () => {
  assert.deepEqual(["viewer", "builder", "admin", undefined].map((role) => canBuild({ role })), [false, true, true, false]);
  assert.equal(canBuild(null), false);
  assert.deepEqual(["viewer", "builder", "admin"].map((role) => isAdmin({ role })), [false, false, true]);
});

test("roles and states are said in words", () => {
  assert.deepEqual(["viewer", "builder", "admin"].map(roleLabel), ["查看者", "建设者", "管理员"]);
  assert.equal(statusText({ disabled: true, must_change: true }), "已停用");
  assert.equal(statusText({ disabled: false, must_change: true }), "要先改初始密码");
  assert.equal(statusText({ disabled: false, must_change: false }), "正常");
});

test("the two-person line says whether the rule is on and whether it holds now", () => {
  assert.equal(twoPersonText({ enabled: true, builders: 3, active: true }), "两人确认：开着。一个人建的东西，要另一个建设者确认才算数。现在能确认的有 3 人");
  assert.equal(twoPersonText({ enabled: true, builders: 1, active: false }), "两人确认：开着，但现在能确认的只有 1 人，所以暂时自己确认自己建的也算数。有第二个人能确认时，自动按两人确认来");
  assert.equal(twoPersonText({ enabled: false, builders: 3, active: false }), "两人确认：关着。一个人建的东西，自己确认就算数");
});

test("the search box speaks business words to a viewer and builder words to a builder", () => {
  assert.equal(searchPlaceholder({ role: "viewer" }), "搜索看板、问题…");
  assert.equal(searchPlaceholder({ role: "builder" }), "搜索数据集、对象类型、管道…");
  assert.equal(searchPlaceholder({ role: "admin" }), "搜索数据集、对象类型、管道…");
  assert.equal(searchPlaceholder(null), "搜索数据集、对象类型、管道…");
});
