import assert from "node:assert/strict";
import test from "node:test";

import { packUrl, pickDataset, validateIndex } from "./publicReviewModel.js";

const entry = (id, pack = `${id}.json`) => ({ id, label: id.toUpperCase(), pack, recalls: 3, complaints: 5, retrieved: "2026-09-13" });
const index = () => ({ schema: "review_datasets.v1", datasets: [entry("nhtsa-chevrolet-bolt"), entry("nhtsa-hyundai-kona")] });

test("dataset index is checked before anything is fetched", () => {
  assert.equal(validateIndex(index()).datasets.length, 2);
  assert.throws(() => validateIndex({ schema: "other", datasets: [] }), /数据集清单/);
  assert.throws(() => validateIndex({ schema: "review_datasets.v1", datasets: [] }), /没有数据集/);
  assert.throws(() => validateIndex({ schema: "review_datasets.v1", datasets: [entry("x", "../secret.json")] }), /文件名/);
  assert.throws(() => validateIndex({ schema: "review_datasets.v1", datasets: [entry("x", "https://evil.test/a.json")] }), /文件名/);
});

test("the last chosen dataset comes back, otherwise the first one", () => {
  assert.equal(pickDataset(index(), "nhtsa-hyundai-kona"), "nhtsa-hyundai-kona");
  assert.equal(pickDataset(index(), "gone"), "nhtsa-chevrolet-bolt");
  assert.equal(pickDataset(index(), null), "nhtsa-chevrolet-bolt");
});

test("pack files are served from the data folder", () => {
  assert.equal(packUrl(entry("nhtsa-hyundai-kona")), "/data/nhtsa-hyundai-kona.json");
});
