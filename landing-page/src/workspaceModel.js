/** The workspace laid out the way DIP lays out its platform: modules in the sidebar, one card per object, and an
 *  object's own page. A run plays the part of DIP's workspace. */
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
