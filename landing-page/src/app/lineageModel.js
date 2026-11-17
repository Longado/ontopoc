// The lineage as a twin-view map, as plain functions: where each card and each pipeline group goes, what a trace keeps, what a search finds, what a card says. No browser needed.
import { KIND_STYLE, litDepth, stateTone } from "./graphModel.js";
import { formatNumber, t } from "./i18n/index.js";
import { statusOf } from "./statusModel.js";

/** The header colour and icon of each kind on the map: graphModel's (datasets green, pipelines teal, object types blue, actions orange, as in DIP). */
export const TWIN_STYLE = KIND_STYLE;
export const TWIN_KINDS = Object.keys(TWIN_STYLE);

export const CARD = { w: 192, h: 64 };
export const GROUP = { head: 30, step: 24, pad: 10 };
const GAP = 14;
const COLUMN_GAP = 44;
const TOP = 44;   // room above the first card for the column headings
const MARGIN = 16;
/** The map's columns, left to right. The last two: what the types are tied together and viewed by, then what is worked out from them or done with them. */
const LAYERS = ["source", "dataset", "pipeline", "written", "type", "model", "derived"].map((key) => ({ key, get label() { return t(`lineage.twin.layer.${key}`); } }));
const LAYER_OF = { source: 0, dataset: 1, pipeline: 2, type: 4, relation: 5, view: 5, derived: 6, action: 6, answer: 6 };

/** The size of a node's box: a card, or for a pipeline a group box with a row for each of its steps. */
export function sizeOf(node) {
  if (node.kind === "pipeline" && node.steps?.length) return { w: CARD.w, h: GROUP.head + node.steps.length * GROUP.step + GROUP.pad };
  return { ...CARD };
}

/** Where everything goes, left to right: sources, datasets, pipelines (a group box with its steps), the datasets they write, object types, then what stands on the types. A column
 * follows the average place of what it reads in the column before it, and is centred against the tallest. Returns {positions: {id: {x, y, w, h}}, columns: [{key, label, x, w, count}], width, height}. */
export function mapLayout(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const kind = Object.fromEntries(nodes.map((n) => [n.id, n.kind]));
  const live = edges.filter((e) => ids.has(e.from) && ids.has(e.to));
  const written = new Set(live.filter((e) => kind[e.from] === "pipeline" && kind[e.to] === "dataset").map((e) => e.to));
  const layerOf = Object.fromEntries(nodes.map((n) => [n.id, n.kind === "dataset" && written.has(n.id) ? 3 : LAYER_OF[n.kind] ?? 6]));
  const lists = LAYERS.map(() => []);
  for (const n of [...nodes].sort((a, b) => String(a.name).localeCompare(String(b.name)))) lists[layerOf[n.id]].push(n);
  const used = lists.map((list, layer) => ({ layer, list })).filter((c) => c.list.length);
  const row = {};
  used.forEach((c) => c.list.forEach((n, i) => { row[n.id] = i; }));
  for (let sweep = 0; sweep < 3; sweep += 1) {
    for (const { layer, list } of used) {
      const mean = (id) => {
        const near = live.filter((e) => e.to === id && layerOf[e.from] < layer).map((e) => row[e.from]);
        return near.length ? near.reduce((a, b) => a + b, 0) / near.length : row[id];
      };
      list.sort((a, b) => mean(a.id) - mean(b.id) || String(a.name).localeCompare(String(b.name)));
      list.forEach((n, i) => { row[n.id] = i; });
    }
  }
  const pitch = CARD.w + COLUMN_GAP;
  const heights = used.map((c) => c.list.reduce((sum, n) => sum + sizeOf(n).h + GAP, -GAP));
  const tallest = Math.max(0, ...heights);
  const columns = used.map((c, i) => ({ key: LAYERS[c.layer].key, get label() { return LAYERS[c.layer].label; }, x: MARGIN + i * pitch, w: CARD.w, count: c.list.length }));
  const positions = {};
  used.forEach((c, i) => {
    let y = TOP + (tallest - heights[i]) / 2;
    for (const n of c.list) {
      const size = sizeOf(n);
      positions[n.id] = { x: columns[i].x, y, ...size };
      y += size.h + GAP;
    }
  });
  return { positions, columns, width: MARGIN * 2 + Math.max(0, used.length * pitch - COLUMN_GAP), height: TOP + tallest + MARGIN };
}

