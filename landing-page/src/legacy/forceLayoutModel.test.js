import assert from "node:assert/strict";
import test from "node:test";

import { edgePath, forceLayout, moveNode } from "./forceLayoutModel.js";

const items = ["客户", "订单", "订单明细", "产品", "员工", "承运商", "供应商", "产品类别"].map((label, i) => ({ id: `t${i}`, label }));
const links = [["t1", "t0"], ["t1", "t2"], ["t2", "t3"], ["t1", "t4"], ["t1", "t5"], ["t3", "t6"], ["t3", "t7"]].map(([from, to]) => ({ from, to }));

const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

test("the layout places every object inside the canvas without two boxes on top of each other", () => {
  const g = forceLayout(items, links);
  assert.equal(g.nodes.length, items.length);
  for (const n of g.nodes) {
    assert.ok(n.x >= 0 && n.y >= 0 && n.x + n.w <= g.width && n.y + n.h <= g.height, n.label);
    assert.ok(n.w >= [...n.label].length * 12, "the box fits its name");
  }
  for (let i = 0; i < g.nodes.length; i++) for (let j = i + 1; j < g.nodes.length; j++) assert.ok(!overlap(g.nodes[i], g.nodes[j]), `${g.nodes[i].label} / ${g.nodes[j].label}`);
});

test("connected objects end up nearer each other than objects with nothing between them", () => {
  const g = forceLayout(items, links);
  const at = Object.fromEntries(g.nodes.map((n) => [n.id, [n.x + n.w / 2, n.y + n.h / 2]]));
  const d = (a, b) => Math.hypot(at[a][0] - at[b][0], at[a][1] - at[b][1]);
  const linked = links.map((l) => d(l.from, l.to));
  const apart = [["t0", "t7"], ["t4", "t6"], ["t5", "t7"]].map(([a, b]) => d(a, b));
  assert.ok(Math.max(...linked) < Math.min(...apart) * 1.2, `${Math.max(...linked)} vs ${Math.min(...apart)}`);
});

test("a line runs from box edge to box edge, and a dragged box takes its lines with it", () => {
  const a = { x: 0, y: 0, w: 100, h: 40 }, b = { x: 300, y: 0, w: 100, h: 40 };
  const e = edgePath(a, b, 0);
  assert.match(e.path, /^M100,20 /);   // leaves a's right edge at mid height
  assert.ok(e.path.endsWith("300,20"));
  const g = moveNode({ nodes: [{ id: "a", ...a }, { id: "b", ...b }], width: 400, height: 40 }, "b", 0, 100);
  assert.deepEqual(g.nodes[1], { id: "b", x: 300, y: 100, w: 100, h: 40 });
  assert.ok(g.height >= 140);   // the canvas grows to hold it
});
