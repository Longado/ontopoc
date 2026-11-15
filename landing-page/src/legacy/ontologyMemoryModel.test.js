import assert from "node:assert/strict";
import test from "node:test";

import { memoryNote, saveResult } from "./ontologyStudioModel.js";

const run = (extra = {}) => ({ saved_as: "x.json", file: { name: "订单.xlsx" }, ontology: { object_types: [], relations: [] }, evaluation: {}, ...extra });

test("a file with nothing saved against it says so, and says how the system tells files apart", () => {
  assert.match(memoryNote(run()), /这份文件还没有保存过确认或验收问题/);
  assert.match(memoryNote(run()), /按文件内容认/);
  assert.equal(memoryNote(run({ confirmation: { confirmed_at: "2026-09-16T00:00:00+00:00" } })), "");
  assert.equal(memoryNote(run({ evaluation: { reference: { confirmed: true, suggested: {} } } })), "");
  assert.equal(memoryNote({ ...run(), saved_as: undefined }), "");   // the bundled example: nothing to remember anyway
});

test("a result too big for the browser is reported, not swallowed", () => {
  const kept = {};
  const storage = { setItem: (k, v) => { kept[k] = v; } };
  assert.equal(saveResult(storage, run()), "");
  assert.equal(Object.keys(kept).length, 1);
  const full = { setItem: () => { throw new DOMException("quota", "QuotaExceededError"); } };
  assert.match(saveResult(full, run()), /没能存进浏览器/);
  assert.match(saveResult(full, run()), /下载/);
  assert.equal(saveResult(null, run()), "");   // no storage at all (private window): not worth a warning
});
