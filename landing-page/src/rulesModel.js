/** Rules found in the data, shaped for the page: per object, adopt or decline, and one chip for the lot. */
import { typeLabel } from "./ontologyStudioModel.js";

/** Candidates per object, in the ontology's order: required fields together, date orders as arrows. */
export function ruleGroups(rules, ontology) {
  return ontology.object_types.map((t) => ({
    type: t.key, label: typeLabel(ontology, t.key),
    required: rules.filter((r) => r.type === t.key && r.kind === "required"),
    orders: rules.filter((r) => r.type === t.key && r.kind === "order"),
  })).filter((g) => g.required.length || g.orders.length);
}

/** The next {adopted, declined} after one click; the service takes the whole lists. */
export function toggleRule(state, id, how) {
  const adopted = state.adopted.filter((x) => x !== id), declined = state.declined.filter((x) => x !== id);
  return how === "adopt" ? { adopted: [...adopted, id], declined } : how === "decline" ? { adopted, declined: [...declined, id] } : { adopted, declined };
}

export const adoptAll = (state, rules) => rules.reduce((s, r) => toggleRule(s, r.id, "adopt"), state);

/** How the rules stand, for the 数据体检 switch. */
export function rulesTile(rules) {
  if (!rules) return null;
  if (!rules.adopted.length) return { value: rules.candidates.length ? `${rules.candidates.length} 条待看` : "没有", tone: "muted" };
  const broken = rules.adopted.filter((r) => r.violations.count).length;
  return broken ? { value: `${broken} / ${rules.adopted.length} 条被违反`, tone: "warn" } : { value: `${rules.adopted.length} 条都守住`, tone: "ok" };
}
