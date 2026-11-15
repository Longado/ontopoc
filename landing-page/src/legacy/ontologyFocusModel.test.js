import assert from "node:assert/strict";
import test from "node:test";

import { focusOntology, layoutGraph, needsFocus, rankByDegree } from "./ontologyGraphModel.js";

const t = (key) => ({ key, label: key.toUpperCase(), populated_from: [], attributes: [] });
const r = (key, from, to) => ({ key, from, to });
const ontology = { object_types: ["a", "b", "c", "d", "e"].map(t),
  relations: [r("ab", "a", "b"), r("ac", "a", "c"), r("bc", "b", "c"), r("de", "d", "e")] };

test("the most connected concept comes first", () => {
  assert.deepEqual(rankByDegree(ontology).map((x) => x.key), ["a", "b", "c", "d", "e"]);
});

test("focus keeps a concept, its neighbours and the relations among them", () => {
  const f = focusOntology(ontology, "a");
  assert.deepEqual(f.object_types.map((x) => x.key), ["a", "b", "c"]);
  assert.deepEqual(f.relations.map((x) => x.key), ["ab", "ac", "bc"]);
  assert.deepEqual(focusOntology(ontology, "a", ["d", "e"]).object_types.map((x) => x.key), ["d", "e"]);
});

test("focus is needed only when the whole graph does not fit the screen", () => {
  const small = layoutGraph(ontology);
  assert.equal(needsFocus(small, 900, 800), false);
  const many = { object_types: Array.from({ length: 40 }, (_, i) => t(`n${i}`)), relations: Array.from({ length: 39 }, (_, i) => r(`r${i}`, "n0", `n${i + 1}`)) };
  assert.equal(needsFocus(layoutGraph(many), 900, 800), true);
});
