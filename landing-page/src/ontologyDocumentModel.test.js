import assert from "node:assert/strict";
import test from "node:test";

import { CHECK_LABELS, isDocument, sourceLine } from "./ontologyStudioModel.js";

test("document checks read as plain sentences", () => {
  assert.equal(CHECK_LABELS.quotes_verified, "模型提出的每一项都能在原文里找到引用");
  assert.equal(CHECK_LABELS.no_isolated_concepts, "每个概念至少和一个别的概念有关系");
});

test("a document run is told apart from a table run and described by paragraphs", () => {
  const doc = { file: { kind: "document" }, sources: [{ name: "流程.md", paragraphs: 3, chars: 120 }] };
  const table = { file: { kind: "table" }, sources: [{ name: "客户", rows: 31, fields: 5 }] };
  assert.equal(isDocument(doc), true);
  assert.equal(isDocument(table), false);
  assert.equal(sourceLine(doc), "流程.md 3 段 120 字");
  assert.equal(sourceLine(table), "客户 31 行 5 列");
});
