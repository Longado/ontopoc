import assert from "node:assert/strict";
import test from "node:test";

import { KIND_LABEL, LAYERS, ageText, cameFromText, edgeLabel, groupLabel, sourceLines, stateTone } from "./graphModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("en");

test("the lineage speaks English: kinds, columns, ages, where a dataset came from", () => {
  assert.equal(KIND_LABEL.type, "Object type");
  assert.deepEqual(LAYERS.map((l) => l.label), ["Sources", "Datasets", "Pipelines", "Datasets (output)", "Object types", "Relations / actions / views", "Derived / answers"]);
  const now = Date.parse("2026-11-14T12:00:00Z");
  assert.equal(ageText("2026-11-14T11:59:40Z", now), "just now");
  assert.equal(ageText("2026-11-11T12:00:00Z", now), "3 d ago");
  assert.equal(cameFromText({ kind: "source", source: "Orders DB", table: "orders" }, true), "pulled from Orders DB, table orders");
  assert.equal(edgeLabel({ connected: 157, of: 160 }), "157 / 160 rows connected");
  assert.equal(groupLabel({ edges: [{}, {}] }), "2 relations");
  assert.deepEqual(sourceLines({ kind_label: "MySQL", status: "failed", status_label: "Failed", tables: [] }), [{ text: "MySQL, Failed", cause: true }, { text: "no tables read into datasets yet" }]);
});

test("a card's dot is green when confirmed, orange when it needs another look, red for a sent-back node or a failed source, grey otherwise", () => {
  assert.equal(stateTone({ kind: "type", state: "confirmed" }), "confirmed");
  assert.equal(stateTone({ kind: "view", state: "needs_look", stale: { label: "x" } }), "needs_look");
  assert.equal(stateTone({ kind: "relation", state: "rejected" }), "rejected");
  assert.equal(stateTone({ kind: "source", status: "failed" }), "rejected");
  assert.equal(stateTone({ kind: "dataset", state: null }), "none");
  assert.equal(stateTone({ kind: "type", state: "confirmed", model_draft: true }), "none");
});
