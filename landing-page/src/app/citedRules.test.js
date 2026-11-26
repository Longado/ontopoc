import assert from "node:assert/strict";
import test from "node:test";

import { setLocale } from "./i18n/index.js";
import { citeLine, conflictLine, conflictNoteLine, reportOnlyTag, RULE_CHECKS, ruleChecks, rulePayload, ruleReady, rulesOfType } from "./typeModel.js";

const columns = [{ name: "fault", declared: "text", enum: false }, { name: "lock_state", declared: "text", enum: true }, { name: "金额", declared: "decimal", enum: false }];
const cite = { document: "document:abc", passage: "p2", quote: "门锁状态 lock_state 必须置为 1" };

test("a conditional rule is offered on every property of a type that has another one", () => {
  assert.ok(RULE_CHECKS.includes("when"));
  assert.ok(ruleChecks(columns[1], columns).includes("when"));
  assert.ok(ruleChecks(columns[2], columns).includes("when"));
  assert.equal(ruleChecks(columns[0], [columns[0]]).includes("when"), false);   // no other property to put in a condition
});

test("a conditional rule is sent with its conditions, one value or a list, and its citation", () => {
  const row = { column: "lock_state", check: "when", conditions: [{ column: "fault", value: " power_loss " }], value: " 1 ", values: "", list: false, cite };
  assert.deepEqual(rulePayload(row), { column: "lock_state", check: "when", when: [{ column: "fault", equals: "power_loss" }], equals: "1", cite });
  assert.deepEqual(rulePayload({ ...row, list: true, values: "1, 4 ,", cite: null }), { column: "lock_state", check: "when", when: [{ column: "fault", equals: "power_loss" }], one_of: ["1", "4"] });
  assert.deepEqual(rulePayload({ column: "金额", check: "gt", value: "0", cite }), { column: "金额", check: "gt", value: "0", cite });   // any kind may cite
  assert.deepEqual(rulePayload({ column: "金额", check: "gt", value: "0", cite: { document: "", passage: "", quote: "" } }), { column: "金额", check: "gt", value: "0" });
  assert.equal(ruleReady(row), true);
  assert.equal(ruleReady({ ...row, conditions: [] }), false);
  assert.equal(ruleReady({ ...row, conditions: [{ column: "fault", value: "" }] }), false);
  assert.equal(ruleReady({ ...row, value: "" }), false);
  assert.equal(ruleReady({ ...row, list: true, values: " , " }), false);
  assert.equal(ruleReady({ ...row, conditions: Array(4).fill({ column: "fault", value: "x" }) }), false);   // at most 3 conditions
  assert.equal(ruleReady({ ...row, cite: { document: "document:abc", passage: "", quote: "x" } }), false);   // a citation is whole or absent
});

test("a saved conditional rule comes back as a form row with its citation; a stale citation is kept without its quote", () => {
  const saved = { column: "lock_state", check: "when", when: [{ column: "fault", equals: "power_loss" }], one_of: ["1", "4"], says: "x", broken: 2, examples: [],
    cite: { ...cite, name: "door-spec.md", where: "第 2 段" } };
  assert.deepEqual(rulesOfType({ rules: [saved] }), [{ column: "lock_state", check: "when", value: "", low: "", high: "", other: "", conditions: [{ column: "fault", value: "power_loss" }],
    list: true, values: "1, 4", cite }]);
  const stale = { ...saved, one_of: undefined, equals: "1", cite: { document: "document:abc", passage: "p2", name: "door-spec.md", stale: "x" } };
  assert.deepEqual(rulesOfType({ rules: [stale] })[0].cite, { document: "document:abc", passage: "p2", quote: "" });
  assert.equal("cite" in rulesOfType({ rules: [{ column: "金额", check: "gt", value: 0 }] })[0], false);   // a rule without one keeps the shape it had
  assert.deepEqual(rulesOfType({ rules: [{ column: "金额", check: "gt", value: 0, cite: { ...cite, name: "x", where: "y" } }] })[0].cite, cite);
});

