// The two graphs as plain functions of what the service sends: where each node goes, what lights up when one is clicked, the words on an edge. No browser needed.
import { timeText } from "./format.js";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";

export const SIZE = {
  source: { w: 172, h: 64 },
  type: { w: 216, h: 80 },
  dataset: { w: 172, h: 64 },
  pipeline: { w: 172, h: 48 },
  relation: { w: 156, h: 48 },
  view: { w: 156, h: 48 },
  action: { w: 156, h: 48 },
  derived: { w: 156, h: 48 },
  answer: { w: 196, h: 48 },
};
const MARGIN = 40;

/** Where the types go in the relation graph: a force layout run to rest, so the same data always draws the same picture. Returns {positions: {id: {x, y, w, h}}, width, height}. */
export function forceLayout(nodes, edges) {
  const items = nodes.map((n) => ({ id: n.id }));
  const known = new Set(items.map((n) => n.id));
  const links = [...new Map(edges.filter((e) => known.has(e.from) && known.has(e.to) && e.from !== e.to).map((e) => [[e.from, e.to].sort().join("|"), { source: e.from, target: e.to }])).values()];
  const sim = forceSimulation(items)
    .force("charge", forceManyBody().strength(-500))
    .force("link", forceLink(links).id((d) => d.id).distance(340).strength(1))
    .force("collide", forceCollide(130))
    .force("x", forceX(0).strength(0.05))
    .force("y", forceY(0).strength(0.05))
    .stop();
  for (let i = 0; i < 320; i += 1) sim.tick();
  return place(items.map((n) => [n.id, { x: n.x, y: n.y, ...SIZE.type }]));
}

/** Shifts a set of centres so the picture starts at the margin, and returns the positions as top-left corners with the size of the whole. */
function place(centres) {
  const left = Math.min(...centres.map(([, c]) => c.x - c.w / 2), 0);
  const top = Math.min(...centres.map(([, c]) => c.y - c.h / 2), 0);
  const positions = Object.fromEntries(centres.map(([id, c]) => [id, { x: c.x - c.w / 2 - left + MARGIN, y: c.y - c.h / 2 - top + MARGIN, w: c.w, h: c.h }]));
  const right = Math.max(...Object.values(positions).map((p) => p.x + p.w), MARGIN);
  const bottom = Math.max(...Object.values(positions).map((p) => p.y + p.h), MARGIN);
  return { positions, width: right + MARGIN, height: bottom + MARGIN };
}

/** Where the nodes of the lineage go, left to right: a node sits one column after the furthest column of what it reads, and within a column the order follows where its
 * neighbours sit. Returns {positions, width, height} like forceLayout. */
export function layeredLayout(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const live = edges.filter((e) => ids.has(e.from) && ids.has(e.to) && e.from !== e.to);
  const layer = Object.fromEntries(nodes.map((n) => [n.id, 0]));
  for (let pass = 0; pass < nodes.length; pass += 1) {   // longest path; the pass limit keeps a cycle from running for ever
    let moved = false;
    for (const e of live) {
      if (layer[e.to] < layer[e.from] + 1) {
        layer[e.to] = layer[e.from] + 1;
        moved = true;
      }
    }
    if (!moved) break;
  }
  const columns = [];
  for (const n of [...nodes].sort((a, b) => a.name.localeCompare(b.name, "zh"))) (columns[layer[n.id]] ??= []).push(n);
  const filled = Array.from(columns, (c) => c ?? []);
  const row = Object.fromEntries(filled.flatMap((c) => c.map((n, i) => [n.id, i])));
  const around = (id, other) => {
    const near = live.filter((e) => (e.from === id && layer[e.to] === other) || (e.to === id && layer[e.from] === other)).map((e) => row[e.from === id ? e.to : e.from]);
    return near.length ? near.reduce((a, b) => a + b, 0) / near.length : row[id];
  };
  for (let sweep = 0; sweep < 4; sweep += 1) {   // each column ordered by the average place of its neighbours in the column before (then after)
    const order = sweep % 2 === 0 ? filled.keys() : [...filled.keys()].reverse();
    for (const i of order) {
      const other = sweep % 2 === 0 ? i - 1 : i + 1;
      if (other < 0 || other >= filled.length) continue;
      filled[i].sort((a, b) => around(a.id, other) - around(b.id, other) || a.name.localeCompare(b.name, "zh"));
      filled[i].forEach((n, k) => { row[n.id] = k; });
    }
  }
  const GAP = 18;
  const COLUMN = 252;
  const heights = filled.map((c) => c.reduce((sum, n) => sum + SIZE[n.kind].h + GAP, -GAP));
  const tallest = Math.max(...heights, 0);
  const centres = filled.flatMap((c, i) => {
    let y = (tallest - heights[i]) / 2;
    return c.map((n) => {
      const s = SIZE[n.kind];
      const centre = [n.id, { x: i * COLUMN + s.w / 2, y: y + s.h / 2, ...s }];
      y += s.h + GAP;
      return centre;
    });
  });
  return place(centres);
}

