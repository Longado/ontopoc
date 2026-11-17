// The two graphs as plain functions of what the service sends: where each node goes, what lights up when one is clicked, the words on an edge. No browser needed.
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";
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

/** The lineage draws every node as the same card (a column of mixed shapes reads as noise). The relation graph keeps SIZE. */
export const LINEAGE_SIZE = { w: 220, h: 56 };

/** The chip colour and the icon of each kind of node (a 24-unit line icon): the same in the graph, the legend and the panel. */
export const KIND_STYLE = {
  source: { colour: "#7961db", icon: "M9 3v5M15 3v5M6 8h12v3a6 6 0 01-12 0zM12 17v4" },
  dataset: { colour: "#238551", icon: "M4 5h16v14H4zM4 10h16M4 15h16M10 5v14" },
  pipeline: { colour: "#00a396", icon: "M3 6h5v5H3zM16 13h5v5h-5zM8 8.5h4a2 2 0 012 2V13" },
  type: { colour: "#2d72d2", icon: "M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5" },
  relation: { colour: "#9d3f9d", icon: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3A4 4 0 0011 18.7l1-1" },
  view: { colour: "#5f6b7c", icon: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6" },
  action: { colour: "#c87619", icon: "M13 3L5 14h6l-1 7 8-11h-6z" },
  derived: { colour: "#d1980b", icon: "M18 5H7l6 7-6 7h11" },
  answer: { colour: "#738091", icon: "M4 5h16v11H9l-5 4z" },
};
/** The colour of a node's state dot and left bar (never the only sign: the state word is on the card's tooltip, in the panel and in the legend). */
export const STATE_COLOUR = { confirmed: "#238551", needs_look: "#c87619", rejected: "#cd4246", none: "#8f99a8" };
/** Which of the four state colours a node shows: its state, a failed source is a failure, anything unconfirmed or stateless is grey. */
export function stateTone(node) {
  if (node.status === "failed") return "rejected";
  if (node.model_draft) return "none";
  if (node.stale || node.state === "needs_look") return "needs_look";
  return node.state === "confirmed" || node.state === "rejected" ? node.state : "none";
}

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
export const LAYERS = ["source", "dataset", "pipeline", "written", "type", "model", "derived"].map((key) => ({ key, get label() { return t(`lineage.layer.${key}`); } }));
const LAYER_OF = { source: 0, dataset: 1, pipeline: 2, type: 4, relation: 5, view: 5, action: 5, derived: 6, answer: 6 };

/** Where the nodes of the lineage go: each kind in its own column (a dataset a pipeline writes goes in the column after the pipelines), the columns packed left to right with no
 * gap between them (the page paints each as a band), every node a LINEAGE_SIZE card inset in its column. The header over each column is drawn by the page, as a sticky strip,
 * so the graph starts at `TOP`. Within a column the order follows where what it reads sits. Returns {positions, columns: [{key, label, x, w, count}], width, height}. */
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
  const GAP = 12;
  const INSET = 16;
  const COLUMN = LINEAGE_SIZE.w + INSET * 2;
  const TOP = 20;
  const columns = used.map((c, i) => ({ key: LAYERS[c.layer].key, get label() { return LAYERS[c.layer].label; }, x: i * COLUMN, w: COLUMN, count: c.list.length }));
  const positions = {};
  let tallest = TOP;
  used.forEach((c, i) => {
    let y = TOP;
    for (const n of c.list) {
      positions[n.id] = { x: columns[i].x + INSET, y, ...LINEAGE_SIZE };
      y += LINEAGE_SIZE.h + GAP;
    }
    tallest = Math.max(tallest, y - GAP);
  });
  return { positions, columns, width: used.length * COLUMN, height: tallest + TOP };
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
  if (edge.connected == null) return t("lineage.edge.unknown");
  return t(edge.rows_limited ? "lineage.edge.connected_limited" : "lineage.edge.connected", { connected: edge.connected, of: edge.of });
}

/** What the colours of the relation graph mean: the word is the state chip's, the colour the line's and the box's. */
export const LEGEND = [
  { key: "confirmed", colour: "#2b7a4b" },
  { key: "proposed", colour: "#6b6b66" },
  { key: "needs_look", colour: "#a35f00" },
  { key: "rejected", colour: "#a8271a" },
].map((l) => ({ ...l, get word() { return t(`lineage.legend.${l.key}.word`); }, get text() { return t(`lineage.legend.${l.key}.text`); } }));

/** What "连上 157 / 161 行" counts, in a sentence for the legend and the drawer: of the rows on the many side, how many find a row on the one side. */
export function connectedMeaning(edge) {
  if (edge.connected == null) return t("lineage.edge.meaning_unknown");
  const found = t("lineage.edge.meaning", { from: edge.from_name, of: edge.of, connected: edge.connected, to: edge.to_name });
  return edge.of > edge.connected ? `${found}${t("lineage.edge.meaning_missing", { missing: edge.of - edge.connected })}` : found;
}

/** The text on a relation's line: how many rows connect, or how many relations there are between the two types. */
export const groupLabel = (group) => (group.edges.length > 1 ? t("lineage.edge.relations", { count: group.edges.length }) : edgeLabel(group.edges[0]));

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
  if (edge.cardinality_ok == null) return edge.rows_limited ? t("lineage.edge.verdict_limited") : edge.problems?.join(t("lineage.list.separator")) ?? "";
  return edge.cardinality_ok ? t("lineage.edge.holds", { cardinality: edge.cardinality_label }) : t("lineage.edge.fails", { cardinality: edge.cardinality_label, text: edge.cardinality_text });
}

