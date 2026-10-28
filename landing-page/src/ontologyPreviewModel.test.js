import assert from "node:assert/strict";
import test from "node:test";

import { previewFactText, previewKeysText, previewLinkText } from "./ontologyUploadModel.js";

test("a column's counts read as how many values, how many kinds, and whether they all differ", () => {
  assert.equal(previewFactText({ filled: 407, distinct: 407, unique: true }), "407 个有值 · 407 种，各不相同");
  assert.equal(previewFactText({ filled: 613, distinct: 365 }), "613 个有值 · 365 种");
  assert.equal(previewFactText({ filled: 1921, distinct: 1 }), "1921 个有值 · 全是同一个值");
  assert.equal(previewFactText({ filled: 0, distinct: 0 }), "全空");
  assert.equal(previewFactText({}), "—");   // a service from before the counts
});

test("a table says which columns tell its rows apart, or that none do", () => {
  assert.equal(previewKeysText({ unique_columns: ["订单号", "金额"] }), "每行都不同的列（不算日期、小数和长文本）：订单号、金额");
  assert.equal(previewKeysText({ unique_columns: [], unique_pairs: [["订单号", "行号"], ["订单号", "数量"]] }),
    "没有一列每行都不同（不算日期、小数和长文本）；两列合起来每行都不同的有：订单号 + 行号、订单号 + 数量");
  assert.equal(previewKeysText({ unique_columns: [], unique_pairs: [] }), "每行都有值的列里（不算日期、小数和长文本），没有一列或两列合起来每行都不同");
  assert.equal(previewKeysText({ unique_columns: [] }), "没有一列每行都不同（不算日期、小数和长文本）");
  assert.equal(previewKeysText({}), null);   // one row: nothing to tell apart
});

test("a likely link names where the values were found", () => {
  assert.equal(previewLinkText({ field: "award_key", to_table: "contracts", to_field: "award_key", found: 365, of: 368 }),
    "award_key 的 368 个不同值里，有 365 个在 contracts.award_key");
});
