import assert from "node:assert/strict";
import test from "node:test";

import { objectsNav, qaNav } from "./workspaceModel.js";

const run = (extra = {}) => ({
  ontology: { object_types: [{ key: "a" }, { key: "b" }], relations: [{ key: "r" }], data_gaps: ["缺交货日期"], ignored_fields: [] },
  evaluation: { stability: { runs: 3 }, questions: { items: [{ status: "answered" }, { status: "query_limit" }] }, asked: [{ items: [{ status: "answered" }] }] },
  ...extra,
});
const decisions = { types: { a: { verdict: "ok" } }, relations: {}, added: [] };

test("本体管理 splits into places, each with the number that tells whether to go there", () => {
  assert.deepEqual(objectsNav(run(), decisions), [
    ["objects", "对象", "2"], ["confirm", "逐项确认", "1 / 3"], ["stability", "稳定性", "3 次"], ["build", "建模记录", "缺口 1"]]);
  const withPrevious = objectsNav(run({ previous: { diff: {} } }), decisions).map(([key]) => key);
  assert.deepEqual(withPrevious, ["objects", "confirm", "stability", "history", "build"]);
  const bare = objectsNav(run({ evaluation: {} }), decisions).map(([key]) => key);
  assert.deepEqual(bare, ["objects", "confirm", "build"]);   // no extra builds, no previous run: no empty places
});

test("智能问答 splits into asking, the fixed questions and the model's questions", () => {
  assert.deepEqual(qaNav(run()), [["ask", "提问", "1"], ["acceptance", "验收问题", "0"], ["model", "模型出的题", "1 / 2"]]);
  assert.deepEqual(qaNav(run({ evaluation: { acceptance: { items: [{}, {}] } } })).map((i) => i[2]), ["0", "2", "—"]);
});