test("a citation, a conflict and its note read in both languages", () => {
  setLocale("zh");
  assert.equal(citeLine({ name: "door-spec.md", where: "第 2 段", quote: "必须置为 1" }), "依据《door-spec.md》第 2 段：“必须置为 1”");
  assert.equal(citeLine({ name: "door-spec.md", stale: "文档被退回了" }), "引用的《door-spec.md》需要再看：文档被退回了");
  assert.equal(citeLine(undefined), "");
  assert.equal(conflictLine({ says: "两条规则冲突", rows: 4 }), "两条规则冲突：现在有 4 行同时满足两条的条件");
  assert.equal(conflictLine({ says: "两条规则冲突", rows: null }), "两条规则冲突");
  assert.equal(conflictNoteLine({ asked: "王工", proposed_by: "Ann", state: "checked" }), "已知：问过 王工（Ann 记下，等另一位确认）");
  setLocale("en");
  assert.equal(citeLine({ name: "door-spec.md", where: "paragraph 2", quote: "set to 1" }), "From “door-spec.md”, paragraph 2: “set to 1”");
  assert.equal(citeLine({ name: "door-spec.md", stale: "it was sent back" }), "The cited “door-spec.md” needs another look: it was sent back");
  assert.equal(conflictLine({ says: "The rules disagree", rows: 1 }), "The rules disagree: 1 row meets both conditions now");
  assert.equal(conflictNoteLine({ asked: "Wang", proposed_by: "Ann", state: "checked" }), "Known: asked Wang (noted by Ann, waiting for a second person to confirm)");
  setLocale("zh");
});

test("a rule marked report only is sent and read back as such; a rule without the mark keeps its shape", () => {
  assert.deepEqual(rulePayload({ column: "金额", check: "gt", value: "0", reportOnly: true }), { column: "金额", check: "gt", value: "0", report_only: true });
  assert.deepEqual(rulePayload({ column: "金额", check: "gt", value: "0", reportOnly: false }), { column: "金额", check: "gt", value: "0" });
  assert.equal(rulesOfType({ rules: [{ column: "金额", check: "gt", value: 0, report_only: true }] })[0].reportOnly, true);
  assert.equal("reportOnly" in rulesOfType({ rules: [{ column: "金额", check: "gt", value: 0 }] })[0], false);
  setLocale("zh");
  assert.equal(reportOnlyTag({ report_only: true }), "只报告：不满足的行只列出来，不拦着确认");
  assert.equal(reportOnlyTag({}), "");
  setLocale("en");
  assert.equal(reportOnlyTag({ report_only: true }), "Report only: the rows that break it are listed; they do not stop confirming");
  setLocale("zh");
});

test("a citation's whole sentence comes with the quoted part marked, by the same function a document answer uses", async () => {
  const { sentenceParts } = await import("./documentModel.js");
  const { citeParts, citeSource } = await import("./typeModel.js");
  assert.equal(citeParts, sentenceParts);
  assert.deepEqual(citeParts({ quote: "必须置为 1", sentence: "DS-1 掉电后，必须置为 1（上锁）。", mark: [9, 15] }), ["DS-1 掉电后，", "必须置为 1", "（上锁）。"]);
  assert.deepEqual(citeParts({ quote: "必须置为 1" }), ["", "必须置为 1", ""]);
  setLocale("zh");
  assert.equal(citeSource({ name: "door-spec.md", where: "第 2 段" }), "依据《door-spec.md》第 2 段：");
  setLocale("en");
  assert.equal(citeSource({ name: "door-spec.md", where: "paragraph 2" }), "From “door-spec.md”, paragraph 2:");
  setLocale("zh");
});

test("a half-filled citation holds back every kind of rule, and a type sent back by a definition change does not say the data changed", async () => {
  const half = { document: "document:abc", passage: "", quote: "x" };
  for (const rule of [{ column: "金额", check: "gt", value: "0" }, { column: "金额", check: "between", low: "1", high: "2" }, { column: "下单日期", check: "not_before", other: "发货时间" },
    { column: "fault", check: "not_empty" }, { column: "lock_state", check: "in_codes" }]) {
    assert.equal(ruleReady(rule), true, rule.check);
    assert.equal(ruleReady({ ...rule, cite: half }), false, rule.check);
  }
  const { stateLine } = await import("./typeModel.js");
  const item = { state: "needs_look", confirmed_by: "Bob", confirmed_at: null, confirmed_on: { door_events: 1 } };
  setLocale("en");
  assert.match(stateLine({ ...item, cause: "data" }, "type"), /data has changed/);
  assert.doesNotMatch(stateLine({ ...item, cause: "definition" }, "type"), /data/);
  assert.match(stateLine({ ...item, cause: "definition" }, "type"), /definition/);
  setLocale("zh");
  assert.doesNotMatch(stateLine({ ...item, cause: "definition" }, "type"), /数据变了/);
});
