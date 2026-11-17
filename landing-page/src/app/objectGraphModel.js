import { t } from "./i18n/index.js";

/** SELECT GRAPH answers: the objects a query drew and how they are related, laid out from the start objects (first column) a step at a time. */

export const OBJECT_BOX = { w: 176, h: 48 };
const COLUMN = 250;
const GAP = 12;

/** {boxes: {id: {x, y, w, h}}, width, height}: each object in the column of its fewest steps from a start object, along the edges either way (a ticket that
 * points at an order is one step from it all the same); in a column, objects are ordered by where their neighbours in the column before stand. */
export function objectGraphLayout(graph) {
  const nodes = graph.nodes ?? [];
  const next = new Map(nodes.map((n) => [n.id, []]));
  for (const e of graph.edges ?? []) {
    if (!next.has(e.from) || !next.has(e.to)) continue;
    next.get(e.from).push(e.to);
    next.get(e.to).push(e.from);
  }
  const depth = new Map();
  let frontier = nodes.filter((n) => n.start).map((n) => n.id);
  frontier.forEach((id) => depth.set(id, 0));
  for (let d = 1; frontier.length; d += 1) {
    const reached = [];
    for (const id of frontier) for (const other of next.get(id)) if (!depth.has(other)) { depth.set(other, d); reached.push(other); }
    frontier = reached;
  }
  for (const n of nodes) if (!depth.has(n.id)) depth.set(n.id, 0);   // not reached from a start object: shown with them rather than lost
  const columns = [];
  for (const n of nodes) (columns[depth.get(n.id)] ??= []).push(n);
  const filled = Array.from(columns, (c) => c ?? []);
  const row = new Map();
  filled.forEach((column, i) => {
    if (i > 0) {
      const place = (n) => {
        const near = next.get(n.id).filter((o) => depth.get(o) === i - 1).map((o) => row.get(o));
        return near.length ? near.reduce((a, b) => a + b, 0) / near.length : Infinity;
      };
      column.sort((a, b) => place(a) - place(b));
    }
    column.forEach((n, k) => row.set(n.id, k));
  });
  const heights = filled.map((c) => c.length * (OBJECT_BOX.h + GAP) - GAP);
  const tallest = Math.max(0, ...heights);
  const boxes = {};
  filled.forEach((column, i) => column.forEach((n, k) => {
    boxes[n.id] = { x: i * COLUMN, y: (tallest - heights[i]) / 2 + k * (OBJECT_BOX.h + GAP), ...OBJECT_BOX };
  }));
  return { boxes, width: Math.max(OBJECT_BOX.w, (filled.length - 1) * COLUMN + OBJECT_BOX.w), height: Math.max(OBJECT_BOX.h, tallest) };
}

/** The two lines on a node: its name, then its type and key; or its key, then its type, when it has no name to show. */
export const nodeLines = (n) => (n.name ? [n.name, `${n.type_name} ${n.key}`] : [n.key, n.type_name]);

/** The line under a graph answer: how many start objects are drawn, and the objects they reach. */
export function graphNote(g) {
  const reached = g.nodes.length - g.nodes.filter((n) => n.start).length;
  const head = t(g.shown < g.starts ? "objects.graph.head.some" : "objects.graph.head.all", { shown: g.shown });
  return t("objects.graph.note", { head, count: reached, cut: g.cut ? t("objects.graph.cut") : "" });
}
