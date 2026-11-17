import assert from "node:assert/strict";
import test from "node:test";

import { actionRow, emptyActionForm, lastRecordText, saveBlock } from "./actionModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("zh");   // these tests pin the Chinese wording; the English is in modelingEnglish.test.js

test("an action is one row of the table: its name, a one-word kind, what it says, its state, its last record (W3)", () => {
  const edit = { id: "改订单状态", name: "改订单状态", kind: "edit", says: "改 状态码", state: "confirmed" };
  assert.deepEqual(actionRow(edit, [], true), { id: "改订单状态", name: "改订单状态", kind: "改", says: "改 状态码", state: "confirmed", last: "还没有提交", canRun: false });
  assert.equal(actionRow({ ...edit, kind: "create" }, [], true).kind, "新建");
  assert.equal(actionRow({ ...edit, kind: "delete" }, [], true).kind, "删除");
});

test("only a confirmed create the person may submit has a run button, and only for a builder", () => {
  const create = { name: "新建订单", kind: "create", says: "", state: "confirmed" };
  assert.equal(actionRow(create, [], true).canRun, true);
  assert.equal(actionRow(create, [], false).canRun, false);
  assert.equal(actionRow({ ...create, state: "proposed" }, [], true).canRun, false);
  assert.equal(actionRow({ ...create, can_submit: false }, [], true).canRun, false);
  assert.equal(actionRow({ ...create, kind: "edit" }, [], true).canRun, false);   // an edit runs from the object it changes
});

test("the last record is who, when and how it stands", () => {
  assert.equal(lastRecordText([]), "还没有提交");
  assert.match(lastRecordText([{ submitted_by: "Ann", submitted_at: "2026-11-14T08:30:00+00:00", state: "pending" }, { submitted_by: "Bob", submitted_at: "2026-11-01T08:30:00+00:00", state: "approved" }]), /^Ann · \d{2}-\d{2} \d{2}:\d{2} · 等批准$/);
  assert.equal(lastRecordText(null), "");   // records not read yet
});

test("a disabled save says why: the first thing missing, or that it is saving", () => {
  assert.deepEqual(saveBlock(emptyActionForm(), false), { disabled: true, reason: "要写行为的名字" });
  assert.deepEqual(saveBlock({ ...emptyActionForm(), name: "x", properties: ["a"] }, false), { disabled: false, reason: "" });
  assert.deepEqual(saveBlock({ ...emptyActionForm(), name: "x", properties: ["a"] }, true), { disabled: true, reason: "正在保存" });
});
