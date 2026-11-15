import assert from "node:assert/strict";
import test from "node:test";

import { CHECK_LABELS, COVERAGE_NOTE } from "./ontologyStudioModel.js";

test("checks say what was actually checked, not more", () => {
  assert.equal(CHECK_LABELS.no_isolated_concepts, "抽出来的概念，每个都至少连着一条抽出来的关系");
  assert.equal(CHECK_LABELS.quotes_verified, "模型提出的每一项都能在原文里找到引用");
});

test("every conclusion says which data it covers", () => {
  assert.equal(COVERAGE_NOTE, "所有结论只覆盖这一次上传的文件；别的系统里有没有、别的表里记没记，这里看不到。");
});