/** The chain through a node: it, everything it reads (up to the sources) and everything that reads it (down to the last object), with the lines between them. */
export function traceSubgraph(id, nodes, edges) {
  const keep = litDepth(id, edges, "both", null);
  return { nodes: nodes.filter((n) => keep.has(n.id)), edges: edges.filter((e) => keep.has(e.from) && keep.has(e.to)) };
}

/** The nodes a search finds, best first, at most `limit`: a name that is the words, one that starts with them, one that holds them, then the kind or the object type they stand on. */
export function searchMatches(nodes, query, kindOf, limit = 8) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const rank = (n) => {
    const name = String(n.name ?? "").toLowerCase();
    if (name === q) return 0;
    if (name.startsWith(q)) return 1;
    if (name.includes(q)) return 2;
    return [kindOf(n), n.type_name, n.key].some((s) => String(s ?? "").toLowerCase().includes(q)) ? 3 : null;
  };
  return nodes.map((n) => ({ n, r: rank(n) })).filter((m) => m.r !== null)
    .sort((a, b) => a.r - b.r || String(a.n.name).localeCompare(String(b.n.name))).slice(0, limit).map((m) => m.n);
}

/** How many nodes of each kind the map holds. */
export function kindCounts(nodes) {
  const out = {};
  for (const n of nodes) out[n.kind] = (out[n.kind] ?? 0) + 1;
  return out;
}

/** The state of a line: a node at either end that failed (red) or needs another look (amber) colours it; otherwise it is plain. */
export function edgeTone(edge, byId) {
  const tones = [byId[edge.from], byId[edge.to]].filter(Boolean).map(stateTone);
  return tones.includes("rejected") ? "rejected" : tones.includes("needs_look") ? "needs_look" : "ok";
}

/** Puts what the other lists know on the nodes: a dataset's rows and columns, a pipeline's steps (`pipelines` is {name: the pipeline as the service gives it}). */
export function enrichNodes(nodes, datasets, pipelines) {
  const stats = Object.fromEntries((datasets ?? []).map((d) => [d.name, d]));
  return nodes.map((n) => {
    const key = n.key ?? n.name;
    if (n.kind === "dataset" && stats[key]) return { ...n, rows: stats[key].rows, columns: stats[key].columns };
    if (n.kind === "pipeline" && pipelines?.[key]?.spec?.steps) return { ...n, steps: pipelines[key].spec.steps };
    return n;
  });
}

const stat = (key, n) => ({ key, value: formatNumber(n), n });

/** What a card says under its header: up to two numbers (each with a key the card draws an icon and a word for), a line of its own kind, and a note when it needs another look. */
export function cardFacts(node) {
  const stats = [];
  let sub = "";
  if (node.kind === "dataset") {
    if (node.columns != null) stats.push(stat("columns", node.columns));
    if (node.rows != null) stats.push(stat("rows", node.rows));
    sub = node.version ? t("lineage.node.version", { version: node.version }) : "";
  } else if (node.kind === "type") {
    if (node.objects != null) stats.push(stat("objects", node.objects));
    if (Array.isArray(node.properties)) stats.push(stat("properties", node.properties.length));
  } else if (node.kind === "source") {
    stats.push(stat("tables", node.tables?.length ?? 0));
    sub = node.kind_label ?? "";
  } else if (node.kind === "relation") {
    sub = [node.from_name, node.to_name].filter(Boolean).join(" → ");
  } else if (node.type_name) {
    sub = node.type_name;
  }
  const word = node.state && node.state !== "confirmed" ? statusOf(node.state, { modelDraft: node.model_draft }).label : "";
  const note = node.status === "failed" ? t("status.failed") : node.stale ? t("lineage.node.needs_look", { label: node.stale.label }) : word;
  return { stats, sub, note, tone: stateTone(node) };
}

/** The view (zoom and offset) that puts `box` in the middle of `frame`. */
export const centreOn = (frame, box, k) => ({ k, x: frame.w / 2 - (box.x + box.w / 2) * k, y: frame.h / 2 - (box.y + box.h / 2) * k });

/** The whole map scaled into a minimap box, keeping its shape: {k, w, h}. */
export function minimapScale(content, box) {
  const k = Math.min(box.w / content.width, box.h / content.height);
  return { k, w: content.width * k, h: content.height * k };
}
