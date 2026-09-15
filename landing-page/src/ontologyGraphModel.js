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
  const colOf = Object.fromEntries(filled.flatMap((c, ci) => c.map((k) => [k, ci])));
  const arcs = edges.some((e) => colOf[e.to] - colOf[e.from] > 1);
  const headroom = arcs ? Math.round((NODE.h + GAP.y) * 0.8) : 0;   // room for edges that arc over a column
  const height = PAD * 2 + headroom + tallest * NODE.h + (tallest - 1) * GAP.y;
  const label = Object.fromEntries(ontology.object_types.map((t) => [t.key, t.label || t.key]));
  const nodes = filled.flatMap((column, ci) => {
    const top = headroom + (height - headroom - (column.length * NODE.h + (column.length - 1) * GAP.y)) / 2;
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

export function neighboursOf(ontology, key) {
  const nodes = new Set([key]), edges = new Set();
  for (const r of ontology.relations) if (r.from === key || r.to === key) { edges.add(r.key); nodes.add(r.from); nodes.add(r.to); }
  return { nodes, edges };
}

/** The types and relations a question's query walks, so the graph can show how an answer was found: one walk per
 * grouping route (or the top-level via), and the union of them for highlighting. */
export function pathOf(ontology, query) {
  if (!query || !ontology.object_types.some((t) => t.key === query.start)) return null;
  const walk = (via) => {
    const nodes = [query.start], edges = [];
    let current = query.start;
    for (const key of via || []) {
      const r = ontology.relations.find((x) => x.key === key);
      if (!r || (r.from !== current && r.to !== current)) return null;
      current = r.from === current ? r.to : r.from;
      nodes.push(current);
      edges.push(key);
    }
    return { nodes, edges };
  };
  const dims = Array.isArray(query.group_by) ? query.group_by.filter((d) => d && typeof d === "object") : [];
  const walks = (dims.length ? dims.map((d) => d.via) : [query.via]).map(walk);
  if (walks.some((w) => !w)) return null;
  return { walks, nodes: [...new Set(walks.flatMap((w) => w.nodes))], edges: [...new Set(walks.flatMap((w) => w.edges))] };
}

export function overviewTiles(run) {
  const { ontology, evaluation } = run;
  const doc = run.file?.kind === "document";
  const fit = evaluation.data_fit || evaluation.document_fit;
  const passed = fit ? fit.checks.filter((c) => c.passed).length : 0;
  const diffCount = (d) => d.types.only_reference.length + d.types.only_ours.length + d.relations.only_reference.length + d.relations.only_ours.length;
  const ref = evaluation.reference?.diff.counts.types;
  const asked = (evaluation.asked || []).flatMap((r) => r.items || []);
  const round = evaluation.questions?.total ? evaluation.questions : { answered: 0, total: 0 };
  const q = round.total + asked.length ? { answered: round.answered + asked.filter((i) => i.status === "answered").length, total: round.total + asked.length } : null;
  const changes = run.previous ? diffCount(run.previous.diff) : null;
  return [
    { key: "ontology", label: "本体", value: `${ontology.object_types.length} 个对象 · ${ontology.relations.length} 条关系`, tone: "neutral", hint: "点开看关系图" },
    { key: "fit", label: doc ? "文档检查" : "数据体检", value: fit ? `通过 ${passed} / ${fit.checks.length}` : "未评测", tone: !fit ? "neutral" : passed === fit.checks.length ? "ok" : "warn",
      hint: !fit ? "" : passed === fit.checks.length ? "全部通过" : `${fit.checks.length - passed} 项没通过，点开看是哪些` },
    { key: "qa", label: "业务问答", value: doc ? "不适用于文档" : q ? `能回答 ${q.answered} / ${q.total}` : "还没出题", tone: !q || doc ? "neutral" : q.answered === q.total ? "ok" : "warn",
      hint: doc ? "文档没有数据行" : !q ? (run.saved_as ? "点开出一组问题" : "上传自己的文件后可以提问") : q.answered === q.total ? "都能用数据回答" : `${q.total - q.answered} 题答不了，点开看原因` },
    { key: "ref", label: "对照标准", value: ref ? `命中 ${ref.matched} / ${ref.reference}` : "还没比对", tone: !ref ? "neutral" : ref.matched === ref.reference ? "ok" : "warn",
      hint: !ref ? "上传参考本体后可以比" : ref.matched === ref.reference ? "参考里的对象都对上了" : `参考里有 ${ref.reference - ref.matched} 个对象没对上` },
    evaluation.stability ? stabilityTile(ontology, evaluation.stability)
      : { key: "stability", label: "稳定性", value: changes === null ? "第一次运行" : changes ? `和上次有 ${changes} 处不同` : "和上次一致", tone: changes === null ? "neutral" : changes ? "warn" : "ok",
        hint: changes === null ? "再上传同一文件可看差别" : changes ? "模型每次搭的会有出入" : "两次搭的一样" },
  ];
}

const times = (runs) => (runs === 3 ? "三次" : `${runs} 次`);

/** Whether an object ("types") or relation ("relations") of the shown run was missing from some other run. */
export function unsteady(stability, kind, key) {
  return Boolean(stability && stability[kind][key] !== undefined && stability[kind][key] < stability.runs);
}

function stabilityTile(ontology, s) {
  const steadyTypes = ontology.object_types.filter((t) => !unsteady(s, "types", t.key)).length;
  const shownSteady = steadyTypes === ontology.object_types.length && !ontology.relations.some((r) => unsteady(s, "relations", r.key));
  const extra = s.elsewhere.types.length;
  const tile = (tone, value, hint) => ({ key: "stability", label: "稳定性", tone, value, hint });
  if (s.runs < 2) return tile("neutral", "另外两次都没成功", "这次无法比较");
  if (!shownSteady) return tile("warn", `${steadyTypes} / ${ontology.object_types.length} 个对象${times(s.runs)}都有`, "虚线框的对象不是每次都有");
  if (extra || s.elsewhere.relations.length) return tile("ok", `这次的 ${ontology.object_types.length} 个对象${times(s.runs)}都有`, extra ? `另有 ${extra} 个对象只在别的某次出现` : "别的某次多了关系，点开看");
  return tile("ok", `${times(s.runs)}搭的都一样`, "对象和关系每次都有");
}

export function consensusLines(ontology, s) {
  const label = (key) => ontology.object_types.find((t) => t.key === key)?.label || key;
  const of = (n) => `（${s.runs} 次里 ${n} 次）`;
  const lines = [];
  if (s.failed) lines.push(s.runs < 2 ? "另外两次都没有成功，这次无法比较" : `另外${s.failed === 1 ? "一次" : `${s.failed} 次`}没有成功，只比了 ${s.runs} 次`);
  const steady = ontology.object_types.filter((t) => !unsteady(s, "types", t.key)).map((t) => t.label || t.key);
  if (steady.length) lines.push(`每次都有：${steady.join("、")}`);
  const shaky = [...ontology.object_types.filter((t) => unsteady(s, "types", t.key)).map((t) => `${t.label || t.key}${of(s.types[t.key])}`),
    ...ontology.relations.filter((r) => unsteady(s, "relations", r.key)).map((r) => `关系 ${label(r.from)} — ${label(r.to)}${of(s.relations[r.key])}`)];
  if (shaky.length) lines.push(`不是每次都有：${shaky.join("；")}`);
  const elsewhere = [...s.elsewhere.types.map((t) => `${t.label}${of(t.count)}`), ...s.elsewhere.relations.map((r) => `关系 ${r.label}${of(r.count)}`)];
  if (elsewhere.length) lines.push(`这次没有、别的某次有：${elsewhere.join("；")}`);
  return lines;
}
