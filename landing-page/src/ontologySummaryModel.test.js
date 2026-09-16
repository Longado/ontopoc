import assert from "node:assert/strict";
import test from "node:test";

import { summaryMarkdown } from "./ontologySummaryModel.js";

const run = (extra = {}) => ({
  file: { name: "客户订单.xlsx", kind: "table" }, purpose: "哪些客户经常延期交货？",
  started_at: "2026-09-16T02:00:00+00:00",
  sources: [{ name: "客户", rows: 26, fields: 4 }, { name: "订单", rows: 35, fields: 6 }],
  ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }],
    relations: [{ key: "r1", from: "order", to: "customer", label: "属于" }], data_gaps: ["缺少实际交货日期"], ignored_fields: [], attempts: [{ errors: [] }], status: "auto_built_verified" },
  evaluation: { data_fit: { checks: [{ key: "fields_accounted", passed: true }, { key: "identity_consistent", passed: false }],
    identity_conflicts: [{ type: "customer", identity: "C010", field: "客户名称", values: ["甲", "乙"] }], identity_spellings: [], suspected_duplicates: [],
    missing_across_sources: [{ type: "customer", source: "客户", count: 1, examples: ["C099"] }], relations: [], orphans: [], source_groups: [["客户", "订单"]], fields: {} } },
  ...extra,
});

test("the summary is for the people in the room: what was read, what it says, what to check", () => {
  const md = summaryMarkdown(run({ confirmation: { confirmed_at: "2026-09-16T03:00:00+00:00", confirmed_by: "信息部 王工", decisions: { types: { customer: { verdict: "ok" } }, relations: {}, added: [] } } }));
  assert.match(md, /^# 客户订单\.xlsx 本体摸底纪要/);
  assert.match(md, /哪些客户经常延期交货？/);
  assert.match(md, /客户（26 行 4 列）/);
  assert.match(md, /订单 属于 客户/);
  assert.match(md, /C010/);
  assert.match(md, /C099/);
  assert.match(md, /缺少实际交货日期/);
  assert.match(md, /信息部 王工/);
  assert.doesNotMatch(md, /customer|auto_built_verified/);   // no internal names in front of a client
});

test("without a confirmation it says plainly that nobody has checked it yet", () => {
  const md = summaryMarkdown(run());
  assert.match(md, /还没有人逐项确认/);
  assert.doesNotMatch(md, /确认人/);
});

test("fixed questions come with the meaning agreed on and whether they still hold", () => {
  const md = summaryMarkdown(run({ evaluation: { ...run().evaluation,
    acceptance: { total: 1, answered: 1, items: [{ question: "哪些客户经常延期交货？", note: "按订单号计数", status: "answered", changed: false,
      answer: { groups: [["甲", 2, 2], ["乙", 1, 6]], total_groups: 2, share: { field: "交货状态", equals: "延期交货" } }, path: "订单 → 客户" }] } } }));
  assert.match(md, /验收问题/);
  assert.match(md, /按订单号计数/);
  assert.match(md, /甲：2 \/ 2（100%）/);
  assert.match(md, /和上次一致/);
});
