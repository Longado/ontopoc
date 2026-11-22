import assert from "node:assert/strict";
import test from "node:test";

import { setLocale } from "./i18n/index.js";
import { dateMates, ruleChecks, ruleExamples, rulePayload, ruleReady, rulesOfType, ruleStanding, typePayload } from "./typeModel.js";

const columns = [
  { name: "金额", declared: "decimal", enum: false }, { name: "状态", declared: "text", enum: true }, { name: "备注", declared: "text", enum: false },
  { name: "下单日期", declared: "date", enum: false }, { name: "发货时间", declared: "datetime", enum: false }, { name: "月份", declared: "month", enum: false },
];
const col = (name) => columns.find((c) => c.name === name);

test("a property is offered only the rules its type can take", () => {
  assert.deepEqual(ruleChecks(col("金额"), columns), ["not_empty", "gt", "ge", "lt", "le", "between"]);
  assert.deepEqual(ruleChecks(col("状态"), columns), ["not_empty", "in_codes"]);
  assert.deepEqual(ruleChecks(col("备注"), columns), ["not_empty"]);   // a text column: only "not empty"
  assert.deepEqual(ruleChecks(col("下单日期"), columns), ["not_empty", "not_before"]);
  assert.deepEqual(ruleChecks(col("月份"), columns), ["not_empty"]);   // no other month to compare with
  assert.deepEqual(dateMates(columns, col("下单日期")).map((c) => c.name), ["发货时间"]);
});

test("a rule is sent with only what its kind needs, and is ready once that is filled in", () => {
  assert.deepEqual(rulePayload({ column: "金额", check: "gt", value: " 0 ", low: "1", high: "2", other: "x" }), { column: "金额", check: "gt", value: "0" });
  assert.deepEqual(rulePayload({ column: "金额", check: "between", value: "", low: "1", high: "50" }), { column: "金额", check: "between", low: "1", high: "50" });
  assert.deepEqual(rulePayload({ column: "发货时间", check: "not_before", other: "下单日期" }), { column: "发货时间", check: "not_before", other: "下单日期" });
  assert.deepEqual(rulePayload({ column: "备注", check: "not_empty", value: "9" }), { column: "备注", check: "not_empty" });
  assert.equal(ruleReady({ column: "金额", check: "gt", value: "" }), false);
  assert.equal(ruleReady({ column: "金额", check: "between", low: "1", high: "" }), false);
  assert.equal(ruleReady({ column: "发货时间", check: "not_before", other: "" }), false);
  assert.equal(ruleReady({ column: "", check: "not_empty" }), false);
  assert.equal(ruleReady({ column: "状态", check: "in_codes" }), true);
});

test("a saved type's rules come back as form rows, and a form with no rules sends an empty list", () => {
  assert.deepEqual(rulesOfType({ rules: [{ column: "金额", check: "gt", value: 0, says: "x", broken: 3, examples: [] }] }), [{ column: "金额", check: "gt", value: 0, low: "", high: "", other: "" }]);
  assert.deepEqual(rulesOfType({}), []);
  const form = { english: "order", name: "订单", description: "", dataset: "订单", key: ["订单号"], columns: [{ name: "订单号", include: true, label: "", declared: "text", enum: false }] };
  assert.equal("rules" in typePayload(form), false);
  assert.deepEqual(typePayload({ ...form, rules: [] }).rules, []);
  assert.deepEqual(typePayload({ ...form, rules: [{ column: "订单号", check: "not_empty" }] }).rules, [{ column: "订单号", check: "not_empty" }]);
});

test("how a rule stands reads in both languages, and says when the count is of the reader's own rows", () => {
  setLocale("zh");
  assert.equal(ruleStanding({ broken: 3 }, false), "现在有 3 行不满足");
  assert.equal(ruleStanding({ broken: 0 }, true), "你能看到的行里现在没有行不满足");
  assert.equal(ruleStanding({ broken: null }, false), "现在没法检查");
  assert.equal(ruleExamples({ examples: [["DD1"], ["DD2", "1"]] }), "DD1、DD2 + 1");
  setLocale("en");
  assert.equal(ruleStanding({ broken: 1 }, false), "1 row breaks it now");
  assert.equal(ruleStanding({ broken: 3 }, true), "3 of the rows you can see break it now");
  assert.equal(ruleStanding({ broken: 0 }, false), "No row breaks it now");
  assert.equal(ruleExamples({ examples: [["DD1"], ["DD2", "1"]] }), "DD1, DD2 + 1");
  setLocale("zh");
});
