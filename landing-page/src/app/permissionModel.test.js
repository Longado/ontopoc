import assert from "node:assert/strict";
import test from "node:test";

import { attrNames, cutOff, loseAccess, prefilledRule, ruleText, seers } from "./permissionModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests assert the Chinese words; the English ones are in english.test.js

const PEOPLE = [
  { id: 1, name: "管理员", role: "admin" },
  { id: 2, name: "Ann", role: "builder" },
  { id: 3, name: "Bob", role: "builder" },
  { id: 4, name: "Vera", role: "viewer" },
];

test("the people who see a type now: everyone, or the ones listed; never the admin; a viewer only when it is confirmed", () => {
  assert.deepEqual(seers({ everyone: true, user_ids: [], state: "confirmed" }, PEOPLE).map((p) => p.name), ["Ann", "Bob", "Vera"]);
  assert.deepEqual(seers({ everyone: true, user_ids: [], state: "proposed" }, PEOPLE).map((p) => p.name), ["Ann", "Bob"]);
  assert.deepEqual(seers({ everyone: false, user_ids: [3, 4], state: "confirmed" }, PEOPLE).map((p) => p.name), ["Bob", "Vera"]);
});

test("a rule list leaves out the people who see the type and are named by none of its rules", () => {
  const type = { everyone: true, user_ids: [], state: "confirmed" };
  const rules = [{ column: "区域", value: "华东", user_ids: [2] }];
  assert.deepEqual(cutOff(type, PEOPLE, rules).map((p) => p.name), ["Bob", "Vera"]);
  assert.deepEqual(cutOff(type, PEOPLE, [...rules, { column: "", value: "", user_ids: [3, 4] }]), []);
  assert.deepEqual(cutOff(type, PEOPLE, []), []);   // no rules: nobody is cut off
});

test("the first rule comes with an all-rows entry for the people it does not name, so the admin removes it on purpose", () => {
  const type = { everyone: true, user_ids: [], state: "confirmed", row_rules: [] };
  const rule = { column: "区域", value: "华东", user_ids: [2] };
  assert.deepEqual(prefilledRule(type, PEOPLE, rule), { column: "", value: "", user_ids: [3, 4], prefilled: true });
  assert.equal(prefilledRule({ ...type, row_rules: [rule] }, PEOPLE, rule), null);   // not the first rule
  assert.equal(prefilledRule(type, PEOPLE, { ...rule, user_ids: [2, 3, 4] }), null);   // nobody left to name
});

test("turning off a list loses nobody; taking people off a list, or closing the type to everyone, names who loses it", () => {
  const everyone = { everyone: true, user_ids: [], state: "confirmed" };
  assert.deepEqual(loseAccess(everyone, [2], PEOPLE).map((p) => p.name), ["Bob", "Vera"]);
  assert.deepEqual(loseAccess(everyone, [], PEOPLE).map((p) => p.name), ["Ann", "Bob", "Vera"]);
  const listed = { everyone: false, user_ids: [2, 3], state: "confirmed" };
  assert.deepEqual(loseAccess(listed, [2], PEOPLE).map((p) => p.name), ["Bob"]);
  assert.deepEqual(loseAccess(listed, [2, 3, 4], PEOPLE), []);
});

test("a rule on each person's own attribute covers the people who have that attribute, and the first one prefills all rows for the rest", () => {
  const people = [{ id: 1, name: "管理员", role: "admin" }, { id: 2, name: "Ann", role: "builder", attrs: { 部门: "华东" } },
    { id: 3, name: "Bob", role: "builder", attrs: { 部门: "" } }, { id: 4, name: "Vera", role: "viewer", attrs: { 岗位: "销售" } }];
  const type = { everyone: true, user_ids: [], state: "confirmed", row_rules: [] };
  const rule = { column: "区域", value: "", user_ids: [], user_attr: "部门" };
  assert.deepEqual(cutOff(type, people, [rule]).map((p) => p.name), ["Bob", "Vera"]);
  assert.deepEqual(prefilledRule(type, people, rule), { column: "", value: "", user_ids: [3, 4], prefilled: true });
  assert.equal(ruleText(rule, "区域", ""), "每个人看 区域 = 自己的部门 的行");
  assert.equal(ruleText({ column: "区域", value: "华东", user_ids: [2] }, "区域", "Ann"), "Ann 看 区域 = 华东 的行");
  assert.equal(ruleText({ column: "", value: "", user_ids: [2] }, "", "Ann"), "Ann 看全部行");
  assert.deepEqual(attrNames(people), ["岗位", "部门"].sort());
});
