import assert from "node:assert/strict";
import test from "node:test";

import { SIZE, ageText, causeLine, edgeLabel, fitText, forceLayout, groupEdges, layeredLayout, leaves, lit, neighbours, shown, verdictText } from "./graphModel.js";

const node = (id, kind, name = id, extra = {}) => ({ id, kind, name, ...extra });
const LINEAGE = {
  nodes: [node("dataset:订单", "dataset"), node("objtype:order", "type", "订单"), node("objview:有效", "view", "有效订单"), node("relation:r", "relation", "订单属于客户", { from_name: "订单", to_name: "客户" }),
    node("objtype:customer", "type", "客户"), node("dataset:客户", "dataset"), node("answer:1", "answer", "取消的订单有多少")],
  edges: [{ from: "dataset:订单", to: "objtype:order" }, { from: "objtype:order", to: "objview:有效" }, { from: "objtype:order", to: "relation:r" }, { from: "objtype:customer", to: "relation:r" },
    { from: "dataset:客户", to: "objtype:customer" }, { from: "objview:有效", to: "answer:1" }],
};

test("a node sits one column after the furthest thing it reads, left to right, and nothing overlaps", () => {
  const { positions, width, height } = layeredLayout(LINEAGE.nodes, LINEAGE.edges);
  const column = (id) => Math.round(positions[id].x / 252);
  assert.deepEqual(["dataset:订单", "objtype:order", "objview:有效", "answer:1"].map(column), [0, 1, 2, 3]);
  assert.equal(column("relation:r"), 2);
  assert.equal(column("dataset:客户"), 0);
  const boxes = Object.values(positions);
  for (const [i, a] of boxes.entries()) {
    for (const b of boxes.slice(i + 1)) assert.ok(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y, "two nodes overlap");
  }
  assert.ok(boxes.every((b) => b.x >= 0 && b.y >= 0 && b.x + b.w <= width && b.y + b.h <= height));
  assert.deepEqual(positions["dataset:订单"].w, SIZE.dataset.w);
});

test("a cycle in the edges does not make the layout run for ever", () => {
  const nodes = [node("a", "type"), node("b", "type")];
  const { positions } = layeredLayout(nodes, [{ from: "a", to: "b" }, { from: "b", to: "a" }]);
  assert.equal(Object.keys(positions).length, 2);
});

test("the force layout gives every type a place of its own, the same on every run, and keeps linked types close", () => {
  const nodes = ["a", "b", "c", "d"].map((id) => node(id, "type"));
  const edges = [{ from: "a", to: "b" }, { from: "b", to: "c" }];
  const first = forceLayout(nodes, edges);
  assert.deepEqual(forceLayout(nodes, edges).positions, first.positions);
  const p = first.positions;
  const gap = (x, y) => Math.hypot(p[x].x - p[y].x, p[x].y - p[y].y);
  assert.ok(gap("a", "b") < 420 && gap("b", "c") < 420, "linked types are drawn close");
  const boxes = Object.values(p);
  for (const [i, a] of boxes.entries()) {
    for (const b of boxes.slice(i + 1)) assert.ok(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y, "two types overlap");
  }
  assert.deepEqual(forceLayout([node("only", "type")], []).positions.only.w, SIZE.type.w);
});

test("clicking a node lights what it reads, what reads it, or both, as far as the edges go", () => {
  const ids = (mode) => [...lit("objtype:order", LINEAGE.edges, mode)].sort();
  assert.deepEqual(ids("up"), ["dataset:订单", "objtype:order"]);
  assert.deepEqual(ids("down"), ["answer:1", "objtype:order", "objview:有效", "relation:r"]);
  assert.deepEqual(ids("both"), ["answer:1", "dataset:订单", "objtype:order", "objview:有效", "relation:r"]);
  assert.deepEqual([...neighbours("objtype:order", [{ from: "objtype:order", to: "objtype:customer" }, { from: "objtype:x", to: "objtype:order" }, { from: "objtype:y", to: "objtype:z" }])].sort(), ["objtype:customer", "objtype:order", "objtype:x"]);
});

test("relations between the same two types are one line, whichever way each points", () => {
  const edges = [{ id: "1", from: "a", to: "b" }, { id: "2", from: "b", to: "a" }, { id: "3", from: "a", to: "c" }];
  const groups = groupEdges(edges);
  assert.deepEqual(groups.map((g) => [g.from, g.to, g.edges.map((e) => e.id)]), [["a", "b", ["1", "2"]], ["a", "c", ["3"]]]);
});

