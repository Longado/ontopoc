import assert from "node:assert/strict";
import test from "node:test";

import { barRows, chartMissing, chartSpec, emptyFilter, fnOptions, formatNumber, greyText, histogramBars, leftOutLines, opsFor, pieSlices, pivotQuery, queryFromParam, queryOf, queryToParam, readyFilters, sliceColor } from "./explorerModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests pin the Chinese wording; the English is in modelingEnglish.test.js

const AGGREGATIONS = { sum: "求和", count: "计数", count_distinct: "去重计数", avg: "平均", min: "最小", max: "最大", median: "中位数", p25: "P25", p75: "P75" };

test("size comparisons are offered only where the values can be put in order", () => {
  assert.deepEqual(opsFor({ ordered: false }), ["eq", "ne", "contains", "empty", "filled"]);
  assert.deepEqual(opsFor({ ordered: true }), ["eq", "ne", "contains", "empty", "filled", "gt", "ge", "lt", "le"]);
});

test("a filter with nothing to compare to is left out until it has a value; empty and filled need none", () => {
  const filters = [{ field: "金额", op: "gt", value: "" }, { field: "金额", op: "gt", value: " 50000 " }, { field: "客户等级", op: "empty", value: "x" }, { field: "", op: "eq", value: "1" }];
  assert.deepEqual(readyFilters(filters), [{ field: "金额", op: "gt", value: " 50000 " }, { field: "客户等级", op: "empty", value: "" }]);
  assert.deepEqual(queryOf({ type: "order", view: "", filters: [emptyFilter([{ key: "状态码" }])] }), { type: "order", view: null, filters: [], rows: null, pivot: null });
});

test("a number may have every aggregation, anything else counting and the extremes, no measure only counting rows", () => {
  assert.deepEqual(fnOptions({ numeric: true }, AGGREGATIONS), Object.keys(AGGREGATIONS));
  assert.deepEqual(fnOptions({ numeric: false }, AGGREGATIONS), ["count", "count_distinct", "min", "max"]);
  assert.deepEqual(fnOptions(null, AGGREGATIONS), ["count"]);
});

test("a chart says what it still needs before it can be asked for", () => {
  assert.equal(chartMissing({ kind: "bar", group: "", measure: "", fn: "count" }), "选按哪一列分组");
  assert.equal(chartMissing({ kind: "bar", group: "状态码", measure: "", fn: "count" }), "");
  assert.equal(chartMissing({ kind: "histogram", measure: "", fn: "count" }), "选一个数字列来量");
  assert.equal(chartMissing({ kind: "number", measure: "", fn: "sum" }), "选要统计的列");
  assert.equal(chartMissing({ kind: "number", measure: "", fn: "count" }), "");
  assert.deepEqual(chartSpec({ kind: "bar", group: "状态码", measure: "", fn: "", bins: undefined }), { kind: "bar", group: "状态码", measure: null, fn: "count", bins: 10, top: null, order: null });
  assert.deepEqual(chartSpec({ kind: "bar", group: "客户编号", top: "5", order: "desc" }), { kind: "bar", group: "客户编号", measure: null, fn: "count", bins: 10, top: 5, order: "desc" });
});

test("numbers read with separators, two decimals at most, and an empty value is a dash", () => {
  assert.equal(formatNumber(1234567), "1,234,567");
  assert.equal(formatNumber(1234.5678), "1,234.57");
  assert.equal(formatNumber(0), "0");
  assert.equal(formatNumber(null), "—");
  assert.equal(formatNumber("12.50"), "12.5");
});

test("a result is grey with the reason from the bottom of the chain, and in colour with nothing said when it is confirmed", () => {
  assert.equal(greyText({ confirmed: true, why: null }), "");
  assert.equal(greyText({ confirmed: false, why: "含义「订单.状态码」：订单 第 2 版里取值变了" }), "含义「订单.状态码」：订单 第 2 版里取值变了");
  assert.equal(greyText({ confirmed: false, why: null }), "用到的定义现在不是已确认的状态");
});

