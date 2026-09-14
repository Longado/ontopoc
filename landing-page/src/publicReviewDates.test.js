import assert from "node:assert/strict";
import test from "node:test";

import { dateCaveat, earlierDates, keyAction } from "./publicReviewModel.js";

const timing = (relation, event_date = "2020-11-13") => ({ event_date, signal_date: "2021-01-01", relation, days: 49 });
const signal = (incident) => ({ fields: [{ path: "dateComplaintFiled", value: "2021-01-01" }, { path: "dateOfIncident", value: incident }, { path: "summary", value: "2019-01-01 was the day" }] });
const pack = () => ({
  source: { date_fields: { complaints: ["dateComplaintFiled", "dateOfIncident"], recalls: ["ReportReceivedDate"] } },
  ontology: { object_types: [
    { role: "event", time_field: { source: "recalls", path: "ReportReceivedDate" } },
    { role: "signal", time_field: { source: "complaints", path: "dateComplaintFiled" } }] },
  recalls: [
    { id: "R1", candidates: [{ id: "A", timing: timing("after") }, { id: "B", timing: timing("after") }, { id: "C", timing: timing("before") }] },
    { id: "R2", candidates: [{ id: "A", timing: timing("after", "2018-01-01") }, { id: "D", timing: null }] },
  ],
  signals: { A: signal("2020-06-01"), B: signal("2020-12-01"), C: signal("2019-01-01"), D: signal("2020-01-01") },
});

test("a complaint filed after the recall but dated earlier elsewhere is flagged", () => {
  const p = pack();
  assert.deepEqual(earlierDates(p, p.recalls[0].candidates[0]), ["dateOfIncident"]);
  assert.deepEqual(earlierDates(p, p.recalls[0].candidates[1]), []);
  assert.deepEqual(earlierDates(p, p.recalls[0].candidates[2]), []);
  assert.deepEqual(earlierDates(p, p.recalls[1].candidates[0]), []);
  assert.deepEqual(earlierDates(p, p.recalls[1].candidates[1]), []);
});

test("the scope page counts how often the other date would flip the order", () => {
  assert.deepEqual(dateCaveat(pack()), { fields: ["dateOfIncident"], after: 3, earlier: 1 });
  assert.equal(dateCaveat({ ...pack(), source: {} }), null);
});

test("review keys work wherever focus is, except while typing", () => {
  assert.deepEqual(keyAction({ key: "2", target: { tagName: "BODY" } }), { mark: "different" });
  assert.deepEqual(keyAction({ key: "ArrowDown", target: { tagName: "BUTTON" } }), { step: 1 });
  assert.deepEqual(keyAction({ key: "ArrowUp", target: { tagName: "BODY" } }), { step: -1 });
  assert.equal(keyAction({ key: "1", target: { tagName: "TEXTAREA" } }), null);
  assert.equal(keyAction({ key: "ArrowDown", target: { tagName: "SELECT" } }), null);
  assert.equal(keyAction({ key: "1", metaKey: true, target: { tagName: "BODY" } }), null);
  assert.equal(keyAction({ key: "x", target: { tagName: "BODY" } }), null);
});
