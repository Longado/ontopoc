import assert from "node:assert/strict";
import test from "node:test";

import { MARKS, confirmOntology, emptyState, exportState, markCandidate, noteCandidate, personalInfo, uncleanNotes, verdictSplit } from "./publicReviewModel.js";

const NOW = "2026-10-01T02:00:00.000Z";
const pack = () => ({
  dataset: { id: "nhtsa-demo" }, boundary: "b", run: { model: "m", matcher_prompt_version: "v3" }, ontology: { hash: "f".repeat(64), value_aliases: [] },
  recalls: [{ id: "R1", series: "R1", candidates: [
    { id: "C1", bucket: "inside_scope", text_check: { verdict: "yes" } }, { id: "C2", bucket: "inside_scope", text_check: { verdict: "no" } },
    { id: "C3", bucket: "inside_scope", text_check: { verdict: "unknown" } }, { id: "C4", bucket: "inside_scope", text_check: null },
    { id: "C5", bucket: "outside_all", text_check: { verdict: "no" } }] }],
  signals: { C1: {}, C2: {}, C3: {}, C4: {}, C5: {} },
});

test("the verdict names a failure, not a defect", () => {
  assert.deepEqual(MARKS, { same: "同一故障", different: "不是", unsure: "说不清" });
});

test("every download says it is an internal working draft, not a finding", () => {
  const out = exportState(pack(), emptyState(pack()), NOW);
  assert.match(out.notice, /内部技术排查工作稿/);
  assert.match(out.notice, /不构成缺陷认定/);
});

test("personal details and machine secrets are spotted before they leave the browser", () => {
  for (const text of ["/Users/x/a.png", "sk-abcdefghijklmnopqrstuv", "VIN 1G1FZ6S01K4", "qe@example.com", "13812345678", "(312) 555-0199"]) {
    assert.ok(personalInfo(text), text);
  }
  for (const text of ["qe-01", "2020-10-13 召回后 2021 款仍起火", "SERVICE BRAKES", "11483089"]) {
    assert.equal(personalInfo(text), "", text);
  }
});

test("notes that would be refused at import are listed", () => {
  let state = confirmOntology(emptyState(pack()), NOW);
  state = markCandidate(state, "R1", "C1", "same", NOW);
  state = noteCandidate(state, "R1", "C1", "车主电话 13812345678", NOW);
  state = markCandidate(state, "R1", "C2", "different", NOW);
  state = noteCandidate(state, "R1", "C2", "只写了现象", NOW);
  assert.deepEqual(uncleanNotes(state), [{ recall: "R1", complaint: "C1", issue: "电话" }]);
});

test("bucket counts come with the model's first-pass split", () => {
  const inside = pack().recalls[0].candidates.filter((c) => c.bucket === "inside_scope");
  assert.deepEqual(verdictSplit(inside), { yes: 1, no: 1, unknown: 1, none: 1 });
});
