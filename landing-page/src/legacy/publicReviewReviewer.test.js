import assert from "node:assert/strict";
import test from "node:test";

import { REVIEWER_KEY, confirmOntology, emptyState, exportState, markCandidate } from "./publicReviewModel.js";

const NOW = "2026-10-01T02:00:00.000Z";
const pack = () => ({
  dataset: { id: "nhtsa-demo-car-2020-2021", label: "DEMO CAR · 2020–2021" },
  boundary: "b", run: { model: "m", matcher_prompt_version: "v3" }, ontology: { hash: "d".repeat(64) },
  recalls: [{ id: "A1", series: "A1", candidates: [{ id: "C1", bucket: "outside_all", text_check: { verdict: "no" } }] }],
  signals: { C1: {} },
});
const reviewed = () => markCandidate(confirmOntology(emptyState(pack()), NOW), "A1", "C1", "same", NOW);

test("the download names its dataset and reviewer, on the file and on every row", () => {
  const out = exportState(pack(), reviewed(), NOW, "  qe-01 ");
  assert.equal(out.dataset, "nhtsa-demo-car-2020-2021");
  assert.equal(out.reviewer, "qe-01");
  assert.deepEqual(out.reviews.map((r) => r.reviewer), ["qe-01"]);
});

test("a download without a reviewer still works; the import asks for one", () => {
  const out = exportState(pack(), reviewed(), NOW);
  assert.equal(out.reviewer, null);
  assert.equal(out.reviews[0].reviewer, null);
  assert.equal(out.reviews.length, 1);
});

test("the reviewer is remembered once for all datasets", () => {
  assert.equal(REVIEWER_KEY, "ontopoc.public-review.reviewer");
});
