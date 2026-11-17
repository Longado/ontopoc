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

/** What the colours of the relation graph mean: the word is the state chip's, the colour the line's and the box's. */
export const LEGEND = [
  { word: "已确认", key: "confirmed", colour: "#2b7a4b", text: "有人看过，按当时的数据确认了" },
  { word: "待确认", key: "proposed", colour: "#6b6b66", text: "刚提出，等另一位建设者确认" },
  { word: "需再看", key: "needs_look", colour: "#a35f00", text: "确认之后数据变了，要再看一次" },
  { word: "已退回", key: "rejected", colour: "#a8271a", text: "被退回了，改好再提" },
];

/** What "连上 157 / 161 行" counts, in a sentence for the legend and the drawer: of the rows on the many side, how many find a row on the one side. */
export function connectedMeaning(edge) {
  if (edge.connected == null) return "现在查不了";
  return `${edge.from_name}一共 ${edge.of} 行，其中 ${edge.connected} 行在${edge.to_name}里找到了对应的一行${edge.of > edge.connected ? `；还有 ${edge.of - edge.connected} 行找不到` : ""}`;
}

/** The text on a relation's line: how many rows connect, or how many relations there are between the two types. */
export const groupLabel = (group) => (group.edges.length > 1 ? `${group.edges.length} 个关系` : edgeLabel(group.edges[0]));

/** The width of a label's pill: a character is about 12 wide, with room at the ends. */
export const labelWidth = (label) => Math.max(56, [...label].length * 12 + 16);

const overlaps = (a, b) => !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);

/** Where each line's label goes ({key: {x, y}}, the centre of the label): in the middle of the line when that is clear, else the nearest place along it or beside it
 * that covers no type box and no label placed before it. `widthOf(group)` is the label's width; it is 22 high. */
export function placeLabels(groups, positions, widthOf) {
  const nodes = Object.values(positions).map((p) => ({ x: p.x - 4, y: p.y - 4, w: p.w + 8, h: p.h + 8 }));
  const placed = {};
  const taken = [];
  const ts = [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8];
  const offsets = [0, 30, -30, 60, -60, 90, -90, 120, -120, 160, -160];
  for (const g of groups) {
    const from = positions[g.from];
    const to = positions[g.to];
    const a = leaves(from, to);
    const b = leaves(to, from);
    const w = widthOf(g);
    const length = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const normal = { x: -(b.y - a.y) / length, y: (b.x - a.x) / length };
    let spot = null;
    search: for (const offset of offsets) {
      for (const t of ts) {
        const x = a.x + (b.x - a.x) * t + normal.x * offset;
        const y = a.y + (b.y - a.y) * t + normal.y * offset;
        const box = { x: x - w / 2, y: y - 11, w, h: 22 };
        if (!nodes.some((n) => overlaps(box, n)) && !taken.some((o) => overlaps(box, o))) {
          spot = { x, y, box };
          break search;
        }
      }
    }
    const at = spot ?? { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, box: { x: (a.x + b.x) / 2 - w / 2, y: (a.y + b.y) / 2 - 11, w, h: 22 } };
    placed[g.key] = { x: at.x, y: at.y };
    taken.push({ ...at.box, x: at.box.x - 2, w: at.box.w + 4 });
  }
  return placed;
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
