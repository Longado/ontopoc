// Spellings the model says are one and the same thing. Code already refused anything the data does not contain;
// here a person accepts or drops each group, and the accepted ones ride along with the rest of the confirmation.
const same = (a, b) => a.type === b.type && a.values.length === b.values.length && a.values.every((v, i) => v === b.values[i]);

const labelOf = (ontology, key) => ontology.object_types.find((t) => t.key === key)?.label || key;

/** This run's candidates, plus the groups a person already accepted for an object this run still has. */
export function variantRows(run, decisions) {
  const accepted = decisions.variants || [];
  const offered = (run.evaluation?.variants?.groups || []).map((g) => ({ ...g, accepted: accepted.some((d) => same(d, g)), carried: false }));
  const carried = accepted.filter((d) => !offered.some((g) => same(g, d)) && run.ontology.object_types.some((t) => t.key === d.type))
    .map((d) => ({ type: d.type, label: labelOf(run.ontology, d.type), values: d.values, records: null, reasoning: "", accepted: true, carried: true }));
  return [...offered, ...carried];
}

export function toggleVariant(decisions, group) {
  const kept = (decisions.variants || []).filter((d) => !same(d, group));
  return { ...decisions, variants: kept.length < (decisions.variants || []).length ? kept : [...kept, { type: group.type, values: group.values }] };
}

/** What the model proposed and what code threw out: a group the data cannot back never reaches the person. */
export function variantNote(run) {
  const found = run.evaluation?.variants;
  if (!found) return null;
  const dropped = (found.rejected || []).map((r) => `${labelOf(run.ontology, r.type)} ${(r.values || []).join("、")}：${r.reason}`);
  if (found.note) return { line: found.note, dropped };
  return { line: `模型 ${found.model} 提了 ${found.groups.length} 组，代码丢掉 ${dropped.length} 组。`, dropped };
}
