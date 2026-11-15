import assert from "node:assert/strict";
import test from "node:test";

import { askSuggestions, askedNow, bridgeLines, layoutTables, latestAsked, objectCountLine, repeatLines, repeatMark, tableChecks } from "./dataLayoutModel.js";

const bridge = { from_source: "tw_company_directors", from_field: "統一編號", to_source: "tw_company_registry", to_field: "統一編號", rows: 1573, linked_rows: 1573 };

function run(extra = {}) {
  return {
    sources: [{ name: "tw_company_registry", rows: 150, fields: 18 }, { name: "tw_company_directors", rows: 1573, fields: 5, skipped_rows: ["董監事名單"] }],
    evaluation: { data_fit: { source_groups: [["tw_company_registry"], ["tw_company_directors"]], bridges: [bridge] },
      handover: { sources: [
        { name: "tw_company_registry", rows: 150, skipped_rows: [], fields: [{ path: "統一編號", type: "VARCHAR", length: 8, empty: 0 }] },
        { name: "tw_company_directors", rows: 1573, skipped_rows: ["董監事名單"], fields: [{ path: "持有股份數", type: "INTEGER", length: 10, empty: 12 }] }] } },
    ...extra,
  };
}

test("a bridge is said with both tables, both columns and how many rows connect", () => {
  assert.deepEqual(bridgeLines(run()), ["tw_company_directors 的「統一編號」有 1573 / 1573 行，能在 tw_company_registry 的「統一編號」里找到"]);
  const connected = run();
  connected.evaluation.data_fit = { source_groups: [["a", "b"]] };   // an older run, or tables already joined
  assert.deepEqual(bridgeLines(connected), []);
});

test("each table is laid out with its size, skipped title lines and column shapes", () => {
  const [first, second] = layoutTables(run());
  assert.deepEqual([first.name, first.rows, first.fields.length, first.skipped], ["tw_company_registry", 150, 1, []]);
  assert.deepEqual(second.skipped, ["董監事名單"]);
  assert.deepEqual(second.fields[0], { path: "持有股份數", type: "INTEGER", length: 10, empty: 12 });
  assert.equal(second.group, 1);   // which connected group it sits in, so unconnected tables can be shown apart
});

test("a run saved before columns were profiled still lists its tables, with no column detail", () => {
  const old = run();
  delete old.evaluation.handover;
  const tables = layoutTables(old);
  assert.deepEqual(tables.map((t) => [t.name, t.rows, t.fields]), [["tw_company_registry", 150, null], ["tw_company_directors", 1573, null]]);
  assert.deepEqual(tables[1].skipped, ["董監事名單"]);
});

const item = (question, status = "answered") => ({ question, status, query: { start: "order", via: [] }, answer: { total: 1 } });

test("suggestions are this run's own answered questions, at most three, not generic examples", () => {
  const withQs = run();
  withQs.evaluation.questions = { items: [item("甲"), item("乙", "query_limit"), item("丙"), item("丁"), item("戊")] };
  assert.deepEqual(askSuggestions(withQs).map((i) => i.question), ["甲", "丙", "丁"]);
  assert.deepEqual(askSuggestions(run()), []);
});

test("the answer to show under the box is the last question asked", () => {
  const asked = run();
  asked.evaluation.asked = [{ items: [item("第一问")] }, { items: [item("第二问")] }];
  assert.equal(latestAsked(asked).question, "第二问");
  asked.evaluation.asked.push({ items: [], error: "模型请求失败：timed out" });
  assert.deepEqual(latestAsked(asked), { error: "模型请求失败：timed out" });
  assert.equal(latestAsked(run()), null);
});

test("the questions asked are listed once each, as they stand after the last time they were asked or worked out", () => {
  const asked = (rounds) => askedNow({ evaluation: { asked: rounds } }).map((i) => [i.question, i.total]);
  assert.deepEqual(asked([{ items: [{ question: "甲", total: 1 }, { question: "乙", total: 2 }] }, { items: [{ question: "甲", total: 3 }] }, { error: "模型请求失败", items: [] }]), [["甲", 3], ["乙", 2]]);
  assert.deepEqual(askedNow({ evaluation: {} }), []);
});