test("bars are as wide as their share of the biggest value", () => {
  const rows = barRows([{ label: "a", value: 10, rows: 3 }, { label: "b", value: 5, rows: 2 }, { label: "c", value: 0, rows: 1 }]);
  assert.deepEqual(rows.map((r) => r.fraction), [1, 0.5, 0]);
  assert.deepEqual(barRows([]), []);
  assert.deepEqual(barRows([{ label: "z", value: 0 }]).map((r) => r.fraction), [0]);   // nothing to divide by is not a bar
  assert.deepEqual(histogramBars([{ from: 0, to: 1, count: 4 }, { from: 1, to: 2, count: 1 }]).map((b) => b.fraction), [1, 0.25]);
});

test("pie slices share the circle by value; one slice is the whole circle and a zero slice has no wedge", () => {
  const slices = pieSlices([{ label: "a", value: 3 }, { label: "b", value: 1 }, { label: "c", value: 0 }]);
  assert.deepEqual(slices.map((s) => s.share), [0.75, 0.25, 0]);
  assert.equal(slices[2].path, "");
  assert.ok(slices[0].path.includes(" 1 1 "), "the big slice takes the long way round");
  assert.ok(slices[1].path.includes(" 0 1 "), "the small one the short way");
  assert.ok(pieSlices([{ label: "only", value: 7 }])[0].path.startsWith("M 80 0 A 80 80 0 1 1"));
  assert.deepEqual(pieSlices([]), []);
});

test("grey has the same five steps as the colour and neither runs out", () => {
  assert.notEqual(sliceColor(0, false), sliceColor(0, true));
  assert.equal(sliceColor(5, false), sliceColor(0, false));
  assert.match(sliceColor(2, true), /^#[0-9a-f]{6}$/);
});

test("the pivot query names the relation, which end the source is, and what the source selected", () => {
  const source = { type: "order", view: null, filters: [{ field: "状态码", op: "eq", value: "2" }], rows: null, pivot: null };
  assert.deepEqual(pivotQuery(source, { id: "order_customer", side: "from", other: "customer" }),
    { type: "customer", view: null, filters: [], rows: null, pivot: { relation: "order_customer", side: "from", source } });
});

test("a query survives the address and a broken one is no query", () => {
  const q = { type: "customer", view: null, filters: [], rows: null, pivot: { relation: "r", side: "to", source: { type: "order", view: "有效订单", filters: [], rows: [3], pivot: null } } };
  assert.deepEqual(queryFromParam(queryToParam(q)), q);
  assert.equal(queryFromParam("{not json"), null);
  assert.equal(queryFromParam('{"x":1}'), null);
  assert.equal(queryFromParam(""), null);
  assert.equal(queryFromParam(null), null);
});

test("what a chart did not draw is named with its rows and its measure, and the rows a relation could not place say where they were not found", () => {
  const capped = { chart: { kind: "bar" }, measure: "金额", groups_hidden: 7, rows_hidden: 20, hidden_groups: [{ label: "KH004", rows: 2, value: 15600 }, { label: "KH023", rows: 3, value: 34020 }] };
  assert.deepEqual(leftOutLines(capped), ["没画出来的：KH004（2 行，15,600）、KH023（3 行，34,020），等 7 组共 20 行"]);
  const counted = { chart: { kind: "bar" }, measure: null, groups_hidden: 1, rows_hidden: 2, hidden_groups: [{ label: "KH099", rows: 2, value: 2 }] };
  assert.deepEqual(leftOutLines(counted), ["没画出来的：KH099（2 行）"]);
  const lost = { chart: { kind: "bar" }, measure: "金额", groups_hidden: 0, unplaced_rows: 2, unplaced_groups: 1, unplaced_through: "客户", unplaced: [{ label: "KH099", rows: 2, value: 12670 }] };
  assert.deepEqual(leftOutLines(lost), ["没画出来的：KH099（2 行，12,670），在「客户」里找不到对应的行"]);
  assert.deepEqual(leftOutLines({ chart: { kind: "bar" }, groups_hidden: 0, unplaced_rows: 0 }), []);
});
