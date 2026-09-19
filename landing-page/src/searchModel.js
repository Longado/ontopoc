/** ⌘K: one search over what the modules keep apart — objects, their fields, relations, uploaded tables — each hit
 *  saying where it is shown. Matching is plain substring, case-insensitive, on names and keys. */
import { isDocument } from "./ontologyStudioModel.js";
import { fieldsOf } from "./workspaceModel.js";

const KINDS = ["object", "field", "relation", "table"];

export function searchIndex(run, decisions) {
  const { ontology } = run;
  const name = (key) => decisions?.types?.[key]?.label || ontology.object_types.find((t) => t.key === key)?.label || key;
  return [
    ...ontology.object_types.map((t) => ({ kind: "object", text: name(t.key), sub: t.key, keys: [t.key, t.label], target: { tab: "objects", object: t.key } })),
    ...ontology.object_types.flatMap((t) => fieldsOf(run, t).map((f) => ({
      kind: "field", text: f.path, sub: `${name(t.key)}${f.identity ? " · 主键" : ""}`, keys: [], target: { tab: "objects", object: t.key, sub: "fields" } }))),
    ...ontology.relations.map((r) => ({ kind: "relation", text: `${name(r.from)} ${r.label || "→"} ${name(r.to)}`, sub: "", keys: [], target: { tab: "graph", relation: r.key } })),
    ...(isDocument(run) ? [] : (run.sources || []).map((s) => ({ kind: "table", text: s.name, sub: s.rows != null ? `${s.rows.toLocaleString("zh-CN")} 行` : "", keys: [], target: { tab: "data", table: s.name } }))),
  ];
}

export function searchHits(index, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const hit = (item) => [item.text, ...item.keys].some((s) => String(s || "").toLowerCase().includes(q));
  return index.filter(hit).sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind));
}
