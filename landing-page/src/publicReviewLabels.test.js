import assert from "node:assert/strict";
import test from "node:test";

import { confirmOntology, displayValue, emptyState, exportState, fieldLabel, markCandidate, noteCandidate } from "./publicReviewModel.js";

const NOW = "2026-09-13T08:00:00.000Z";
const pack = () => ({
  schema: "public_review_pack.v1", boundary: "b", run: { model: "m", matcher_prompt_version: "v3" },
  ontology: { hash: "d".repeat(64), status: "auto_built_verified", human_review: "pending" },
  groups: [{ id: "BATTERY", recalls: ["A1", "A2"] }],
  recalls: [
    { id: "A1", series: "A1", date: "2020-01-01", mechanism: ["BATTERY"], covered: [], fields: [], text_checked: true, counts: {},
      candidates: [{ id: "C1", bucket: "outside_all", via_alias: true, timing: { event_date: "2020-01-01", signal_date: "2024-07-08", relation: "after", days: 1650 }, other_events: [], text_check: { verdict: "no" } }] },
    { id: "A2", series: "A1", date: "2024-01-01", mechanism: ["BATTERY"], covered: [], fields: [], text_checked: true, counts: {},
      candidates: [{ id: "C1", bucket: "outside_all", via_alias: true, timing: { event_date: "2024-01-01", signal_date: "2024-07-08", relation: "after", days: 189 }, other_events: [], text_check: { verdict: "no" } }] },
  ],
  signals: { C1: { objects: ["CHEVROLET BOLT EV 2023"], parts: ["ELECTRICAL SYSTEM", "SEATS"], date: "2024-07-08", flags: ["fire"], fields: [] } },
});

test("known fields read in Chinese and unknown ones keep their raw name", () => {
  assert.equal(fieldLabel("dateComplaintFiled"), "投诉提交日期");
  assert.equal(fieldLabel("summary"), "投诉描述");
  assert.equal(fieldLabel("Remedy"), "补救措施");
  assert.equal(fieldLabel("somethingNew"), "somethingNew");
  assert.equal(displayValue("True"), "是");
  assert.equal(displayValue("False"), "否");
  assert.equal(displayValue("2024-07-08"), "2024-07-08");
});

test("download rows can be read without the page", () => {
  let state = markCandidate(confirmOntology(emptyState(pack()), NOW), "A1", "C1", "same", NOW);
  state = noteCandidate(state, "A1", "C1", "座椅下起火", NOW);
  const [row] = exportState(pack(), state, NOW).reviews;
  assert.deepEqual(row, {
    recall: "A1", complaint: "C1", bucket: "outside_all", human: "same", note: "座椅下起火", model_verdict: "no",
    updated_at: NOW, vehicles: ["CHEVROLET BOLT EV 2023"], parts: ["ELECTRICAL SYSTEM", "SEATS"],
    complaint_date: "2024-07-08", flags: ["fire"], recall_date: "2020-01-01", timing: "after", days_from_recall: 1650,
    via_alias: true, series_recalls: ["A1", "A2"], reviewer: null,
  });
});
