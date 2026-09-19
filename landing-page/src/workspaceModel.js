/** The workspace laid out as a data platform: modules in the sidebar, one card per object, and an object's own
 *  page. A run plays the part of a workspace. */
import { isDocument, typeLabel } from "./ontologyStudioModel.js";

const SECTIONS = [["data", "数据接入"], ["objects", "本体管理"], ["graph", "本体关系"], ["qa", "智能问答"], ["check", "数据体检"]];

/** The modules a run can show: a document has no rows to lay out or to answer questions from. */
export function sectionsFor(run) {
  if (!run) return [];
  return isDocument(run) ? SECTIONS.filter(([key]) => key !== "data" && key !== "qa") : SECTIONS;
}

/** One card per object: what it is called, a line about it, where it is read from and how it connects. */
export function objectCards(run, decisions) {
  const { ontology } = run;
  const counts = ontology.verification?.metrics?.instances || {};
  return ontology.object_types.map((t) => ({
    key: t.key, label: t.label || t.key, note: t.definition || t.rationale || "",
    sources: [...new Set(t.populated_from.map((p) => p.source))],
    identity: [...new Set(t.populated_from.flatMap((p) => Object.values(p.identity)))],
    count: counts[t.key] ?? null,
    relations: ontology.relations.filter((r) => r.from === t.key || r.to === t.key).length,
    verdict: decisions?.types[t.key]?.verdict || null,
    renamed: decisions?.types[t.key]?.label || null,
  }));
}

/** The relations an object takes part in, each with the object at its other end. */
export function objectRelations(run, key) {
  const { ontology } = run;
  return ontology.relations.filter((r) => r.from === key || r.to === key).map((r) => ({
    key: r.key, text: `${typeLabel(ontology, r.from)} ${r.label || "→"} ${typeLabel(ontology, r.to)}`, other: r.from === key ? r.to : r.from,
  }));
}

/** Where a status chip leads. */
export function sectionOfTile(tile) {
  return { ontology: "objects", stability: "objects", fit: "check", qa: "qa", ref: "check" }[tile] || "objects";
}

/** 本体管理's own places, each with the number that says whether to go there; a place with nothing in it is left out. */
export function objectsNav(run, decisions) {
  const { ontology, evaluation } = run;
  const judged = [...Object.values(decisions?.types || {}), ...Object.values(decisions?.relations || {})].filter((d) => d.verdict).length;
  const gaps = ontology.data_gaps?.length || 0;
  return [
    ["objects", "对象", String(ontology.object_types.length)],
    ["confirm", "逐项确认", `${judged} / ${ontology.object_types.length + ontology.relations.length}`],
    ...(run.version ? [["version", "新版本", `＋${run.version.objects.reduce((n, o) => n + (o.added || 0), 0)} －${run.version.objects.reduce((n, o) => n + (o.removed || 0), 0)}`]] : []),
    ...(evaluation.stability ? [["stability", "稳定性", `${evaluation.stability.runs} 次`]] : []),
    ...(run.previous ? [["history", "和上次比", ""]] : []),
    ["build", "建模记录", gaps ? `缺口 ${gaps}` : ""],
  ];
}

/** 智能问答's places: asking, the questions fixed with the business, the model's round. */
export function qaNav(run) {
  const { evaluation } = run;
  const mine = (evaluation.asked || []).reduce((n, r) => n + (r.items?.length || 0), 0);
  const round = evaluation.questions;
  const answered = round?.items?.filter((i) => i.status === "answered").length;
  return [
    ["ask", "提问", String(mine)],
    ["acceptance", "验收问题", String(evaluation.acceptance?.items.length || 0)],
    ["model", "模型出的题", round?.items ? `${answered} / ${round.items.length}` : "—"],
  ];
}
