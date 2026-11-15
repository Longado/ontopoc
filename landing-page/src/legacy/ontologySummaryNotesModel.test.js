import assert from "node:assert/strict";
import test from "node:test";

import { summaryMarkdown } from "./ontologySummaryModel.js";

// The shape the CMS hospital run produced: 17 groups with a figure, 14 more where nothing could be read, 311 values skipped.
const groups = Array.from({ length: 17 }, (_, i) => [`第 ${i + 1} 类医院`, 17 - i, 5]);
const run = {
  file: { name: "hospitals.csv", kind: "table" }, purpose: "哪类医院差于全国", started_at: "2026-09-18T00:16:00+00:00",
  sources: [{ name: "医院", rows: 1258, fields: 38 }],
  ontology: { object_types: [{ key: "hospital", label: "医院" }], relations: [], data_gaps: [], ignored_fields: [], attempts: [{ errors: [] }], status: "auto_built_verified" },
  evaluation: { data_fit: { checks: [], identity_conflicts: [], identity_spellings: [], suspected_duplicates: [], missing_across_sources: [], relations: [], orphans: [], source_groups: [["医院"]], fields: {} },
    acceptance: { total: 1, answered: 1, items: [{ question: "哪类医院差于全国的指标最多？", note: "", status: "answered", changed: null, path: "医院：按类型分组",
      answer: { groups, total_groups: 17, without_value: 0, unread_groups: { count: 14, examples: ["儿童医院", "精神病院"] },
        measure: { field: "差于全国的指标数", op: "average", value: 0.098, counted: 947, skipped: 311 } } }] } },
};

test("the handover page cuts the list of groups short, never the lines that say what the figures leave out", () => {
  const md = summaryMarkdown(run);
  assert.match(md, /- 第 10 类医院：8（5 个值）/);
  assert.doesNotMatch(md, /第 11 类医院/);
  assert.match(md, /- 另有 7 组，完整结果见“本体和评测”文件/);   // seven groups, not seven plus the notes
  assert.match(md, /另有 14 组一个能读成数字的值都没有，不算作 0/);
  assert.match(md, /读到 947 个值，311 个不是数字或为空，没算进去/);
});