test("a line leaves a box at its border, towards the other box", () => {
  const a = { x: 0, y: 0, w: 100, h: 50 };
  assert.deepEqual(leaves(a, { x: 300, y: 0, w: 100, h: 50 }), { x: 100, y: 25 });
  assert.deepEqual(leaves(a, { x: 0, y: 200, w: 100, h: 50 }), { x: 50, y: 50 });
});

test("an edge says how many rows connect, of the rows a limited person can see when a row rule limits them, and says when the cardinality fails", () => {
  const edge = { connected: 157, of: 160, rows_limited: false, cardinality_ok: false, cardinality_label: "多对一", cardinality_text: "客户 里“客户编号”有 1 个值重复", problems: [] };
  assert.equal(edgeLabel(edge), "连上 157 / 160 行");
  assert.equal(edgeLabel({ ...edge, rows_limited: true, of: 16, connected: 14 }), "你能看到的 连上 14 / 16 行");
  assert.equal(edgeLabel({ connected: null, problems: ["x"] }), "查不了");
  assert.equal(verdictText(edge), "多对一不成立：客户 里“客户编号”有 1 个值重复");
  assert.equal(verdictText({ ...edge, cardinality_ok: true }), "多对一成立");
  assert.equal(verdictText({ cardinality_ok: null, problems: ["对象类型“x”已经不在了"] }), "对象类型“x”已经不在了");
  assert.match(verdictText({ ...edge, rows_limited: true, cardinality_ok: null, cardinality_text: null }), /不判断基数/);   // a slice of the rows is no verdict
});

test("how long ago a version was uploaded reads in the biggest whole unit", () => {
  const now = Date.parse("2026-11-14T12:00:00Z");
  assert.equal(ageText("2026-11-14T11:59:40Z", now), "刚刚");
  assert.equal(ageText("2026-11-14T11:15:00Z", now), "45 分钟前");
  assert.equal(ageText("2026-11-14T07:00:00Z", now), "5 小时前");
  assert.equal(ageText("2026-11-11T12:00:00Z", now), "3 天前");
  assert.equal(ageText("2026-06-01T12:00:00Z", now), "5 个月前");
  assert.equal(ageText("nonsense", now), "");
});

test("the cause filter and the search keep the nodes they match, and a node that needs a look says its cause in words", () => {
  const stale = node("objtype:order", "type", "订单", { stale: { label: "上一步过时", root: "“状态码”的含义", root_cause: "data" } });
  const edited = node("objtype:c", "type", "客户", { stale: { label: "定义改了", root: null, root_cause: "definition" } });
  const fine = node("objtype:d", "type", "产品", { stale: null });
  assert.deepEqual([stale, edited, fine].map((n) => shown(n, "data", "")), [true, false, false]);
  assert.deepEqual([stale, edited, fine].map((n) => shown(n, "definition", "")), [false, true, false]);
  assert.deepEqual([stale, edited, fine].map((n) => shown(n, "", " 客")), [false, true, false]);
  assert.equal(shown(node("relation:r", "relation", "订单属于客户", { from_name: "订单", to_name: "客户" }), "", "客户"), true);
  const own = node("objtype:order", "type", "订单", { stale: { cause: "data", label: "数据变了", root: "“状态码”的含义", root_cause: "data", short: "订单 第 2 版 状态码 取值变了" } });
  assert.equal(shown(own, "data", ""), true);   // a type whose own data moved is in the 数据变了 filter
  assert.equal(shown(own, "definition", ""), false);
  assert.equal(causeLine(stale), "上一步过时：“状态码”的含义");
  assert.equal(causeLine(edited), "定义改了");
  assert.equal(causeLine(fine), "");
});

test("a name too wide for its box is cut with an ellipsis and a short one is left alone", () => {
  assert.equal(fitText("订单", 100, 14), "订单");
  assert.equal(fitText("订单属于客户的关系名称很长很长很长", 100, 14), "订单属于客户…");
  assert.equal(fitText("order_customer_relation", 60, 12).endsWith("…"), true);
  assert.equal(fitText("", 60, 12), "");
  const cut = fitText("订单属于客户的关系名称很长很长很长", 100, 14);
  assert.ok([...cut].length * 14 <= 100 + 14);
});
