import test from "node:test";
import assert from "node:assert/strict";
import { canBuild, isAdmin, roleLabel, statusText, twoPersonText } from "./authModel.js";

test("only a builder or an admin changes data", () => {
  assert.deepEqual(["viewer", "builder", "admin", undefined].map((role) => canBuild({ role })), [false, true, true, false]);
  assert.equal(canBuild(null), false);
  assert.deepEqual(["viewer", "builder", "admin"].map((role) => isAdmin({ role })), [false, false, true]);
});

test("roles and states are said in words", () => {
  assert.deepEqual(["viewer", "builder", "admin"].map(roleLabel), ["查看", "建设", "管理员"]);
  assert.equal(statusText({ disabled: true, must_change: true }), "已停用");
  assert.equal(statusText({ disabled: false, must_change: true }), "要先改初始密码");
  assert.equal(statusText({ disabled: false, must_change: false }), "正常");
});

test("the two-person line says whether the rule is on and whether it holds now", () => {
  assert.equal(twoPersonText({ enabled: true, builders: 3, active: true }), "两人确认：已开启，现在有 3 人能确认，生效中");
  assert.match(twoPersonText({ enabled: true, builders: 1, active: false }), /已开启，但现在有 1 人能确认，暂不生效/);
  assert.match(twoPersonText({ enabled: false, builders: 3, active: false }), /已关闭/);
});