/** "3 d ago", "just now": how long ago an ISO time was, in the biggest whole unit. */
export function ageText(iso, now = Date.now()) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.floor((now - then) / 60000));
  if (minutes < 1) return t("lineage.age.now");
  if (minutes < 60) return t("lineage.age.minutes", { count: minutes });
  if (minutes < 60 * 24) return t("lineage.age.hours", { count: Math.floor(minutes / 60) });
  if (minutes < 60 * 24 * 60) return t("lineage.age.days", { count: Math.floor(minutes / (60 * 24)) });
  return t("lineage.age.months", { count: Math.floor(minutes / (60 * 24 * 30)) });
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
  return s.root ? t("lineage.cause", { label: s.label, root: s.root }) : s.label;
}

/** Who confirmed a node and on which data, in one sentence; "" when nobody has. */
export function confirmedText(node) {
  if (!node.confirmed_by) return "";
  const on = Object.entries(node.confirmed_on ?? {}).map(([name, v]) => t("lineage.version_of", { name, version: v })).join(t("lineage.list.separator"));
  return t(on ? "lineage.confirmed_on" : "lineage.confirmed", { who: node.confirmed_by, time: timeText(node.confirmed_at), on });
}

export const KIND_LABEL = Object.fromEntries(Object.keys(KIND_STYLE).map((kind) => [kind, undefined]));
for (const kind of Object.keys(KIND_LABEL)) Object.defineProperty(KIND_LABEL, kind, { enumerable: true, get: () => t(`lineage.kind.${kind}`) });

/** Where the current version of a dataset came from, in a few words; "" when the service does not say. */
export function cameFromText(came, full = false) {
  if (!came) return "";
  if (came.kind === "upload") return t("lineage.came.upload");
  if (came.kind === "source") return came.source ? t(full ? "lineage.came.source_table" : "lineage.came.source", { source: came.source, table: came.table }) : t("lineage.came.source_unnamed");
  if (came.kind === "pipeline") return came.pipeline ? t("lineage.came.pipeline", { name: came.pipeline }) : t("lineage.came.pipeline_unnamed");
  if (came.kind === "action") return came.action ? t("lineage.came.action", { name: came.action }) : t("lineage.came.action_unnamed");
  return "";
}

/** How a dataset's date is said: an upload (or a version whose origin was not recorded) was uploaded, the rest were updated. */
export const datedText = (came) => (!came || came.kind === "upload" || came.kind === "other" ? t("lineage.dated.uploaded") : t("lineage.dated.updated"));

/** The two lines under a source's name: its kind and whether its last test or pull worked (a failure stands out), and what it fills. */
export function sourceLines(node) {
  const filled = node.tables?.length ?? 0;
  return [{ text: t("lineage.source.line", { kind: node.kind_label, status: node.status_label }), ...(node.status === "failed" ? { cause: true } : {}) }, { text: filled ? t("lineage.source.fills", { count: filled }) : t("lineage.source.empty") }];
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

const READABLE_FLOOR = 0.7;   // below this the text of a card is too small to read: the picture is cut off at the edge and the reader drags for the rest
/** Where the picture sits in its frame. "all" shows the whole of it, centred, never larger than life. "readable" (the lineage) fits the whole picture but never zooms in past 100% or out past
 * 70%, keeps `content.top` pixels clear for the sticky column header, centres what fits and starts at the left edge what does not. */
export function fitView(frame, content, mode = "all") {
  if (mode === "width") return { k: Math.min(frame.w / content.width, 1.5), x: 0, y: 44 };   // the old lineage fit, kept for its test: fill the width, up to 150%
  if (mode === "readable") {
    const top = content.top ?? 0;
    const k = Math.min(1, Math.max(READABLE_FLOOR, Math.min(frame.w / content.width, (frame.h - top) / content.height)));
    return { k, x: Math.max(0, (frame.w - content.width * k) / 2), y: top };
  }
  const k = Math.min(frame.w / content.width, frame.h / content.height, 1);
  return { k, x: (frame.w - content.width * k) / 2, y: (frame.h - content.height * k) / 2 };
}
