/** Numbers shaped for drawing and narrowing: bars, dots, tags and filters instead of sentences. */
import { typeLabel } from "./ontologyStudioModel.js";

/** How full a column is: the share of rows with a value, for a bar. null when no rows were read. */
export function filled(field, rows) {
  if (!rows) return null;
  return { share: Math.round(((rows - field.empty) / rows) * 100), empty: field.empty, rows };
}

/** Columns counted by type, most common first; an all-empty column has no type. */
export function typeMix(fields) {
  const counts = new Map();
  for (const f of fields) counts.set(f.type || "全空", (counts.get(f.type || "全空") || 0) + 1);
  return [...counts].sort((a, b) => b[1] - a[1]);
}

/** Every object and relation of the shown build, then what only other builds had: how many of the builds had it. */
export function stabilityRows(ontology, s) {
  const rows = [
    ...ontology.object_types.map((t) => ({ label: t.label || t.key, kind: "对象", present: s.types[t.key] ?? s.runs, runs: s.runs, here: true })),
    ...ontology.relations.map((r) => ({ label: `${typeLabel(ontology, r.from)} ${r.label || "—"} ${typeLabel(ontology, r.to)}`, kind: "关系", present: s.relations[r.key] ?? s.runs, runs: s.runs, here: true })),
  ];
  return rows.concat(s.elsewhere.types.map((t) => ({ label: t.label, kind: "对象", present: t.count, runs: s.runs, here: false })),
    s.elsewhere.relations.map((r) => ({ label: r.label, kind: "关系", present: r.count, runs: s.runs, here: false })));
}

/** Cards whose name (the model's or the one the person gave) contains the query, with the chosen verdict. */
export function filterCards(cards, query, verdict) {
  const q = query.trim();
  return cards.filter((c) => (!q || c.label.includes(q) || (c.renamed || "").includes(q))
    && (verdict === "all" || (verdict === "none" ? !c.verdict : c.verdict === verdict)));
}

export function filterQuestions(items, which) {
  if (which === "all") return items;
  return items.filter((i) => (which === "answered") === (i.status === "answered"));
}

/** What an answer counted, as short tags. */
export function answerTags(item) {
  const a = item.answer || {};
  if (a.measure) return [`${a.measure.op === "sum" ? "合计" : "平均"} · ${a.measure.field}`, `读到 ${a.measure.counted} 个值`, ...(a.measure.skipped ? [`跳过 ${a.measure.skipped} 个`] : [])];
  if (a.share) return [`占比 · ${a.share.field} = ${a.share.equals}`];
  return [];
}

/** Rows as CSV with a byte-order mark, so a spreadsheet opens Chinese and leading zeros as written. */
export function rowsCsv(columns, rows) {
  const cell = (v) => (v === undefined || v === null ? "" : /[",\r\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  return `﻿${[columns, ...rows.map((r) => columns.map((c) => r[c]))].map((line) => line.map(cell).join(",")).join("\r\n")}\r\n`;
}
