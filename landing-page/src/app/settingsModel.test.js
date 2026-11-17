import assert from "node:assert/strict";
import test from "node:test";
import { BACKUP_FILES, workspaceRows } from "./settingsModel.js";

const rowOf = (rows, key) => rows.find((r) => r.key === key);

test("the model row says whether questions can be answered, and what to do when not", () => {
  assert.equal(rowOf(workspaceRows({ modelReady: true }), "model").state, "ok");
  const no = rowOf(workspaceRows({ modelReady: false }), "model");
  assert.equal(no.state, "warn");
  assert.match(no.text, /没有配置/);
  assert.equal(rowOf(workspaceRows({ modelReady: null }), "model").state, "unknown");
});

test("the two-person row follows the rule and links to the users page", () => {
  const on = rowOf(workspaceRows({ twoPerson: { enabled: true, active: true, builders: 2 } }), "two");
  assert.equal(on.state, "ok");
  assert.equal(on.link.href, "#/users");
  const idle = rowOf(workspaceRows({ twoPerson: { enabled: true, active: false, builders: 1 } }), "two");
  assert.equal(idle.state, "warn");
  assert.equal(rowOf(workspaceRows({ twoPerson: { enabled: false, active: false, builders: 1 } }), "two").state, "warn");
  assert.equal(rowOf(workspaceRows({ twoPerson: null }), "two").state, "unknown");
});

test("the build row shows the running build and says when the files changed after start", () => {
  assert.match(rowOf(workspaceRows({ health: { running: "abc123", stale: false } }), "build").text, /abc123/);
  const stale = rowOf(workspaceRows({ health: { running: "abc123", stale: true } }), "build");
  assert.equal(stale.state, "warn");
  assert.match(stale.text, /重启/);
  assert.equal(rowOf(workspaceRows({ health: null }), "build").state, "unknown");
});

test("backup advice names the two files", () => {
  assert.deepEqual(BACKUP_FILES.map((f) => f.file), ["workspace.sqlite", "sources.key"]);
});
