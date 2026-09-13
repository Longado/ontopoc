import assert from "node:assert/strict";
import test from "node:test";

import {
  confirmOntology, defaultRecallId, emptyState, exportState, markCandidate, markOf, orderCandidates,
  summarize, timingLabel, validatePack,
} from "./publicReviewModel.js";

const NOW = "2026-09-13T08:00:00.000Z";
const timing = (relation, days) => ({ event_date: "2021-08-20", signal_date: "x", relation, days });
const signal = (date, flags = []) => ({ objects: ["EV"], parts: ["P"], date, flags, fields: [] });
const pack = () => ({
  schema: "public_review_pack.v1", boundary: "b", run: { model: "m", matcher_prompt_version: "v3" },
  ontology: { hash: "c".repeat(64), status: "auto_built_verified", human_review: "pending" },
  groups: [{ id: "BATTERY", recalls: ["A1", "A2"] }, { id: "SEATS", recalls: ["S1"] }],
  recalls: [
    { id: "A1", series: "A1", date: "2020-01-01", mechanism: ["BATTERY"], covered: [], fields: [], text_checked: true, counts: { inside_scope: 0, covered_by_other_event: 0, outside_all: 3 },
      candidates: [
        { id: "C1", bucket: "outside_all", timing: timing("before", -10), via_alias: false, other_events: [], text_check: { verdict: "no" } },
        { id: "C2", bucket: "outside_all", timing: timing("after", 20), via_alias: false, other_events: [], text_check: { verdict: "yes" } },
        { id: "C3", bucket: "outside_all", timing: timing("after", 5), via_alias: true, other_events: [], text_check: { verdict: "unknown" } },
      ] },
    { id: "A2", series: "A1", date: "2024-01-01", mechanism: ["BATTERY"], covered: [], fields: [], text_checked: true, counts: { inside_scope: 0, covered_by_other_event: 0, outside_all: 1 },
      candidates: [{ id: "C2", bucket: "outside_all", timing: timing("before", -100), via_alias: false, other_events: [], text_check: { verdict: "yes" } }] },
    { id: "S1", series: "S1", date: "2021-01-01", mechanism: ["SEATS"], covered: [], fields: [], text_checked: false, counts: { inside_scope: 0, covered_by_other_event: 0, outside_all: 1 },
      candidates: [{ id: "C4", bucket: "outside_all", timing: null, via_alias: false, other_events: [], text_check: null }] },
  ],
  signals: { C1: signal("2021-01-01", ["crash", "fire"]), C2: signal("2022-01-01"), C3: signal("2023-01-01", ["fire"]), C4: signal("2021-02-01") },
});

test("after-recall complaints come first, then fire or crash, then the newest", () => {
  const p = pack();
  assert.deepEqual(orderCandidates(p.recalls[0].candidates, p.signals).map((c) => c.id), ["C3", "C2", "C1"]);
});

test("timing reads as plain words", () => {
  assert.equal(timingLabel(timing("after", 1053)), "召回后 1053 天");
  assert.equal(timingLabel(timing("same_day", 0)), "召回当天");
  assert.equal(timingLabel(timing("before", -30)), "召回前 30 天");
  assert.equal(timingLabel(null), "");
});

test("a mark made under one recall of a series shows under the others", () => {
  const p = pack();
  const state = markCandidate(confirmOntology(emptyState(p), NOW), "A1", "C2", "same", NOW);
  assert.equal(markOf(state, "A1", "C2").mark, "same");
  assert.equal(summarize(p, state, "A2").reviewed, 1);
  assert.equal(summarize(p, state, "S1").reviewed, 0);
  assert.equal(exportState(p, state, NOW).reviews.length, 1);
});

test("default recall is the one with model verdicts and the most outside-scope complaints", () => {
  assert.equal(defaultRecallId(pack()), "A1");
});

test("pack whose candidates point at missing complaints is rejected before rendering", () => {
  const p = pack();
  delete p.signals.C3;
  assert.throws(() => validatePack(p), /投诉/);
  const q = pack();
  q.recalls[0].candidates = "oops";
  assert.throws(() => validatePack(q));
});
