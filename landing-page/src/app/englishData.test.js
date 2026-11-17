import assert from "node:assert/strict";
import test from "node:test";
import { diagnose, errorReport, STEPS } from "./connectModel.js";
import { originLink } from "./datasetModel.js";
import { keyText, typeLabel } from "./format.js";
import { setLocale } from "./i18n/index.js";
import { ROLE_CARDS, inviteText, twoPersonBanner } from "./usersModel.js";
import { ruleText } from "./permissionModel.js";
import { afterUpload, choiceProblem, filesProblem, resultLine, waysFor } from "./uploadModel.js";
import { estimateText, runSummary, scheduleProblem, sourceProblem, statusText } from "./sourceModel.js";
import { taskRow } from "./taskModel.js";
import { zoneLabel } from "./scheduleTime.js";
import { keyListText, noChangeText, versionChangeText } from "./versionText.js";

setLocale("en");   // the product's default; these pin the English copy of the data pages

test("the connection guide speaks English: steps, causes and the report", () => {
  assert.deepEqual(STEPS.map((s) => s.label), ["Type", "Connection", "Test", "Tables", "Schedule"]);
  const d = diagnose("连不上数据库：被对方拒绝");
  assert.equal(d.kind, "port");
  assert.equal(d.title, "Can't reach this address and port");
  assert.equal(d.causes[0].what, "The port is wrong");
  assert.equal(diagnose("something else").title, "Couldn't connect");
  const report = errorReport({ source: "erp", kind: "PostgreSQL", host: "db", port: 5432, database: "sales", username: "ro", tls: "none", message: "boom", at: "2026-11-16 10:00" });
  assert.equal(report.split("\n")[0], "OntoPoc could not connect to the database (2026-11-16 10:00)");
  assert.match(report, /Encryption: None/);
  assert.doesNotMatch(report, /password/i);
});

test("datasets, versions and columns read in English", () => {
  assert.equal(originLink("upload").label, "Upload");
  assert.equal(originLink("source:erp/public.orders").label, "Source erp (table public.orders)");
  assert.equal(typeLabel("datetime"), "Date and time");
  assert.equal(keyText({ possible_key: true }), "Unique, no blanks");
  assert.equal(keyText({ key_check: { status: "failed", violations: 1, null_key_rows: 2 } }), "Key check failed: 1 duplicate row, 2 blank rows");
  assert.equal(versionChangeText({ mode: "update_by_key", changed: 2, added: 1, unchanged: 5 }), "2 changed, 1 added, 5 unchanged");
  assert.equal(versionChangeText({ mode: "new", rows: 1 }), "1 row");
  assert.equal(keyListText(["a", "b"], 5), "a, b and more (5 rows in all)");
  assert.equal(noChangeText({ mode: "overwrite" }), "Overwrite: identical to the current version, so no new version was written");
});

test("upload messages and ways read in English", () => {
  assert.equal(filesProblem([]), "Choose a file first");
  assert.equal(choiceProblem("a.csv", { kind: null }, []), "a.csv: choose how to handle it: new dataset, update by key, or overwrite");
  assert.deepEqual(waysFor([]).primary.map((w) => w.label), ["New dataset"]);
  assert.deepEqual(waysFor(["x"]).folded.map((w) => w.label), ["Update by key", "Overwrite"]);
  assert.equal(resultLine({ name: "orders", mode: "new", rows: 3 }), "orders: created, 3 rows");
  assert.equal(resultLine({ name: "orders", mode: "new", rows: 1 }), "orders: created, 1 row");
  assert.deepEqual(afterUpload([{ name: "orders", mode: "new" }]).map((a) => a.label), ["View dataset", "Create an object type from it"]);
});

test("sources, schedules and runs read in English", () => {
  assert.equal(statusText({ status: "ok" }), "Connected");
  assert.equal(estimateText(1200), "≈ 1,200 (estimate)");
  assert.equal(runSummary({ status: "success", rows: 4, version: 2, changed: false }), "4 rows, version 2, Same as the previous version, so no new version was written");
  assert.equal(sourceProblem({ name: "", host: "", port: "5432", database: "", username: "", password: "" }, false), "Enter a name");
  assert.equal(scheduleProblem({ name: "x", kind: "source", target: "", cadence: "daily", time: "08:00", tz: "UTC" }, [], []), "Choose a source");
  assert.equal(zoneLabel("Asia/Shanghai"), "Beijing time (Asia/Shanghai)");
});

test("tasks, users and permissions read in English", () => {
  const row = taskRow({ id: 1, at: "2026-11-16T10:00:00", kind: "upload", title: "orders", mode: "new", created_version: true, version: 2, rows: 3, changes: {}, state: "done" });
  assert.equal(row.kind, "Upload dataset");
  assert.equal(row.state, "Done");
  assert.deepEqual(ROLE_CARDS.map((r) => r.label), ["Viewer", "Builder", "Admin"]);
  assert.equal(inviteText({ origin: "http://x", username: "ann", display_name: "Ann", password: "pw", role: "builder" }).split("\n")[0], "Hi Ann, I've created an OntoPoc account for you (Builder):");
  assert.match(twoPersonBanner({ enabled: true, active: false, builders: 1 }).text, /only 1 person can confirm/);
  assert.equal(ruleText({ column: "region", value: "East", user_ids: [1] }, "Region", "Ann, Bob"), "Ann, Bob can see rows where Region = East");
  assert.equal(ruleText({ column: "" , user_ids: [1] }, "", "Ann"), "Ann can see all rows");
});
