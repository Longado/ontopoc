import assert from "node:assert/strict";
import test from "node:test";

import { cardinalityLabel, cardinalityLine, fieldNote, formOf } from "./ontologyHandoverModel.js";

const ontology = { object_types: [{ key: "trip", label: "班次" }, { key: "route", label: "线路" }] };

test("a relation says which side is the many, in the objects' own names", () => {
  const rel = { from: "trip", to: "route", most_from: 1, most_to: 392 };
  assert.equal(cardinalityLabel(rel), "多对一");
  assert.equal(cardinalityLine(ontology, rel), "一个班次对应 1 个线路；一个线路最多对应 392 个班次");
  assert.equal(cardinalityLabel({ ...rel, most_from: 3, most_to: 1 }), "一对多");
  assert.equal(cardinalityLabel({ ...rel, most_from: 1, most_to: 1 }), "一对一");
  assert.equal(cardinalityLabel({ ...rel, most_from: 524, most_to: 20 }), "多对多");
});

test("a relation with nothing linked says so instead of claiming one-to-one", () => {
  assert.equal(cardinalityLabel({ from: "trip", to: "route", most_from: 0, most_to: 0 }), "没有连上");
});

test("a field's note says how much of it is empty, and says nothing when it is full", () => {
  assert.equal(fieldNote({ empty: 0, rows: 300 }), "");
  assert.equal(fieldNote({ empty: 13158, rows: 28653 }), "13158 / 28653 行是空的");
  assert.equal(fieldNote({ empty: 4, rows: 4, type: null }), "全是空的，看不出类型");
});

test("the form is read from the run, and a run from before the form existed has none", () => {
  const handover = { types: [{ type: "trip", fields: [] }], relations: [] };
  assert.equal(formOf({ evaluation: { handover } }), handover);
  assert.equal(formOf({ evaluation: {} }), null);
});
