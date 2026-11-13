import assert from "node:assert/strict";
import test from "node:test";

import { choiceProblem, filesProblem, firstChoice, resultLine, stem, uploadPayload, uploadProblem, withKeyColumn, withKind, withTarget } from "./uploadModel.js";

const NAMES = ["订单", "客户"];
const file = (name, size = 100) => ({ name, size });

test("a free name starts as a new dataset; a taken name starts with nothing chosen", () => {
  assert.deepEqual(firstChoice("产品.xlsx", NAMES), { kind: "new", name: "产品", target: null, keyColumns: [] });
  assert.deepEqual(firstChoice("订单.xlsx", NAMES), { kind: null, name: "订单", target: "订单", keyColumns: [] });
  assert.deepEqual(firstChoice("订单-六月.csv", NAMES, "订单"), { kind: null, name: "订单-六月", target: "订单", keyColumns: [] });
});

test("an undecided taken name cannot be sent, and neither can a bare update or a new name that is taken", () => {
  const undecided = firstChoice("订单.xlsx", NAMES);
  assert.match(choiceProblem("订单.xlsx", undecided, NAMES), /新数据集、按主键更新或覆盖/);
  assert.match(choiceProblem("订单.xlsx", withKind(undecided, "new"), NAMES), /已经有叫“订单”的数据集/);
  assert.match(choiceProblem("订单.xlsx", withKind({ ...undecided, target: null }, "update_by_key"), NAMES), /选一个要更新的数据集/);
  assert.match(choiceProblem("订单.xlsx", withKind(undecided, "update_by_key"), NAMES), /选出主键列/);
  assert.equal(choiceProblem("订单.xlsx", withKind(undecided, "overwrite"), NAMES), "");
  assert.equal(choiceProblem("订单.xlsx", withKeyColumn(withKind(undecided, "update_by_key"), "订单号", true), NAMES), "");
  assert.equal(choiceProblem("产品.xlsx", firstChoice("产品.xlsx", NAMES), NAMES), "");
});

test("key columns are toggled without mutating, and a new target clears them", () => {
  const a = withKind(firstChoice("订单.xlsx", NAMES), "update_by_key");
  const b = withKeyColumn(withKeyColumn(a, "订单号", true), "承诺版本", true);
  assert.deepEqual([a.keyColumns, b.keyColumns], [[], ["订单号", "承诺版本"]]);
  assert.deepEqual(withKeyColumn(b, "订单号", false).keyColumns, ["承诺版本"]);
  assert.deepEqual(withTarget(b, "客户").keyColumns, []);
});

test("files are checked for type and total size before sending", () => {
  assert.equal(filesProblem([file("a.xlsx"), file("b.csv")]), "");
  assert.match(filesProblem([file("a.pdf")]), /只收 .xlsx 和 .csv/);
  assert.match(filesProblem([file("a.xlsx", 6 * 1024 * 1024), file("b.xlsx", 6 * 1024 * 1024)]), /上限 10.0 MB/);
  assert.equal(filesProblem([]), "先选择文件");
  assert.equal(stem("订单.2026.xlsx"), "订单.2026");
});

test("two files writing the same dataset are refused", () => {
  const files = [file("订单.xlsx"), file("订单-六月.csv")];
  const choices = files.map((f) => withKind(firstChoice(f.name, NAMES, "订单"), "overwrite"));
  assert.match(uploadProblem(files, choices, NAMES), /两个文件都要写入“订单”/);
  assert.equal(uploadProblem(files.slice(0, 1), choices.slice(0, 1), NAMES), "");
});

test("the request carries the target and way only for an update, and a name only when it was changed", () => {
  const files = [file("产品.xlsx"), file("订单.csv"), file("客户.csv"), file("新.csv")];
  const choices = [
    firstChoice("产品.xlsx", NAMES),
    withKeyColumn(withKind(firstChoice("订单.csv", NAMES), "update_by_key"), "订单号", true),
    withKind(firstChoice("客户.csv", NAMES), "overwrite"),
    { ...firstChoice("新.csv", NAMES), name: " 新数据 " },
  ];
  const body = uploadPayload(" 小林 ", files, ["a", "b", "c", "d"], choices);
  assert.equal(body.who, "小林");
  assert.deepEqual(body.files, [
    { filename: "产品.xlsx", content_base64: "a" },
    { filename: "订单.csv", content_base64: "b", target: "订单", mode: "update_by_key", key_columns: ["订单号"] },
    { filename: "客户.csv", content_base64: "c", target: "客户", mode: "overwrite" },
    { filename: "新.csv", content_base64: "d", name: "新数据" },
  ]);
});

test("each saved file reads as a sentence; a skipped update is plain and a failed key check is said", () => {
  const base = { name: "订单", version: 2, rows: 163, created_version: true, reused: false, mode: "update_by_key", changes: { changed: 2, added: 3, unchanged: 1 } };
  assert.equal(resultLine(base), "订单：按主键更新，改 2、增 3、未变 1；现在 163 行，第 2 版");
  assert.equal(resultLine({ ...base, created_version: false }), "订单：没有变化，没有新版本");
  const blank = { ...base, changes: { ...base.changes, blank_kept: 4 } };
  assert.equal(resultLine(blank), "订单：按主键更新，改 2、增 3、未变 1；现在 163 行，第 2 版；新文件里 4 个空格子，保留了原值");
  assert.equal(resultLine({ ...blank, created_version: false }), "订单：没有变化，没有新版本（新文件里 4 个空格子，保留了原值）");
  assert.match(resultLine({ ...base, key_check: { status: "failed" } }), /主键检查没通过$/);
  assert.equal(resultLine({ ...base, mode: "overwrite" }), "订单：已覆盖，现在 163 行，第 2 版");
  assert.equal(resultLine({ ...base, mode: "new", rows: 12 }), "订单：新建，12 行");
  assert.equal(resultLine({ ...base, reused: true, version: 1 }), "订单：内容和第 1 版完全一样，已设为当前版本");
});
