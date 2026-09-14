import assert from "node:assert/strict";
import test from "node:test";

import { ACCEPT, CHECK_LABELS, attemptSummary, checkSummary, typeSources, validateRun } from "./ontologyStudioModel.js";

const run = () => ({
  schema: "company_ontology_run.v1", file: { name: "demo.xlsx", kind: "table", sha256: "a".repeat(64) },
  sources: [{ name: "客户", rows: 31, fields: 5 }],
  ontology: {
    status: "auto_built_verified", model: "deepseek-flash", prompt_version: "company_ontology_modeler.v1",
    attempts: [{ errors: [{ code: "relation_source_mismatch", message: "relation order_customer: customer is not populated from '订单'" }] }, { errors: [] }],
    object_types: [{ key: "customer", label: "客户", populated_from: [{ source: "客户", identity: { customer_id: "客户编号" } }, { source: "订单", identity: { customer_id: "客户编号" } }], attributes: [] }],
    relations: [], data_gaps: [], ignored_fields: [],
  },
  evaluation: { data_fit: { checks: [{ key: "fields_accounted", passed: true }, { key: "identity_consistent", passed: false }] } },
});

test("only a company ontology run is shown", () => {
  assert.equal(validateRun(run()).schema, "company_ontology_run.v1");
  assert.throws(() => validateRun({ schema: "other" }), /结果格式/);
  assert.throws(() => validateRun({ ...run(), ontology: null }), /结果格式/);
});

test("the upload accepts tables and says which", () => {
  assert.equal(ACCEPT, ".csv,.xlsx");
});

test("checks read as plain sentences with a pass count", () => {
  assert.equal(CHECK_LABELS.references_resolve, "引用的对象都能在它所属的表里找到");
  assert.deepEqual(checkSummary(run().evaluation.data_fit), { passed: 1, total: 2 });
  assert.equal(checkSummary(null), null);
});

test("attempts say how many times code sent the model back and why", () => {
  assert.deepEqual(attemptSummary(run().ontology), { attempts: 2, passed: true, rejected: [["relation_source_mismatch", 1]] });
});

test("a type lists where it comes from and by which fields", () => {
  assert.equal(typeSources(run().ontology.object_types[0]), "客户（客户编号）、订单（客户编号）");
});
