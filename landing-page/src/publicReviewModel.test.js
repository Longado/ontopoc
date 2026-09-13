import assert from "node:assert/strict";
import test from "node:test";

import {
  confirmOntology, emptyState, exportState, highlight, markCandidate, nextSelection,
  noteCandidate, restoreState, storageKey, summarize, validatePack, visibleCandidates,
} from "./publicReviewModel.js";

const NOW = "2026-09-13T08:00:00.000Z";
const check = (verdict) => ({ verdict, reasoning: "r", evidence: verdict === "yes" ? "smoke" : "", model: "deepseek-flash", prompt_version: "public_defect_match.v2" });
const pack = () => ({
  schema: "public_review_pack.v1",
  boundary: "候选，待质量工程师复核",
  run: { model: "deepseek-flash", modeler_prompt_version: "public_ontology_modeler.v2", matcher_prompt_version: "public_defect_match.v2" },
  ontology: { hash: "a".repeat(64), status: "auto_built_verified", human_review: "pending", object_types: [], relations: [], data_gaps: [] },
  recalls: [{
    id: "R1", mechanism: ["BATTERY"], covered: ["EV 2020"], fields: [], text_checked: true,
    counts: { inside_scope: 1, covered_by_other_event: 0, outside_all: 2 },
    candidates: [
      { id: "C1", bucket: "outside_all", other_events: [], text_check: check("yes") },
      { id: "C2", bucket: "outside_all", other_events: [], text_check: check("no") },
      { id: "C3", bucket: "inside_scope", other_events: [], text_check: check("unknown") },
    ],
  }, {
    id: "R2", mechanism: ["AIR BAGS"], covered: [], fields: [], text_checked: false,
    counts: { inside_scope: 0, covered_by_other_event: 0, outside_all: 1 },
    candidates: [{ id: "C4", bucket: "outside_all", other_events: [], text_check: null }],
  }],
  signals: { C1: { objects: [], parts: [], fields: [] }, C2: { objects: [], parts: [], fields: [] }, C3: { objects: [], parts: [], fields: [] }, C4: { objects: [], parts: [], fields: [] } },
});

test("rejects data that is not a verified review pack", () => {
  assert.throws(() => validatePack({ schema: "other" }));
  assert.throws(() => validatePack({ ...pack(), ontology: { ...pack().ontology, status: "blocked" } }));
  assert.equal(validatePack(pack()).schema, "public_review_pack.v1");
});

test("review is blocked until the ontology is confirmed", () => {
  const state = emptyState(pack());
  assert.throws(() => markCandidate(state, "R1", "C1", "same", NOW), /确认本体/);
  const confirmed = confirmOntology(state, NOW);
  assert.equal(confirmed.confirmed_at, NOW);
  assert.equal(state.confirmed_at, null);
});

test("a mark is saved at once and a note needs a mark first", () => {
  const confirmed = confirmOntology(emptyState(pack()), NOW);
  assert.throws(() => noteCandidate(confirmed, "R1", "C1", "look again", NOW), /先选/);
  assert.throws(() => markCandidate(confirmed, "R1", "C1", "maybe", NOW));
  const marked = markCandidate(confirmed, "R1", "C1", "same", NOW);
  const noted = noteCandidate(marked, "R1", "C1", "座椅下起火", NOW);
  const changed = markCandidate(noted, "R1", "C1", "unsure", NOW);
  assert.deepEqual(changed.marks["R1/C1"], { mark: "unsure", note: "座椅下起火", updated_at: NOW });
  assert.equal(confirmed.marks["R1/C1"], undefined);
});

test("selection always belongs to the visible list", () => {
  const recall = pack().recalls[0];
  const outside = visibleCandidates(recall, "outside_all");
  assert.deepEqual(outside.map((c) => c.id), ["C1", "C2"]);
  assert.equal(nextSelection("C2", outside), "C2");
  assert.equal(nextSelection("C3", outside), "C1");
  assert.equal(nextSelection("C1", visibleCandidates(recall, "covered_by_other_event")), "");
});

test("summary compares human marks with model verdicts only where the model ran", () => {
  let state = confirmOntology(emptyState(pack()), NOW);
  state = markCandidate(state, "R1", "C1", "same", NOW);
  state = markCandidate(state, "R1", "C2", "same", NOW);
  state = markCandidate(state, "R2", "C4", "different", NOW);
  const r1 = summarize(pack(), state, "R1");
  assert.deepEqual({ reviewed: r1.reviewed, total: r1.total, compared: r1.compared, agree: r1.agree }, { reviewed: 2, total: 3, compared: 2, agree: 1 });
  assert.deepEqual(r1.disagreements, [{ id: "C2", model: "different", human: "same" }]);
  const r2 = summarize(pack(), state, "R2");
  assert.deepEqual({ reviewed: r2.reviewed, compared: r2.compared }, { reviewed: 1, compared: 0 });
});

test("stored reviews restore only for the same ontology and never silently reset", () => {
  const p = pack();
  assert.match(storageKey(p), /^ontopoc\.public-review\.v1\.a{16}$/);
  assert.equal(restoreState(null, p).confirmed_at, null);
  const saved = markCandidate(confirmOntology(emptyState(p), NOW), "R1", "C1", "same", NOW);
  assert.deepEqual(restoreState(JSON.stringify(saved), p), saved);
  assert.throws(() => restoreState(JSON.stringify({ ...saved, ontology_hash: "b".repeat(64) }), p));
  assert.throws(() => restoreState("{not json", p));
  assert.throws(() => restoreState(JSON.stringify({ ...saved, marks: { "R1/C1": { mark: "maybe" } } }), p));
});

test("export carries labels with model verdicts and versions", () => {
  const state = markCandidate(confirmOntology(emptyState(pack()), NOW), "R1", "C2", "same", NOW);
  const out = exportState(pack(), state, NOW);
  assert.equal(out.schema, "public_review_export.v1");
  assert.equal(out.matcher_prompt_version, "public_defect_match.v2");
  assert.deepEqual(out.reviews, [{ recall: "R1", complaint: "C2", bucket: "outside_all", human: "same", note: "", model_verdict: "no", updated_at: NOW }]);
});

test("evidence highlight finds the quote or returns nothing", () => {
  assert.deepEqual(highlight("I saw smoke under the seat", "smoke"), ["I saw ", "smoke", " under the seat"]);
  assert.equal(highlight("text", ""), null);
  assert.equal(highlight("text", "absent"), null);
});