/** The ids lit when `id` is picked: it, and by `mode` what it reads ("up"), what reads it ("down") or both, followed as far as the edges go. */
export function lit(id, edges, mode = "both") {
  const out = new Set([id]);
  for (const [direction, from, to] of [["up", "to", "from"], ["down", "from", "to"]]) {
    if (mode !== "both" && mode !== direction) continue;
    const todo = [id];
    while (todo.length) {
      const at = todo.pop();
      for (const e of edges) {
        if (e[from] === at && !out.has(e[to])) {
          out.add(e[to]);
          todo.push(e[to]);
        }
      }
    }
  }
  return out;
}

/** The ids lit when `id` is picked, no further than `depth` edges away (null: as far as the edges go). */
export function litDepth(id, edges, mode = "both", depth = null) {
  if (depth == null) return lit(id, edges, mode);
  const out = new Set([id]);
  for (const [direction, from, to] of [["up", "to", "from"], ["down", "from", "to"]]) {
    if (mode !== "both" && mode !== direction) continue;
    let frontier = [id];
    for (let step = 0; step < depth && frontier.length; step += 1) {
      const next = [];
      for (const at of frontier) for (const e of edges) if (e[from] === at && !out.has(e[to])) { out.add(e[to]); next.push(e[to]); }
      frontier = next;
    }
  }
  return out;
}

/** The lineage's fixed columns, left to right: what each holds, with the words of its header. */
export const LAYERS = [
  { key: "source", label: "数据源" },
  { key: "dataset", label: "数据集" },
  { key: "pipeline", label: "管道" },
  { key: "written", label: "数据集（产出）" },
  { key: "type", label: "对象类型" },
  { key: "model", label: "关系 / 行为 / 视图" },
  { key: "derived", label: "派生 / 回答" },
];
const LAYER_OF = { source: 0, dataset: 1, pipeline: 2, type: 4, relation: 5, view: 5, action: 5, derived: 6, answer: 6 };

/** Where the nodes of the lineage go: each kind in its own column (a dataset a pipeline writes goes in the column after the pipelines), a header over each column that has
 * nodes, the columns packed left to right. Within a column the order follows where what it reads sits. Returns {positions, columns: [{key, label, x, w, count}], width, height, headerHeight}. */
export function lineageColumns(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const kind = Object.fromEntries(nodes.map((n) => [n.id, n.kind]));
  const live = edges.filter((e) => ids.has(e.from) && ids.has(e.to));
  const written = new Set(live.filter((e) => kind[e.from] === "pipeline" && kind[e.to] === "dataset").map((e) => e.to));
  const layerById = Object.fromEntries(nodes.map((n) => [n.id, n.kind === "dataset" && written.has(n.id) ? 3 : LAYER_OF[n.kind] ?? 6]));
  const byLayer = LAYERS.map(() => []);
  for (const n of [...nodes].sort((a, b) => a.name.localeCompare(b.name, "zh"))) byLayer[layerById[n.id]].push(n);
  const used = byLayer.map((list, layer) => ({ layer, list })).filter((c) => c.list.length);
  const row = {};
  used.forEach((c) => c.list.forEach((n, i) => { row[n.id] = i; }));
  for (let sweep = 0; sweep < 3; sweep += 1) {   // each column follows the average place of what it reads in the columns before it
    for (const { layer, list } of used) {
      const mean = (id) => {
        const near = live.filter((e) => e.to === id && layerById[e.from] < layer).map((e) => row[e.from]);
        return near.length ? near.reduce((a, b) => a + b, 0) / near.length : row[id];
      };
      list.sort((a, b) => mean(a.id) - mean(b.id) || a.name.localeCompare(b.name, "zh"));
      list.forEach((n, i) => { row[n.id] = i; });
    }
  }
  const GAP = 14;
  const COLUMN = 236;
  const HEADER = 44;
  const columns = used.map((c, i) => ({ key: LAYERS[c.layer].key, label: LAYERS[c.layer].label, x: MARGIN + i * COLUMN, w: COLUMN, count: c.list.length }));
  const positions = {};
  let tallest = MARGIN + HEADER;
  used.forEach((c, i) => {
    let y = MARGIN + HEADER;
    for (const n of c.list) {
      positions[n.id] = { x: columns[i].x, y, ...SIZE[n.kind] };
      y += SIZE[n.kind].h + GAP;
    }
    tallest = Math.max(tallest, y - GAP);
  });
  return { positions, columns, headerHeight: HEADER, width: MARGIN * 2 + used.length * COLUMN, height: tallest + MARGIN };
}

/** The picked node and the nodes one edge away from it: what the relation graph lights. */
export function neighbours(id, edges) {
  const out = new Set([id]);
  for (const e of edges) {
    if (e.from === id) out.add(e.to);
    if (e.to === id) out.add(e.from);
  }
  return out;
}

/** The relations between the same two types as one entry each: [{key, from, to, edges}]. The first relation gives the direction the line is drawn in. */
export function groupEdges(edges) {
  const groups = new Map();
  for (const e of edges) {
    const key = [e.from, e.to].sort().join("|");
    if (!groups.has(key)) groups.set(key, { key, from: e.from, to: e.to, edges: [] });
    groups.get(key).edges.push(e);
  }
  return [...groups.values()];
}

