import assert from "node:assert/strict";
import test from "node:test";

import { confirmOntology, elsewhere, emptyState, hasConflict, markCandidate, overview } from "./publicReviewModel.js";

const NOW = "2026-10-01T02:00:00.000Z";
const c = (id, verdict, bucket = "outside_all") => ({ id, bucket, text_check: verdict ? { verdict } : null });
const pack = () => ({
  ontology: { hash: "a".repeat(64) },
  recalls: [
    { id: "R1", series: "R1", date: "2020-10-13", candidates: [c("C1", "yes"), c("C2", "no"), c("C3", "no", "inside_scope")] },
    { id: "R2", series: "R1", date: "2021-03-01", candidates: [c("C2", "no")] },
    { id: "R3", series: "R3", date: "2022-12-16", candidates: [c("C1", "unknown", "covered_by_other_event"), c("C2", "no"), c("C4", null)] },
  ],
  signals: {},
});

test("a complaint's other recalls are listed with their first call and your review, same series left out", () => {
  let state = confirmOntology(emptyState(pack()), NOW);
  state = markCandidate(state, "R3", "C1", "different", NOW);
  assert.deepEqual(elsewhere(pack(), state, "R1", "C1"), [
    { recall: "R3", date: "2022-12-16", bucket: "covered_by_other_event", model: "unsure", human: "different" }]);
  assert.deepEqual(elsewhere(pack(), state, "R1", "C2").map((x) => x.recall), ["R3"]);
  assert.deepEqual(elsewhere(pack(), state, "R1", "C3"), []);
});

test("different first calls across recalls are flagged", () => {
  const p = pack();
  assert.equal(hasConflict(p, p.recalls[0], p.recalls[0].candidates[0]), true);
  assert.equal(hasConflict(p, p.recalls[0], p.recalls[0].candidates[1]), false);
  assert.equal(hasConflict(p, p.recalls[2], p.recalls[2].candidates[2]), false);
});

test("the results overview covers every recall series", () => {
  let state = confirmOntology(emptyState(pack()), NOW);
  state = markCandidate(state, "R1", "C1", "same", NOW);
  state = markCandidate(state, "R1", "C2", "same", NOW);
  state = markCandidate(state, "R3", "C4", "unsure", NOW);
  assert.deepEqual(overview(pack(), state), [
    { series: "R1", recalls: ["R1", "R2"], total: 3, reviewed: 2, compared: 2, agree: 1, disagreements: [{ recall: "R1", id: "C2", model: "different", human: "same" }] },
    { series: "R3", recalls: ["R3"], total: 3, reviewed: 1, compared: 0, agree: 0, disagreements: [] },
  ]);
});
