import assert from "node:assert/strict";
import test from "node:test";

import { layoutGraph } from "./ontologyGraphModel.js";

test("relation names sit toward the less connected end, so a hub's names do not pile up beside it", () => {
  const t = (key) => ({ key, label: key, populated_from: [], attributes: [] });
  const ontology = { object_types: ["hub", "a", "b", "c"].map(t), relations: ["a", "b", "c"].map((k) => ({ key: `hub_${k}`, from: "hub", to: k })) };
  const g = layoutGraph(ontology);
  const at = Object.fromEntries(g.nodes.map((n) => [n.key, n]));
  for (const e of g.edges) {
    const hub = at.hub.x + at.hub.w, leaf = at[e.to].x;
    assert.ok(Math.abs(e.lx - leaf) < Math.abs(e.lx - hub), `${e.key}: label at ${e.lx}, hub edge ${hub}, leaf ${leaf}`);
  }
});
