import assert from "node:assert/strict";
import test from "node:test";

import { decisionsOf, referenceDownload } from "./ontologyConfirmModel.js";

test("a rerun of a confirmed file starts from the suggested decisions", () => {
  const suggested = { types: { order: { verdict: "ok" } }, relations: {}, added: ["发票"] };
  assert.deepEqual(decisionsOf({ evaluation: { reference: { confirmed: true, suggested } } }), suggested);
});

test("the downloaded reference says who confirmed it, for which file, and which identities the data check disproved", () => {
  const run = { file: { name: "retail.csv", sha256: "ab" }, ontology: { object_types: [{ key: "line", label: "发票行" }, { key: "product", label: "商品" }] },
    evaluation: { data_fit: { identity_conflicts: [{ type: "line", identity: "1" }, { type: "line", identity: "2" }, { type: "product", identity: "9" }] } },
    confirmation: { confirmed_at: "2026-09-15T12:00:00+00:00", confirmed_by: "王工", reference: { object_types: [{ key: "line", label: "发票行" }], relations: [] } } };
  const out = referenceDownload(run);
  assert.deepEqual(out.confirmed, { at: "2026-09-15T12:00:00+00:00", by: "王工", file: "retail.csv", sha256: "ab" });
  assert.deepEqual(out.object_types, run.confirmation.reference.object_types);
  assert.deepEqual(out.data_check, [{ type: "line", label: "发票行", note: "识别字段在数据里不唯一：2 个编号在不同行里信息不一致" }]);
});
