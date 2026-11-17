import assert from "node:assert/strict";
import test from "node:test";
import { derivedPayload, derivedProblem, emptyDerivedForm, formFromLine, nextRelations, offerChange, sampleText, usedByText, waitingText } from "./derivedModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests pin the Chinese wording; the English is in modelingEnglish.test.js

const AGG = { count: "计数", latest: "取最新", median: "中位数" };
const statistic = (over = {}) => ({ ...emptyDerivedForm(), name: "已取消订单数", english_name: "cancelled_orders", path: ["order_customer"], ...over });

test("a statistic that crosses a many side needs a way to make the rows one, and a lookup needs none", () => {
  const many = { many: true, measured: { columns: [] } };
  assert.match(derivedProblem(statistic(), many), /统计方式/);
  assert.equal(derivedProblem(statistic({ fn: "count" }), many), "");   // counting rows needs no column
  assert.match(derivedProblem(statistic({ fn: "median" }), many), /哪一列/);
  assert.match(derivedProblem(statistic({ fn: "latest", column: "库存数量" }), many), /比先后/);
  assert.match(derivedProblem(statistic({ column: "" }), { many: false, measured: { columns: [] } }), /哪一列/);
  assert.equal(derivedProblem(statistic({ column: "单价" }), { many: false, measured: { columns: [] } }), "");
});

test("the name, the English name and the formula are asked for first", () => {
  assert.match(derivedProblem({ ...emptyDerivedForm("function"), english_name: "gross" }, null), /名称/);
  assert.match(derivedProblem({ ...emptyDerivedForm("function"), name: "含税", english_name: "1x" }, null), /英文名/);
  assert.match(derivedProblem({ ...emptyDerivedForm("function"), name: "含税", english_name: "gross" }, null), /算式/);
  assert.match(derivedProblem(statistic({ path: [] }), null), /路径/);
});

test("the payload of a statistic drops empty conditions and writes latest only for 取最新; a formula sends only its text", () => {
  const form = statistic({ fn: "latest", column: "库存数量", latest: { order: "快照月份", tie: "" }, conditions: [{ column: "", op: "is", label: "" }, { column: "状态码", op: "is", label: "已取消" }] });
  assert.deepEqual(derivedPayload("product", form), {
    type: "product", kind: "statistic", english_name: "cancelled_orders", name: "已取消订单数", description: "", path: ["order_customer"], measure: { column: "库存数量" }, fn: "latest",
    latest: { order: "快照月份", tie: null }, conditions: [{ column: "状态码", op: "is", label: "已取消" }],
  });
  assert.equal(derivedPayload("p", statistic({ fn: "count" })).latest, null);
  assert.deepEqual(derivedPayload("order", { ...emptyDerivedForm("function"), name: " 含税金额 ", english_name: "gross", expression: " 金额 * 1.13 " }),
    { type: "order", kind: "function", english_name: "gross", name: "含税金额", description: "", expression: "金额 * 1.13" });
});

test("editing starts from the saved definition", () => {
  const line = { definition: { kind: "statistic", name: "当前库存", english_name: "stock_now", description: "", path: ["stock_product"], measure: { column: "库存数量" }, fn: "latest", latest: { order: "快照月份", tie: null }, conditions: [] } };
  const form = formFromLine(line);
  assert.deepEqual([form.path, form.column, form.fn, form.latest.order, form.conditions.length], [["stock_product"], "库存数量", "latest", "快照月份", 1]);
  assert.equal(formFromLine({ definition: { ...line.definition, fn: "value" } }).fn, "");   // a lookup has no aggregation to show
});

test("a path goes on from the type it has reached and does not turn straight back", () => {
  const relations = [{ key: "a", from: "order", to: "customer" }, { key: "b", from: "order", to: "product" }, { key: "c", from: "stock", to: "product" }];
  assert.deepEqual(nextRelations(relations, "customer", []).map((r) => r.key), ["a"]);
  assert.deepEqual(nextRelations(relations, "customer", [{ relation: "a", to_type: "order" }]).map((r) => r.key), ["b"]);
});

test("a refused aggregation comes with a button that makes the change it offers", () => {
  const form = statistic({ fn: "sum", column: "库存数量" });
  const change = offerChange(form, { fn: "latest", order: "快照月份" }, AGG);
  assert.match(change.label, /快照月份/);
  assert.deepEqual([change.apply().fn, change.apply().latest.order, change.apply().column], ["latest", "快照月份", "库存数量"]);
  assert.equal(offerChange(form, { fn: "median" }, AGG).apply().fn, "median");
});

test("the small sentences", () => {
  assert.equal(usedByText({ answers: 2, views: 0, actions: 0 }), "用于 2 个回答 / 0 个视图 / 0 个行为");
  assert.equal(waitingText({ waiting_on: [{ name: "订单属于客户" }] }), "要先确认“订单属于客户”，才能确认这个派生属性");
  assert.equal(waitingText({ waiting_on: [] }), "");
  assert.equal(sampleText({ label: "样本", inputs: [{ column: "金额", value: "2520" }], result: "2847.6" }), "样本：金额 = 2520，结果 2847.6");
});
