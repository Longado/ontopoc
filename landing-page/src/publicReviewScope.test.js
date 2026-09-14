import assert from "node:assert/strict";
import test from "node:test";

import {
  ALIAS_VERDICTS, aliasDoubts, aliasKey, confirmOntology, emptyState, exportState, partExample, readyToConfirm,
  restoreState, restoreView, sharedModelYears, stepSelection, viewKey,
} from "./publicReviewModel.js";

const NOW = "2026-10-01T02:00:00.000Z";
const BRAKES = { type: "component", source: "complaints", value: "SERVICE BRAKES", target_source: "recalls", target_value: "SERVICE BRAKES, HYDRAULIC", records_linked: 34, reasoning: "r" };
const pack = (aliases = [BRAKES]) => ({
  dataset: { id: "nhtsa-demo" }, boundary: "b", run: { model: "m", matcher_prompt_version: "v3" },
  ontology: { hash: "e".repeat(64), value_aliases: aliases },
  recalls: [
    { id: "R1", series: "R1", mechanism: ["AIR BAGS:FRONTAL"], covered: ["DEMO EV 2022", "DEMO EUV 2022"], counts: { outside_all: 1 }, text_checked: true,
      candidates: [{ id: "C1", bucket: "outside_all" }, { id: "C2", bucket: "outside_all" }, { id: "C3", bucket: "inside_scope" }] },
    { id: "R2", series: "R2", mechanism: ["SEAT BELTS"], covered: ["DEMO EV 2019"], counts: { outside_all: 0 }, text_checked: false,
      candidates: [{ id: "C3", bucket: "inside_scope" }] },
  ],
  signals: {
    C1: { objects: ["DEMO EV 2022"], parts: ["AIR BAGS", "ELECTRICAL SYSTEM"] },
    C2: { objects: ["DEMO EV 2021"], parts: ["AIR BAGS"] },
    C3: { objects: ["DEMO EV 2019"], parts: ["SEAT BELTS"] },
  },
});

test("every name mapping needs an answer before review starts", () => {
  const key = aliasKey(BRAKES);
  assert.equal(key, "complaints|SERVICE BRAKES|SERVICE BRAKES, HYDRAULIC");
  assert.equal(readyToConfirm(pack(), {}), false);
  assert.equal(readyToConfirm(pack(), { [key]: "wrong" }), true);
  assert.equal(readyToConfirm(pack([]), {}), true);
  assert.deepEqual(Object.keys(ALIAS_VERDICTS), ["right", "wrong", "unsure"]);
});

test("confirming keeps each mapping answer, and a wrong answer is surfaced later", () => {
  const key = aliasKey(BRAKES);
  const before = emptyState(pack());
  const state = confirmOntology(before, NOW, { [key]: "wrong" });
  assert.equal(state.confirmed_at, NOW);
  assert.deepEqual(state.alias_checks, { [key]: "wrong" });
  assert.equal(before.alias_checks, undefined);
  assert.throws(() => confirmOntology(before, NOW, { [key]: "maybe" }), /对应/);
  assert.deepEqual(aliasDoubts(pack(), state).map((a) => [a.value, a.verdict]), [["SERVICE BRAKES", "wrong"]]);
  assert.deepEqual(aliasDoubts(pack(), confirmOntology(before, NOW, { [key]: "right" })), []);
});

test("mapping answers survive a reload and travel with the download", () => {
  const key = aliasKey(BRAKES);
  const state = confirmOntology(emptyState(pack()), NOW, { [key]: "unsure" });
  assert.deepEqual(restoreState(JSON.stringify(state), pack()).alias_checks, { [key]: "unsure" });
  assert.throws(() => restoreState(JSON.stringify({ ...state, alias_checks: { [key]: "maybe" } }), pack()));
  const out = exportState(pack(), state, NOW);
  assert.deepEqual(out.alias_checks, [{ source: "complaints", value: "SERVICE BRAKES", target_source: "recalls",
    target_value: "SERVICE BRAKES, HYDRAULIC", records_linked: 34, verdict: "unsure" }]);
  assert.equal(exportState(pack(), emptyState(pack()), NOW).alias_checks[0].verdict, null);
});

test("plain-language examples come from the data itself", () => {
  assert.deepEqual(partExample(pack()), { recall: "AIR BAGS:FRONTAL", complaint: "AIR BAGS", candidates: 3 });
  assert.equal(partExample({ ...pack(), recalls: [] }), null);
  assert.deepEqual(sharedModelYears(pack()), ["DEMO EV 2019", "DEMO EV 2022"]);
});

test("after a reload the page returns to the same tab, recall, list and complaint", () => {
  const p = pack();
  assert.match(viewKey(p), /^ontopoc\.public-review\.view\.e{16}$/);
  const saved = JSON.stringify({ tab: "review", recallId: "R1", bucket: "outside_all", selected: "C2" });
  assert.deepEqual(restoreView(saved, p, true), { tab: "review", recallId: "R1", bucket: "outside_all", selected: "C2" });
  assert.equal(restoreView(saved, p, false).tab, "ontology");
  assert.deepEqual(restoreView(null, p, true), { tab: "recalls", recallId: "R1", bucket: "outside_all", selected: "" });
  assert.deepEqual(restoreView("{broken", p, false), { tab: "ontology", recallId: "R1", bucket: "outside_all", selected: "" });
  const stale = JSON.stringify({ tab: "nowhere", recallId: "GONE", bucket: "odd", selected: 5 });
  assert.deepEqual(restoreView(stale, p, true), { tab: "recalls", recallId: "R1", bucket: "outside_all", selected: "" });
});

test("arrow keys step through the visible list and stop at the ends", () => {
  const visible = [{ id: "A" }, { id: "B" }, { id: "C" }];
  assert.equal(stepSelection("A", visible, 1), "B");
  assert.equal(stepSelection("C", visible, 1), "C");
  assert.equal(stepSelection("A", visible, -1), "A");
  assert.equal(stepSelection("gone", visible, 1), "A");
  assert.equal(stepSelection("A", [], 1), "");
});