/** The point where the line from the centre of `box` towards `toward` leaves the box. */
export function leaves(box, toward) {
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;
  const dx = toward.x + toward.w / 2 - cx;
  const dy = toward.y + toward.h / 2 - cy;
  if (!dx && !dy) return { x: cx, y: cy };
  const scale = Math.min(dx ? box.w / 2 / Math.abs(dx) : Infinity, dy ? box.h / 2 / Math.abs(dy) : Infinity);
  return { x: cx + dx * scale, y: cy + dy * scale };
}

/** The label on a relation's line: how many rows of the many side find the one side. A person a row rule limits reads it of the rows they can see. */
export function edgeLabel(edge) {
  if (edge.connected == null) return "查不了";
  return `${edge.rows_limited ? "你能看到的 " : ""}连上 ${edge.connected} / ${edge.of} 行`;
}

/** The words that say whether the cardinality holds, for the drawer; "" when the check could not run. */
export function verdictText(edge) {
  if (edge.cardinality_ok == null) return edge.rows_limited ? "受行规则限制，只数了你能看到的行，不判断基数是否成立" : edge.problems?.join("；") ?? "";
  return edge.cardinality_ok ? `${edge.cardinality_label}成立` : `${edge.cardinality_label}不成立：${edge.cardinality_text}`;
}

/** "3 天前", "刚刚": how long ago an ISO time was. */
export function ageText(iso, now = Date.now()) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.floor((now - then) / 60000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} 小时前`;
  if (minutes < 60 * 24 * 60) return `${Math.floor(minutes / (60 * 24))} 天前`;
  return `${Math.floor(minutes / (60 * 24 * 30))} 个月前`;
}

/** Whether a node stays in full colour under the cause filter ("data", "definition" or "" for all) and the search words. */
export function shown(node, filter, query) {
  if (filter && node.stale?.root_cause !== filter) return false;
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [node.name, node.key, node.type_name, node.from_name, node.to_name].some((s) => String(s ?? "").toLowerCase().includes(q));
}

/** What the node says about itself when it needs another look: the cause in one word, and where it comes from. "" when it does not. */
export function causeLine(node) {
  const s = node.stale;
  if (!s) return "";
  return s.root ? `${s.label}：${s.root}` : s.label;
}

/** Who confirmed a node and on which data, in one sentence; "" when nobody has. */
export function confirmedText(node) {
  if (!node.confirmed_by) return "";
  const on = Object.entries(node.confirmed_on ?? {}).map(([name, v]) => `${name} 第 ${v} 版`).join("、");
  return `${node.confirmed_by} 于 ${timeText(node.confirmed_at)} 确认${on ? `，依据 ${on}` : ""}`;
}

export const KIND_LABEL = { source: "数据源", dataset: "数据集", pipeline: "管道", type: "对象类型", relation: "关系", view: "视图", action: "行为", derived: "派生属性", answer: "回答" };

/** Where the current version of a dataset came from, in a few words; "" when the service does not say. */
export function cameFromText(came, full = false) {
  if (!came) return "";
  if (came.kind === "upload") return "上传的";
  if (came.kind === "source") return came.source ? `从 ${came.source}${full ? ` 的表 ${came.table}` : ""} 拉取` : "从数据源拉取";
  if (came.kind === "pipeline") return came.pipeline ? `管道 ${came.pipeline} 写的` : "管道写的";
  if (came.kind === "action") return came.action ? `行为 ${came.action} 改过` : "行为改过";
  return "";
}

/** How a dataset's date is said: an upload (or a version whose origin was not recorded) was uploaded, the rest were updated. */
export const datedText = (came) => (!came || came.kind === "upload" || came.kind === "other" ? "上传于" : "更新于");

/** The two lines under a source's name: its kind and whether its last test or pull worked (a failure stands out), and what it fills. */
export function sourceLines(node) {
  const filled = node.tables?.length ?? 0;
  return [{ text: `${node.kind_label}，${node.status_label}`, ...(node.status === "failed" ? { cause: true } : {}) }, { text: filled ? `填 ${filled} 个数据集` : "还没有读进数据集的表" }];
}

/** `text` cut with "…" so it fits `maxPx` at font size `size`: a Chinese character is as wide as the size, a Latin one about 0.58 of it. */
export function fitText(text, maxPx, size) {
  const width = (ch) => (ch.charCodeAt(0) > 255 ? size : size * 0.58);
  const chars = [...String(text ?? "")];
  let used = 0;
  for (const [i, ch] of chars.entries()) {
    used += width(ch);
    if (used > maxPx) {
      let head = 0;
      let cut = i;
      while (cut > 0 && head + width("…") + chars.slice(0, cut).reduce((s, c) => s + width(c), 0) > maxPx) cut -= 1;
      return `${chars.slice(0, cut).join("")}…`;
    }
  }
  return chars.join("");
}
