import assert from "node:assert/strict";
import test from "node:test";

import { fileProblem, previousLine } from "./ontologyStudioModel.js";
import { overviewTiles } from "./ontologyGraphModel.js";

process.env.TZ = "Asia/Shanghai";

test("files the service would refuse are caught before upload", () => {
  assert.match(fileProblem({ name: "a.zip", size: 10 }), /不支持 \.zip/);
  assert.match(fileProblem({ name: "空.xlsx", size: 0 }), /是空的/);
  assert.match(fileProblem({ name: "大.csv", size: 11 * 1024 * 1024 }), /10 MB/);
  assert.equal(fileProblem({ name: "订单.XLSX", size: 2048 }), "");
  assert.equal(fileProblem({ name: "流程.md", size: 10 }), "");
});

test("the compared run is named by local time and what it was built for", () => {
  const line = previousLine({ started_at: "2026-09-15T01:55:47+00:00", purpose: "哪些客户的售后问题最多？", counts: { types: 4, relations: 3 } });
  assert.equal(line, "上一次运行：09-15 09:55，建模目的“哪些客户的售后问题最多？”，4 个对象、3 条关系");
  assert.equal(previousLine({ started_at: "2026-09-15T01:55:47+00:00" }), "上一次运行：09-15 09:55");
});

const run = (evaluation, extra = {}) => ({
  file: { kind: "table" }, ontology: { object_types: [{}, {}], relations: [{}] },
  evaluation: { data_fit: { checks: [{ passed: true }, { passed: false }, { passed: false }] }, ...evaluation }, ...extra,
});

test("each tile says in words whether its number is good", () => {
  const hints = (r) => Object.fromEntries(overviewTiles(r).map((t) => [t.key, t.hint]));
  const partial = hints(run({ questions: { answered: 5, total: 6 }, reference: { diff: { counts: { types: { reference: 5, matched: 4 } } } } },
    { previous: { diff: { types: { only_reference: ["x"], only_ours: [] }, relations: { only_reference: [], only_ours: [] } } } }));
  assert.equal(partial.fit, "2 项没通过，点开看是哪些");
  assert.equal(partial.qa, "1 题答不了，点开看原因");
  assert.equal(partial.ref, "参考里有 1 个对象没对上");
  assert.equal(partial.stability, "模型每次搭的会有出入");
  const fresh = hints(run({ data_fit: { checks: [{ passed: true }] } }));
  assert.equal(fresh.fit, "全部通过");
  assert.equal(fresh.qa, "上传自己的文件后可以提问");
  assert.equal(fresh.ref, "逐项确认本体，或上传参考本体");
  assert.equal(fresh.stability, "再上传同一文件可看差别");
});
