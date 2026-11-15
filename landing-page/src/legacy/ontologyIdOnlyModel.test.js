import assert from "node:assert/strict";
import test from "node:test";

import { summaryMarkdown } from "./ontologySummaryModel.js";

const run = (idOnly) => ({
  file: { name: "orders.xlsx", kind: "table" }, purpose: "看清订单", started_at: "2026-09-18T02:00:00+00:00",
  sources: [{ name: "订单", rows: 830, fields: 6 }],
  ontology: { object_types: [{ key: "order", label: "订单" }, { key: "employee", label: "员工" }], relations: [],
    data_gaps: [], ignored_fields: [], attempts: [{ errors: [] }], status: "auto_built_verified" },
  evaluation: { data_fit: { checks: [], identity_conflicts: [], identity_spellings: [], suspected_duplicates: [],
    missing_across_sources: [], relations: [], orphans: [], source_groups: [["订单"]], fields: {}, id_only: idOnly } },
});

test("the handover page says which objects are only an id column, so nobody presents them as real things", () => {
  const md = summaryMarkdown(run([{ type: "employee", source: "订单", field: "员工号", count: 9 }]));
  assert.match(md, /只有编号、没有描述它的表/);
  assert.match(md, /员工：9 个编号，来自“订单”的“员工号”，这份数据里没有一张表在描述它/);
});

test("nothing is said when every object has a table behind it", () => {
  assert.doesNotMatch(summaryMarkdown(run([])), /只有编号/);
  assert.doesNotMatch(summaryMarkdown(run(undefined)), /只有编号/);   // results saved before this check existed
});
