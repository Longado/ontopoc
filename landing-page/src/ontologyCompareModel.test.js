import assert from "node:assert/strict";
import test from "node:test";

import { referenceCounts, stabilityLines } from "./ontologyStudioModel.js";

const diff = (onlyRefTypes, onlyOurTypes, onlyRefRels = [], onlyOurRels = []) => ({
  types: { matched: [["客户", "客户"]], only_reference: onlyRefTypes, only_ours: onlyOurTypes },
  relations: { matched: [], only_reference: onlyRefRels, only_ours: onlyOurRels },
  counts: { types: { reference: 5, ours: 4, matched: 4 }, relations: { reference: 4, ours: 3, matched: 3 } },
});

test("a rerun says what was added or dropped since the previous run", () => {
  assert.deepEqual(stabilityLines(diff(["售后工程师"], [], ["售后工单 — 售后工程师"], [])),
    ["对象少了：售后工程师", "关系少了：售后工单 — 售后工程师"]);
  assert.deepEqual(stabilityLines(diff([], ["发票"])), ["对象多了：发票"]);
  assert.deepEqual(stabilityLines(diff([], [])), []);
});

test("a reference comparison reads as hits over the reference and extras", () => {
  assert.equal(referenceCounts(diff([], [])), "对象命中 4 / 5，多出 0 个；关系命中 3 / 4，多出 0 条");
});
