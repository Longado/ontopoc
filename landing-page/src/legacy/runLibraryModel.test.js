import assert from "node:assert/strict";
import test from "node:test";

import { folderLabel, groupRuns, runLabel } from "./runLibraryModel.js";

const run = (over) => ({ saved_as: "x.json", file: "orders.csv", purpose: "看清订单", started_at: "2026-09-18T04:49:03+00:00",
  status: "auto_built_verified", confirmed: false, ...over });

test("runs of the same file sit in one folder, and the folder with the latest run comes first", () => {
  const runs = [run({ saved_as: "3.json", file: "b.csv" }), run({ saved_as: "2.json", file: "a.csv" }), run({ saved_as: "1.json", file: "b.csv" })];
  const folders = groupRuns(runs);
  assert.deepEqual(folders.map((f) => f.file), ["b.csv", "a.csv"]);
  assert.deepEqual(folders[0].runs.map((r) => r.saved_as), ["3.json", "1.json"]);
});

test("a batch of files is named by its first file and how many there were", () => {
  assert.equal(folderLabel("bart_routes.csv、bart_trips.csv、bart_stops.csv"), "bart_routes.csv 等 3 份");
  assert.equal(folderLabel("orders.csv"), "orders.csv");
  assert.equal(folderLabel(null), "没有文件名");
});

test("a run is named by what it was for, and says when it did not get through", () => {
  assert.equal(runLabel(run()), "看清订单");
  assert.equal(runLabel(run({ purpose: "" })), "没写建模目的");
  assert.equal(runLabel(run({ status: "needs_review" })), "看清订单（没通过核验）");
  assert.equal(runLabel(run({ confirmed: true })), "看清订单 ✓");
});
