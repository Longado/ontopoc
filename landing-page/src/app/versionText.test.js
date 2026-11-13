import assert from "node:assert/strict";
import test from "node:test";

import { keyText, percentText, typeLabel } from "./format.js";
import { modeLabel, noChangeText, timeline, versionChangeText } from "./versionText.js";

test("each version says what it did in its own mode", () => {
  assert.equal(versionChangeText({ mode: "new", rows: 160 }), "160 行");
  assert.equal(versionChangeText({ mode: "update_by_key", changed: 2, added: 3, unchanged: 1, rows: 163 }), "改 2，增 3，未变 1");
  assert.equal(versionChangeText({ mode: "overwrite", replaced_rows: 160, rows: 2 }), "原 160 行，现 2 行");
  assert.equal(versionChangeText({ mode: "upload", rows: 31 }), "31 行");
  assert.deepEqual(["new", "update_by_key", "overwrite", "upload", "x"].map(modeLabel), ["新建", "按主键更新", "覆盖", "导入", "导入"]);
});

test("an update that changed nothing is one plain sentence", () => {
  assert.equal(noChangeText({ key_columns: ["订单号"] }), "按主键更新（订单号）：没有变化，没有新版本");
});

test("versions and skipped updates share one list, newest first", () => {
  const versions = [{ version: 2, at: "2026-11-13T10:00:00+00:00" }, { version: 1, at: "2026-11-13T09:00:00+00:00" }];
  const skipped = [{ at: "2026-11-13T09:30:00+00:00", key_columns: ["a"] }, { at: "2026-11-13T10:00:00+00:00", key_columns: ["a"] }];
  const order = timeline(versions, skipped).map((r) => (r.type === "version" ? `v${r.version}` : "skip"));
  assert.deepEqual(order, ["skip", "v2", "skip", "v1"]);   // a skip in the same second as a version came after it
  assert.equal(versions.length, 2);
});

test("fill rate never rounds up to full, types read in Chinese", () => {
  assert.deepEqual([1, 0.9996, 0.5, null].map(percentText), ["100%", "99.9%", "50%", "—"]);
  assert.deepEqual(["integer", "date", "boolean", "weird"].map(typeLabel), ["整数", "日期", "是否", "weird"]);
});

test("a column's key cell reads the recorded check first, then the stored counts", () => {
  assert.equal(keyText({ possible_key: true, key_check: null }), "唯一，没有空值");
  assert.equal(keyText({ possible_key: false, key_check: null }), "—");
  assert.equal(keyText({ key_check: { status: "failed", violations: 1, null_key_rows: 0 } }), "主键检查没通过：重复 1 行");
  assert.equal(keyText({ key_check: { status: "passed" } }), "主键检查通过");
});
