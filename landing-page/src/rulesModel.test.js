import assert from "node:assert/strict";
import test from "node:test";

import { adoptAll, ruleGroups, ruleStatus, rulesTile, toggleRule } from "./rulesModel.js";

const ontology = { object_types: [{ key: "contract", label: "合同" }, { key: "vendor", label: "供应商" }] };
const req = (type, field) => ({ id: `required:${type}:${field}`, kind: "required", type, field, holds: 3 });
const order = { id: "order:contract:签订:到期", kind: "order", type: "contract", before: "签订", after: "到期", holds: 3 };

test("candidate rules are grouped per object: required fields as one row, orders as arrows", () => {
  const groups = ruleGroups([req("contract", "金额"), order, req("vendor", "名称"), req("contract", "签订")], ontology);
  assert.deepEqual(groups.map((g) => [g.label, g.required.map((r) => r.field), g.orders.map((r) => `${r.before}→${r.after}`)]),
    [["合同", ["金额", "签订"], ["签订→到期"]], ["供应商", ["名称"], []]]);
});

test("adopting or declining sends the whole lists, and a rule moves from one to the other", () => {
  const state = { adopted: [], declined: [] };
  const a = toggleRule(state, "required:contract:金额", "adopt");
  assert.deepEqual(a, { adopted: ["required:contract:金额"], declined: [] });
  assert.deepEqual(toggleRule(a, "required:contract:金额", "decline"), { adopted: [], declined: ["required:contract:金额"] });
  assert.deepEqual(adoptAll(a, [req("contract", "金额"), req("contract", "签订")]), { adopted: ["required:contract:金额", "required:contract:签订"], declined: [] });
});

test("the rules chip says how many are adopted and how many are broken", () => {
  assert.deepEqual(rulesTile({ adopted: [], candidates: [order] }), { value: "1 条待看", tone: "muted" });
  assert.deepEqual(rulesTile({ adopted: [{ violations: { count: 0 } }, { violations: { count: 2 } }], candidates: [] }), { value: "1 / 2 条被违反", tone: "warn" });
  assert.deepEqual(rulesTile({ adopted: [{ violations: { count: 0 } }], candidates: [] }), { value: "1 条都守住", tone: "ok" });
  assert.equal(rulesTile(undefined), null);
});

test("a rule that could not be checked is never counted as kept", () => {
  const unchecked = { violations: null, unchecked: "这次的本体里没有对象 vendor" };
  assert.deepEqual(rulesTile({ adopted: [{ violations: { count: 0 } }, unchecked], candidates: [] }), { value: "1 / 2 条无法检查", tone: "warn" });
  assert.deepEqual(rulesTile({ adopted: [{ violations: { count: 2 } }, unchecked], candidates: [] }), { value: "1 条被违反，1 条无法检查", tone: "warn" });
  assert.deepEqual(ruleStatus(unchecked), { kind: "unchecked", mark: "?", label: "无法检查：这次的本体里没有对象 vendor" });
  assert.deepEqual(ruleStatus({ violations: { count: 3 } }), { kind: "broken", mark: "✕ 3", label: "3 个违反" });
  assert.deepEqual(ruleStatus({ violations: { count: 0 } }), { kind: "kept", mark: "✓", label: "都守住" });
});
