// The form a downstream platform asks for (DIP asks for key / display / name / type / length per attribute, and a
// cardinality per relation), filled in as far as the data allows. Types and lengths are read from every value by code;
// the columns only a person can write are left for them, never guessed.
import { typeLabel } from "./ontologyStudioModel.js";

export const formOf = (run) => run.evaluation?.handover || null;

/** 多对一 means many of the relation's "from" objects point at one "to" object. */
export function cardinalityLabel({ most_from: perFrom, most_to: perTo }) {
  if (!perFrom && !perTo) return "没有连上";
  if (perFrom > 1 && perTo > 1) return "多对多";
  if (perTo > 1) return "多对一";
  if (perFrom > 1) return "一对多";
  return "一对一";
}

/** "一个班次对应 1 个线路；一个线路最多对应 392 个班次" — the numbers behind the label, in the objects' own names. */
export function cardinalityLine(ontology, rel) {
  const from = typeLabel(ontology, rel.from);
  const to = typeLabel(ontology, rel.to);
  const side = (a, b, n) => `一个${a}${n > 1 ? "最多" : ""}对应 ${n} 个${b}`;
  return `${side(from, to, rel.most_from)}；${side(to, from, rel.most_to)}`;
}

export function fieldNote({ empty, rows, type }) {
  if (type === null) return "全是空的，看不出类型";
  return empty ? `${empty} / ${rows} 行是空的` : "";
}
