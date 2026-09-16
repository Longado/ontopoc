import assert from "node:assert/strict";
import test from "node:test";

import { batchProblem, batchSummary, uploadPayload } from "./ontologyUploadModel.js";

const f = (name, size, type = "table") => ({ name, size, type });

test("a batch is refused for the same reasons one file is, and names the file", () => {
  assert.equal(batchProblem([f("客户.csv", 10), f("订单.xlsx", 20)]), "");
  assert.match(batchProblem([f("客户.csv", 10), f("报告.pdf", 20)]), /报告\.pdf/);
  assert.match(batchProblem([f("空.csv", 0)]), /空\.csv/);
  assert.match(batchProblem([f("大.csv", 6 * 1024 * 1024), f("也大.csv", 6 * 1024 * 1024)]), /一共/);
  assert.equal(batchProblem([]), "先选择文件");
});

test("one document alone is still allowed", () => {
  assert.equal(batchProblem([f("流程.md", 10)]), "");
  assert.match(batchProblem([f("流程.md", 10), f("流程2.md", 10)]), /一次只能传一份文档/);
});

test("the batch says what will be modelled together", () => {
  assert.equal(batchSummary([f("客户.csv", 1024), f("订单.csv", 2048)]), "2 个文件 · 3 KB · 会放在一起建模");
  assert.equal(batchSummary([f("流程.md", 1024)]), "1 个文件 · 1 KB");
});

test("one file keeps the request shape it always had", () => {
  assert.deepEqual(Object.keys(uploadPayload([f("订单.csv", 1)], "目的", "AAA")), ["filename", "content_base64", "purpose"]);
  const many = uploadPayload([f("客户.csv", 1), f("订单.csv", 1)], "目的", "AAA");
  assert.deepEqual(Object.keys(many), ["files", "purpose"]);
  assert.deepEqual(many.files, [{ filename: "客户.csv", content_base64: "AAA" }, { filename: "订单.csv", content_base64: "AAA" }]);
});