const checked = () => ({
  ...run(),
  ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "engineer", label: "工程师" }] },
  data_checks: {
    tables: [{ dataset: "tw_company_registry", status: "ok", rows_in: 153, rows_stored: 150, dropped: { blank: 2, title: 1 } },
      { dataset: "tw_company_directors", status: "error", rows_in: 1573, rows_stored: null, dropped: {}, error: "tw_company_directors：读到 1573 行，只存入 1500 行，已取消导入" }],
    keys: [
      { object_type: "customer", dataset: "tw_company_registry", key_columns: ["統一編號"], check_type: "key_unique", status: "failed", violations: 1, null_key_rows: 0, samples: [{ key: { 統一編號: "KH012" }, count: 2 }] },
      { object_type: "engineer", dataset: "tw_company_registry", key_columns: ["負責人"], check_type: "key_distinct", status: "passed", distinct: 4, null_key_rows: 2, samples: [] },
      { object_type: "customer", dataset: "tw_company_registry", key_columns: ["名稱"], check_type: "key_unique", status: "passed", violations: 0, null_key_rows: 0, samples: [] }],
  },
});

test("a table says rows in the file, rows stored, what was dropped and why, and each drafted identity's result", () => {
  const c = tableChecks(checked(), "tw_company_registry");
  assert.deepEqual([c.rowsIn, c.rowsStored, c.droppedCount, c.dropped], [153, 150, 3, "空行 2、标题行 1"]);
  assert.deepEqual(c.keys.map((k) => [k.type, k.columns, k.failed, k.text]), [
    ["客户", "統一編號", true, "重复 1 行，如 KH012（2 行）"],
    ["工程师", "負責人", false, "4 个不同取值，2 行没有值"],
    ["客户", "名稱", false, "没有重复，没有空值"]]);
});

test("a table that could not be stored carries the error naming the table and the rows", () => {
  const c = tableChecks(checked(), "tw_company_directors");
  assert.match(c.error, /tw_company_directors.*1573.*1500/);
  assert.deepEqual(layoutTables(checked()).map((t) => t.checks.error === null), [true, false]);
});

test("a run saved before the checks existed has no check lines", () => {
  assert.equal(tableChecks(run(), "tw_company_registry"), null);
  assert.equal(layoutTables(run())[0].checks, null);
});

test("repeated identities are said as rows, identities and which ones repeat, with the rule once one is chosen", () => {
  const rows = [{ source: "客户", rows: 31, identities: 30, repeated: 1, examples: ["KH012"], rule: null }, { source: "订单", rows: 160, identities: 160, repeated: 0, examples: [] }];
  assert.deepEqual(repeatLines(rows), ["客户表：31 行，30 个不同编号，1 行是重复编号（KH012）。还没定怎么算，重复的每一行都列在下面"]);
  const ruled = (rule) => repeatLines([{ ...rows[0], rule }])[0].split("。")[1];
  assert.equal(ruled({ rule: "keep_both", confirmed_by: "王工" }), "已确认（王工）：每一行都留");
  assert.equal(ruled({ rule: "data_error", confirmed_by: null }), "已确认：当作数据错误，等客户改数据");
  assert.equal(ruled({ rule: "keep_latest", column: "更新日期", confirmed_by: "王工" }), "已确认（王工）：只留「更新日期」最新的一行");
  assert.equal(ruled({ rule: "keep_latest", column: "更新日期", confirmed_by: "王工", ties: 2, blank: 1 }),
    "已确认（王工）：只留「更新日期」最新的一行；2 个编号的几行在这一列上并列，取了文件里靠后的一行；1 个编号有的行这一列是空的，按最旧算");
  assert.deepEqual(repeatLines([{ source: "订单", rows: 3, identities: 3, repeated: 0 }]), []);
  assert.deepEqual(repeatLines(undefined), []);
});

test("the count line says where each number comes from", () => {
  const sources = [{ source: "客户", rows: 31, identities: 30, repeated: 1, examples: ["KH012"], rule: null }];
  assert.equal(objectCountLine({ objects: 31, total: 32, mentioned_only: { count: 1, examples: ["KH099"] }, identity_repeats: sources }),
    "共 31 个对象：30 个在客户表里有行，1 个只在别的表里出现（KH099）；列出 32 行，重复的编号各占一行");
  assert.equal(objectCountLine({ objects: 30, total: 30, mentioned_only: { count: 0, examples: [] }, identity_repeats: sources }), "共 30 个对象");
  assert.equal(objectCountLine({ objects: 30, total: 31, mentioned_only: { count: 0, examples: [] }, identity_repeats: sources }), "共 30 个对象；列出 31 行，重复的编号各占一行");
});

