import assert from "node:assert/strict";
import test from "node:test";

import { LEGEND, connectedMeaning, placeLabels } from "./graphModel.js";

const rects = (a, b) => !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);

test("relation labels sit clear of every type box and of each other (W3)", () => {
  const positions = { a: { x: 0, y: 0, w: 216, h: 80 }, b: { x: 600, y: 0, w: 216, h: 80 }, c: { x: 300, y: 0, w: 216, h: 80 }, d: { x: 300, y: 300, w: 216, h: 80 } };
  // a-b passes straight through c; a-d and b-d leave from the same sides; two labels want the same middle
  const groups = [{ key: "a|b", from: "a", to: "b", edges: [{ id: "r1" }] }, { key: "a|d", from: "a", to: "d", edges: [{ id: "r2" }] }, { key: "b|d", from: "b", to: "d", edges: [{ id: "r3" }] }, { key: "c|d", from: "c", to: "d", edges: [{ id: "r4" }] }];
  const widths = { "a|b": 110, "a|d": 110, "b|d": 110, "c|d": 110 };
  const placed = placeLabels(groups, positions, (g) => widths[g.key]);
  assert.deepEqual(Object.keys(placed).sort(), ["a|b", "a|d", "b|d", "c|d"]);
  const boxes = Object.entries(placed).map(([key, p]) => ({ key, x: p.x - widths[key] / 2, y: p.y - 11, w: widths[key], h: 22 }));
  for (const b of boxes) for (const node of Object.values(positions)) assert.equal(rects(b, node), false, `${b.key} covers a type`);
  for (const [i, x] of boxes.entries()) for (const y of boxes.slice(i + 1)) assert.equal(rects(x, y), false, `${x.key} covers ${y.key}`);
});

test("a label with room goes in the middle of its line", () => {
  const positions = { a: { x: 0, y: 0, w: 100, h: 50 }, b: { x: 500, y: 0, w: 100, h: 50 } };
  const placed = placeLabels([{ key: "a|b", from: "a", to: "b", edges: [{}] }], positions, () => 100);
  assert.deepEqual(placed["a|b"], { x: 300, y: 25 });
});

test("the legend names each colour and what 连上 157 / 161 行 counts", () => {
  assert.deepEqual(LEGEND.map((l) => l.word), ["已确认", "待确认", "需再看", "已退回"]);
  assert.match(connectedMeaning({ connected: 157, of: 161, from_name: "订单", to_name: "客户" }), /订单.*161 行.*157 行.*客户/);
  assert.equal(connectedMeaning({ connected: null }), "现在查不了");
});
