import assert from "node:assert/strict";
import test from "node:test";

import { cardFacts, centreOn, edgeTone, enrichNodes, kindCounts, mapLayout, minimapScale, searchMatches, traceSubgraph } from "./lineageModel.js";
import { setLocale } from "./i18n/index.js";

setLocale("en");

const node = (id, kind, extra = {}) => ({ id, kind, name: extra.name ?? id, ...extra });
const NODES = [
  node("source:db", "source", { name: "Orders DB", tables: [{ table: "orders", dataset: "Orders" }] }),
  node("dataset:Orders", "dataset", { name: "Orders" }),
  node("dataset:Tickets", "dataset", { name: "Tickets" }),
  node("pipeline:Totals", "pipeline", { name: "Totals", steps: [{ id: "o", type: "input" }, { id: "t", type: "input" }, { id: "j", type: "join" }, { id: "out", type: "output" }] }),
  node("dataset:Totals", "dataset", { name: "Totals (data)" }),
  node("objtype:order", "type", { name: "Order", objects: 160, properties: [{}, {}, {}] }),
  node("objtype:customer", "type", { name: "Customer" }),
  node("relation:oc", "relation", { name: "Order belongs to customer", type_name: "Order" }),
  node("objaction:mark", "action", { name: "Mark delivered", type_name: "Order" }),
];
const EDGES = [
  { from: "source:db", to: "dataset:Orders" },
  { from: "dataset:Orders", to: "pipeline:Totals" },
  { from: "dataset:Tickets", to: "pipeline:Totals" },
  { from: "pipeline:Totals", to: "dataset:Totals" },
  { from: "dataset:Orders", to: "objtype:order" },
  { from: "objtype:order", to: "relation:oc" },
  { from: "objtype:customer", to: "relation:oc" },
  { from: "objtype:order", to: "objaction:mark" },
];

test("the map goes left to right: source, dataset, pipeline, the dataset it writes, object type, then what stands on the types", () => {
  const { positions, columns } = mapLayout(NODES, EDGES);
  const x = (id) => positions[id].x;
  assert.ok(x("source:db") < x("dataset:Orders"));
  assert.ok(x("dataset:Orders") < x("pipeline:Totals"));
  assert.ok(x("pipeline:Totals") < x("dataset:Totals"));
  assert.ok(x("dataset:Totals") < x("objtype:order"));
  assert.ok(x("objtype:order") < x("relation:oc"));
  assert.ok(x("relation:oc") < x("objaction:mark"));
  assert.deepEqual(columns.map((c) => c.key), ["source", "dataset", "pipeline", "written", "type", "model", "derived"]);
  assert.deepEqual(columns.map((c) => c.count), [1, 2, 1, 1, 2, 1, 1]);
});

test("a pipeline is a group box as tall as its steps need; nothing in a column overlaps", () => {
  const { positions, width, height } = mapLayout(NODES, EDGES);
  assert.ok(positions["pipeline:Totals"].h > positions["dataset:Orders"].h + 3 * 20);
  const byX = {};
  for (const [id, p] of Object.entries(positions)) (byX[p.x] ??= []).push({ id, ...p });
  for (const column of Object.values(byX)) {
    column.sort((a, b) => a.y - b.y);
    column.slice(1).forEach((p, i) => assert.ok(p.y >= column[i].y + column[i].h, `${p.id} overlaps ${column[i].id}`));
  }
  assert.ok(width > 0 && height > 0);
  assert.deepEqual(mapLayout(NODES, EDGES).positions, positions, "the same data draws the same map");
});

test("tracing a node keeps its whole upstream and downstream chain and drops what is beside it", () => {
  const sub = traceSubgraph("dataset:Orders", NODES, EDGES);
  assert.deepEqual(sub.nodes.map((n) => n.id).sort(), ["dataset:Orders", "dataset:Totals", "objaction:mark", "objtype:order", "pipeline:Totals", "relation:oc", "source:db"]);
  assert.ok(sub.edges.every((e) => sub.nodes.some((n) => n.id === e.from) && sub.nodes.some((n) => n.id === e.to)));
  const up = traceSubgraph("objtype:order", NODES, EDGES);
  assert.ok(up.nodes.some((n) => n.id === "source:db"), "its source is upstream of the type");
  assert.ok(!up.nodes.some((n) => n.id === "dataset:Tickets"));
});