test("a row of a repeated key says what is decided about it", () => {
  assert.equal(repeatMark(null), "");
  assert.equal(repeatMark({ repeat: "pending", rows: 2 }), "重复编号（共 2 行），还没定怎么算");
  assert.equal(repeatMark({ repeat: "keep_both", rows: 2 }), "重复编号（共 2 行），每一行都留");
  assert.equal(repeatMark({ repeat: "data_error", rows: 2 }), "重复编号（共 2 行），当作数据错误");
  assert.equal(repeatMark({ repeat: "keep_latest", rows: 3, column: "更新日期" }), "重复编号（共 3 行），按「更新日期」只留最新的一行");
  assert.equal(repeatMark({ repeat: "keep_latest", rows: 2, column: "更新日期", tie: true }), "重复编号（共 2 行），按「更新日期」只留最新的一行（这一列上并列，取了文件里靠后的一行）");
  assert.equal(repeatMark({ repeat: "keep_latest", rows: 2, column: "更新日期", blank: true }), "重复编号（共 2 行），按「更新日期」只留最新的一行（有一行这一列是空的，按最旧算）");
});

test("a relation's check reads as lines, the problems marked", async () => {
  const { relationLines } = await import("./dataLayoutModel.js");
  const side = { end: "to", object: "customer", other: "order", columns: ["客户编号"], lookup: "客户", rows: 160, empty: 0, matched: 157, unmatched: 3, unmatched_keys: 1,
    samples: [{ key: "KH099", rows: 3 }], if_trimmed: 0, fanout: { keys: 1, source_rows: 2, extra_rows: 2, samples: [{ key: "KH012", rows: 2 }] } };
  const run = { ontology: { object_types: [{ key: "order", label: "订单" }, { key: "customer", label: "客户" }] },
    data_checks: { relations: [{ key: "oc", from: "order", to: "customer", source: "订单", sides: [side], cardinality: { declared: "one_to_one", holds: false, most_from: 1, most_to: 9 } }] } };
  const [found] = relationLines(run, (r) => r.source === "订单");
  assert.deepEqual(found.lines.map((l) => [l.text, l.warn]), [
    ["「客户编号」在「客户」表里：157 / 160 行找到对应", false],
    ["3 行找不到（KH099）", true],
    ["「客户」表里 1 个编号重复（KH012），2 行连过去会多出 2 行", true],
    ["声明的基数「一对一」不成立：一个订单最多连 1 个客户，一个客户最多连 9 个订单", true]]);
  const rules = (rule) => ({ "customer.客户": { rule } });
  const fan = (rule) => relationLines(run, () => true, rules(rule))[0].lines.find((l) => /编号重复/.test(l.text));
  assert.deepEqual([fan("keep_latest").text, fan("keep_latest").warn], ["「客户」表里 1 个编号重复（KH012），已按你的选择只留最新的一行，连过去不再多出行", false]);   // the extra rows are gone once the latest row is kept
  assert.match(fan("keep_both").text, /你选了每一行都留，2 行连过去会多出 2 行/);
  assert.equal(fan("data_error").warn, true);
  assert.deepEqual(relationLines(run, (r) => r.source === "客户"), []);
  assert.equal(relationLines({ ontology: run.ontology, data_checks: {} }, () => true), null);
});

test("a column whose name does not say what its rows give is marked with the two words", async () => {
  const { nameNotes } = await import("./dataLayoutModel.js");
  const item = (actual_text) => ({ kind: "name_vs_calc", column: { source: "交付统计", column: "交付天数P50", says_text: "中位数", actual_text } });
  assert.deepEqual(nameNotes([item("平均数"), { kind: "code_meaning" }]), { "交付统计.交付天数P50": "名字说是中位数，算出来是平均数" });
  assert.equal(nameNotes([item(null)])["交付统计.交付天数P50"], "名字说是中位数，重算对不上");
  const p90 = { kind: "name_vs_calc", column: { source: "交付统计", column: "交付天数P90", says_text: "第 90 百分位", actual_text: null, how: "第 90 百分位按插值算；写成“最近秩”的也算对" } };
  assert.equal(nameNotes([p90])["交付统计.交付天数P90"], "名字说是第 90 百分位，重算对不上（第 90 百分位按插值算；写成“最近秩”的也算对）");
  assert.deepEqual(nameNotes(undefined), {});
  const column = { source: "订单统计", column: "金额合计", says_text: "合计" };
  assert.equal(nameNotes([{ kind: "name_by_view", column: { ...column, view: "有效订单" } }])["订单统计.金额合计"], "按「有效订单」算的合计");
  assert.equal(nameNotes([{ kind: "name_values", column }])["订单统计.金额合计"], "名字说是合计，有值不是数字，没和重算比");
  assert.equal(nameNotes([{ kind: "name_source", column: { ...column, candidates: ["订单", "订单二"] } }])["订单统计.金额合计"], "名字说是合计，2 张表都能重算，还没定用哪一张");
});
