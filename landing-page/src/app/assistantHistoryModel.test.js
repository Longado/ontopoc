import assert from "node:assert/strict";
import test from "node:test";

import { MODES } from "./assistantModel.js";
import { draftAgain, filterByMode, filterModes, outcomeLine, pastTurn, railItems, scopeOf } from "./assistantHistoryModel.js";
import { groupByDay } from "./chatModel.js";

const at = (y, m, d, h = 10) => new Date(y, m - 1, d, h).toISOString();
const asks = [{ id: 1, question: "how many orders", asked_at: at(2026, 11, 16, 9), status: "answered" }];
const turns = [
  { id: 5, mode: "pipeline", message: "keep paid orders", asked_at: at(2026, 11, 16, 11), outcome: { state: "applied" } },
  { id: 6, mode: "query", message: "start order", asked_at: at(2026, 11, 15, 8), outcome: null },
  { id: 7, mode: "meanings", message: "what is state", asked_at: at(2026, 11, 16, 10) },
];

test("the rail shows Ask questions and builder turns together, grouped by day, each with its mode", () => {
  const groups = groupByDay(railItems(asks, turns), new Date(2026, 10, 16, 15));
  assert.deepEqual(groups.map((g) => [g.key, g.items.map((x) => [x.key, x.mode, x.turn])]), [
    ["today", [["t5", "pipeline", true], ["t7", "meanings", true], ["a1", "ask", false]]],
    ["yesterday", [["t6", "query", true]]],
  ]);
});

test("the same words in two modes are two items; in one mode they show once", () => {
  const items = railItems([{ id: 1, question: "x", asked_at: at(2026, 11, 16) }], [
    { id: 2, mode: "query", message: "x", asked_at: at(2026, 11, 16, 11) },
    { id: 3, mode: "query", message: "x", asked_at: at(2026, 11, 16, 12) },
  ]);
  assert.deepEqual(groupByDay(items, new Date(2026, 10, 16, 15))[0].items.map((x) => x.key), ["t3", "a1"]);
});

test("the filter offers the modes in MODES and any other mode a turn carries, and none when there is nothing to tell apart", () => {
  const items = railItems(asks, turns);
  assert.deepEqual(filterModes(items), [...MODES.filter((m) => ["ask", "query", "pipeline"].includes(m)), "meanings"]);
  assert.deepEqual(filterModes(railItems(asks, [])), []);
  assert.deepEqual(filterByMode(items, "pipeline").map((x) => x.key), ["t5"]);
  assert.deepEqual(filterByMode(items, "meanings").map((x) => x.key), ["t7"]);
  assert.equal(filterByMode(items, "").length, 4);
  assert.deepEqual(filterByMode(items, "ask").map((x) => x.key), ["a1"]);
});

test("Draft again gives back the same mode, message and scope, leaves out what is hidden, and carries nothing that runs", () => {
  const model = draftAgain({ mode: "model", message: "suggest types", scope: { datasets: [{ kind: "datasets", name: "orders" }, { kind: "datasets", hidden: true }] } });
  assert.deepEqual(model, { mode: "model", text: "suggest types", datasets: ["orders"], target: null, types: [] });
  const plan = draftAgain({ mode: "pipeline", message: "filter", scope: { target: { kind: "pipeline", name: "p1", label: "Orders pipeline" } } });
  assert.deepEqual(plan, { mode: "pipeline", text: "filter", datasets: [], target: { kind: "pipeline", name: "p1", label: "Orders pipeline" }, types: [] });
  assert.equal(draftAgain({ mode: "pipeline", message: "f", scope: { target: { kind: "dataset", hidden: true } } }).target, null);
  assert.deepEqual(draftAgain({ mode: "query", message: "start order", scope: {} }), { mode: "query", text: "start order", datasets: [], target: null, types: [] });
  assert.deepEqual(draftAgain({ mode: "meanings", message: "m", scope: { types: [{ kind: "types", name: "order" }, { kind: "types", hidden: true }] } }).types, ["order"]);
});

test("the scope kept with a turn is what the composer had", () => {
  assert.deepEqual(scopeOf("model", { chosen: ["a", "b"] }), { datasets: ["a", "b"] });
  assert.deepEqual(scopeOf("pipeline", { target: { kind: "dataset", name: "d" } }), { target: { kind: "dataset", name: "d", label: "d" } });
  assert.deepEqual(scopeOf("query"), {});
});

test("what happened next reads as applied, saved as a name, or nothing known", () => {
  assert.deepEqual(outcomeLine({ state: "saved", name: "orders_clean" }), { key: "saved", name: "orders_clean" });
  assert.deepEqual(outcomeLine({ state: "saved", name: "gone", hidden: true }), { key: "saved", name: "" });
  assert.equal(outcomeLine(null), null);
  assert.equal(pastTurn(4).kind, "past");
});
