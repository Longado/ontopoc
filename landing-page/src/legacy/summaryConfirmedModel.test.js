import assert from "node:assert/strict";
import test from "node:test";

import { summaryMarkdown } from "./ontologySummaryModel.js";

const run = (confirmation) => ({
  file: { name: "客户订单.xlsx", kind: "table" }, purpose: "哪些客户经常延期交货？", started_at: "2026-09-16T02:00:00+00:00",
  sources: [{ name: "订单", rows: 35, fields: 6 }],
  ontology: { object_types: [{ key: "customer", label: "客户" }, { key: "order", label: "订单" }, { key: "region", label: "大区" }],
    relations: [{ key: "r1", from: "order", to: "customer", label: "属于" }, { key: "r2", from: "customer", to: "region", label: "位于" }],
    data_gaps: [], ignored_fields: [], attempts: [{ errors: [] }], status: "auto_built_verified" },
  evaluation: { data_fit: { checks: [{ key: "fields_accounted", passed: true }], identity_conflicts: [], missing_across_sources: [] },
    acceptance: { items: [{ question: "每个客户几张订单？", status: "answered", changed: null, answer: { total: 35 } }] } },
  ...(confirmation ? { confirmation } : {}),
});

const section = (md, heading) => md.split(`## ${heading}`)[1].split("\n## ")[0];

test("after confirmation the body lists what was judged right, under the names the person gave", () => {
  const body = section(summaryMarkdown(run({ confirmed_at: "2026-09-16T03:00:00+00:00", confirmed_by: "王工",
    decisions: { types: { customer: { verdict: "ok", label: "客户主体" }, order: { verdict: "ok" }, region: { verdict: "wrong" } },
      relations: { r1: { verdict: "ok" }, r2: { verdict: "wrong" } }, added: ["售后工程师"] } })), "业务里有哪些东西");
  assert.match(body, /- 客户主体\n/);
  assert.match(body, /- 订单 属于 客户主体/);
  assert.doesNotMatch(body, /- 大区\n|- 客户主体 位于/);       // judged wrong: not stated as part of the business
  assert.match(body, /确认时判错、没有列进来：大区；客户主体 位于 大区/);
  assert.match(body, /确认时补上的：售后工程师/);
});

test("what the person has not judged yet is marked as the model's, not mixed in with the confirmed", () => {
  const body = section(summaryMarkdown(run({ confirmed_at: "2026-09-16T03:00:00+00:00",
    decisions: { types: { customer: { verdict: "ok" } }, relations: {}, added: [] } })), "业务里有哪些东西");
  assert.match(body, /还没判的，是模型提出的：订单、大区；订单 属于 客户；客户 位于 大区/);
  assert.doesNotMatch(body, /- 订单\n/);
});

test("before anyone confirms, the section says up front that all of it is the model's proposal", () => {
  const body = section(summaryMarkdown(run(null)), "业务里有哪些东西");
  assert.match(body, /以下都是模型提出的，还没有人确认/);
  assert.match(body, /- 大区\n/);
});

test("the data check and the fixed questions say their numbers were worked out by code, not by the model", () => {
  const md = summaryMarkdown(run(null));
  assert.match(section(md, "数据体检"), /由代码在上传的数据上逐行算，不经过模型/);
  assert.match(section(md, "验收问题"), /答案由代码在上传的数据上算，不经过模型/);
});