test("search matches a name, a kind or the object type a node stands on, names that start with the words first", () => {
  const kindOf = (n) => ({ type: "Object type", relation: "Relation", action: "Action", dataset: "Dataset", source: "Source", pipeline: "Pipeline" }[n.kind]);
  assert.deepEqual(searchMatches(NODES, "ord", kindOf).map((m) => m.id), ["objtype:order", "relation:oc", "dataset:Orders", "source:db", "objaction:mark"]);
  assert.deepEqual(searchMatches(NODES, "pipeline", kindOf).map((m) => m.id), ["pipeline:Totals"]);
  assert.deepEqual(searchMatches(NODES, "  ", kindOf), []);
  assert.equal(searchMatches(Array.from({ length: 30 }, (_, i) => node(`dataset:d${i}`, "dataset", { name: `d${i}` })), "d", kindOf).length, 8);
});

test("the node-type filter counts each kind", () => {
  assert.deepEqual(kindCounts(NODES), { source: 1, dataset: 3, pipeline: 1, type: 2, relation: 1, action: 1 });
});

test("a line is amber when either end needs another look, red when a source failed, else plain", () => {
  const byId = { a: { id: "a", kind: "dataset", stale: { label: "data changed" } }, b: { id: "b", kind: "type", state: "confirmed" }, c: { id: "c", kind: "source", status: "failed" }, d: { id: "d", kind: "type", state: "confirmed" } };
  assert.equal(edgeTone({ from: "a", to: "b" }, byId), "needs_look");
  assert.equal(edgeTone({ from: "c", to: "a" }, byId), "rejected");
  assert.equal(edgeTone({ from: "b", to: "d" }, byId), "ok");
});

test("the facts on a card: columns and rows of a dataset, objects and properties of a type, tables of a source", () => {
  const datasets = [{ name: "Orders", rows: 160, columns: 8 }];
  const [source, orders, order] = enrichNodes(NODES.filter((n) => ["dataset:Orders", "objtype:order", "source:db"].includes(n.id)), datasets, {});
  assert.deepEqual(cardFacts(orders).stats.map((s) => [s.key, s.value]), [["columns", "8"], ["rows", "160"]]);
  assert.deepEqual(cardFacts(order).stats.map((s) => [s.key, s.value]), [["objects", "160"], ["properties", "3"]]);
  assert.deepEqual(cardFacts(source).stats.map((s) => [s.key, s.value]), [["tables", "1"]]);
  assert.deepEqual(cardFacts({ ...orders, stale: { label: "Data changed" } }).note, "Needs review: Data changed");
  assert.deepEqual(cardFacts({ kind: "dataset", name: "x" }).stats, [], "a dataset nobody reported on has no numbers, not zeros");
});

test("enrichment puts the dataset's rows and columns and a pipeline's steps on the nodes, and leaves the rest alone", () => {
  const pipelines = { Totals: { spec: { steps: [{ id: "o", type: "input", dataset: "Orders" }, { id: "out", type: "output", name: "Totals" }] } } };
  const out = enrichNodes([node("dataset:Orders", "dataset", { name: "Orders", key: "Orders" }), node("pipeline:Totals", "pipeline", { name: "Totals", key: "Totals" }), node("objtype:x", "type")],
    [{ name: "Orders", rows: 5, columns: 2 }], pipelines);
  assert.deepEqual([out[0].rows, out[0].columns], [5, 2]);
  assert.deepEqual(out[1].steps.map((s) => s.id), ["o", "out"]);
  assert.equal(out[2].rows, undefined);
});

test("centreOn puts a box in the middle of the frame at the given zoom", () => {
  assert.deepEqual(centreOn({ w: 1000, h: 600 }, { x: 400, y: 200, w: 200, h: 100 }, 1), { k: 1, x: 0, y: 50 });
  assert.deepEqual(centreOn({ w: 1000, h: 600 }, { x: 0, y: 0, w: 200, h: 100 }, 0.5), { k: 0.5, x: 450, y: 275 });
});

test("the minimap scales the whole map into its box, keeping the shape", () => {
  const s = minimapScale({ width: 2000, height: 500 }, { w: 200, h: 120 });
  assert.equal(s.k, 0.1);
  assert.deepEqual([s.w, s.h], [200, 50]);
});
