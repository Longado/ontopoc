import assert from "node:assert/strict";
import test from "node:test";

import { anyRunning, durationText, taskRow } from "./taskModel.js";

const draft = (extra) => ({ kind: "draft", id: "abc", title: "订单.xlsx", state: "done", at: "2026-11-13T10:00:00+00:00", ended_at: "2026-11-13T10:01:30+00:00", ...extra });
const upload = (extra) => ({ kind: "upload", id: "订单@2", title: "订单", state: "done", at: "2026-11-13T10:00:00+00:00", who: "小王", mode: "update_by_key", version: 2, rows: 163, created_version: true, changes: { changed: 2, added: 3, unchanged: 1 }, ...extra });

test("durations read in minutes and seconds, and a missing end reads as nothing", () => {
  assert.equal(durationText("2026-11-13T10:00:00+00:00", "2026-11-13T10:01:30+00:00"), "1 分 30 秒");
  assert.equal(durationText("2026-11-13T10:00:00+00:00", "2026-11-13T10:00:05+00:00"), "5 秒");
  assert.equal(durationText("2026-11-13T10:00:00+00:00", null), "");
});

test("a modelling job says how long it took, why it failed, or that the restart cut it off", () => {
  assert.deepEqual([taskRow(draft()).kind, taskRow(draft()).state, taskRow(draft()).text, taskRow(draft()).bad], ["起草本体", "完成", "用了 1 分 30 秒", false]);
  const failed = taskRow(draft({ state: "failed", error: "建模时出错：x" }));
  assert.deepEqual([failed.state, failed.text, failed.bad], ["失败", "建模时出错：x", true]);
  const cut = taskRow(draft({ state: "interrupted", ended_at: null }));
  assert.deepEqual([cut.state, cut.bad], ["中断", true]);
  assert.equal(taskRow(draft({ state: "running", ended_at: null })).text, "");
});

test("an upload says what it did in the version list's words, and a skipped update is plain", () => {
  const made = taskRow(upload());
  assert.deepEqual([made.kind, made.dataset, made.who, made.text, made.bad], ["上传数据集", "订单", "小王", "按主键更新：改 2，增 3，未变 1，第 2 版", false]);
  assert.equal(taskRow(upload({ created_version: false, version: null, rows: null })).text, "按主键更新：没有变化，没有新版本");
  assert.equal(taskRow(upload({ mode: "new", version: 1, rows: 160, changes: { changed: 0, added: 160, unchanged: 0 } })).text, "新建：160 行，第 1 版");
  assert.equal(taskRow(upload({ mode: "overwrite", version: 3, rows: 2, changes: { replaced_rows: 160 } })).text, "覆盖：原 160 行，现 2 行，第 3 版");
});

test("the list keeps refreshing only while something is running", () => {
  assert.equal(anyRunning([draft(), upload()]), false);
  assert.equal(anyRunning([draft({ state: "running" })]), true);
});
