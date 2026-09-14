// Layered left-to-right layout for a company ontology: relations point from the referencing thing to the referenced one.
// ponytail: fixed layout for the 4–15 types an upload produces; switch to a graph library if ontologies grow past that.
export const NODE = { w: 184, h: 64 };
const GAP = { x: 112, y: 32 };
const PAD = 24;

export function layoutGraph(ontology) {
  const keys = ontology.object_types.map((t) => t.key);
  const layer = Object.fromEntries(keys.map((k) => [k, 0]));
  const edges = ontology.relations.filter((r) => layer[r.from] !== undefined && layer[r.to] !== undefined && r.from !== r.to);
  for (let pass = 0; pass < keys.length; pass++) {   // longest path; at most one pass per type, so cycles cannot hang it
    let moved = false;
    for (const e of edges) if (layer[e.to] < layer[e.from] + 1 && layer[e.from] + 1 < keys.length) { layer[e.to] = layer[e.from] + 1; moved = true; }
    if (!moved) break;
  }
  const columns = [];
  for (const k of keys) (columns[layer[k]] ||= []).push(k);
  const filled = columns.filter(Boolean);
  const tallest = Math.max(...filled.map((c) => c.length));
  const height = PAD * 2 + tallest * NODE.h + (tallest - 1) * GAP.y;
  const label = Object.fromEntries(ontology.object_types.map((t) => [t.key, t.label || t.key]));
  const nodes = filled.flatMap((column, ci) => {
    const top = (height - (column.length * NODE.h + (column.length - 1) * GAP.y)) / 2;
    return column.map((k, i) => ({ key: k, label: label[k], x: PAD + ci * (NODE.w + GAP.x), y: top + i * (NODE.h + GAP.y), ...NODE }));
  });
  const at = Object.fromEntries(nodes.map((n) => [n.key, n]));
  const width = PAD * 2 + filled.length * NODE.w + (filled.length - 1) * GAP.x;
  return {
    width, height, nodes,
    edges: ontology.relations.filter((r) => at[r.from] && at[r.to]).map((r, i, all) => {
      const a = at[r.from], b = at[r.to];
      const twin = all.filter((o) => (o.from === r.from && o.to === r.to) || (o.from === r.to && o.to === r.from)).indexOf(r);
      const forward = b.x > a.x;
      const x1 = forward ? a.x + a.w : a.x + a.w / 2, y1 = forward ? a.y + a.h / 2 : a.y + a.h;
      const x2 = forward ? b.x : b.x + b.w / 2, y2 = forward ? b.y + b.h / 2 : b.y;
      const bend = forward ? (x2 - x1) / 2 : 0;
      const skips = forward && Math.round((b.x - a.x) / (NODE.w + GAP.x)) > 1;   // arc over the columns in between
      const lift = twin * 22 + (skips ? NODE.h + GAP.y : 0);
      const path = forward ? `M${x1},${y1} C${x1 + bend},${y1 - lift} ${x2 - bend},${y2 - lift} ${x2},${y2}`
        : `M${x1},${y1} C${x1 + 60 + lift},${y1 + 40} ${x2 + 60 + lift},${y2 - 40} ${x2},${y2}`;
      return { key: r.key, from: r.from, to: r.to, path, lx: (x1 + x2) / 2 + (forward ? 0 : 60 + lift), ly: (y1 + y2) / 2 - lift };
    }),
  };
}

/** Evaluation findings grouped by the object type they concern, so the graph can mark the node. */
export function findingsByType(fit) {
  const by = {};
  const add = (type, kind, detail) => (by[type] ||= []).push({ kind, detail, severity: kind === "orphans" ? "note" : "problem" });
  if (!fit) return by;
  for (const c of fit.identity_conflicts || []) add(c.type, "identity_conflict", c);
  for (const s of fit.identity_spellings || []) add(s.type, "identity_spelling", s);
  for (const d of fit.suspected_duplicates || []) add(d.type, "suspected_duplicate", d);
  for (const m of fit.missing_across_sources || []) add(m.type, "missing_reference", m);
  for (const o of fit.orphans || []) if (o.count) add(o.type, "orphans", o);
  return by;
}

export function edgeStats(fit, key) {
  const r = fit?.relations?.find((x) => x.key === key);
  return r ? { rows: r.rows, linked_rows: r.linked_rows, complete: r.linked_rows === r.rows } : null;
}
