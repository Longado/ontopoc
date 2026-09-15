// A person's item-by-item judgement of an ontology. Every change returns new decisions; the old ones are never edited.

export function decisionsOf(run) {
  const saved = run.confirmation?.decisions;
  return saved ? { types: { ...saved.types }, relations: { ...saved.relations }, added: [...(saved.added || [])] } : { types: {}, relations: {}, added: [] };
}

const without = (map, key) => Object.fromEntries(Object.entries(map).filter(([k]) => k !== key));

/** Pressing the same verdict again clears it. A right relation marks its ends right; a wrong object marks its relations wrong. */
export function setVerdict(ontology, decisions, kind, key, verdict) {
  const current = decisions[kind][key];
  let next = { ...decisions, [kind]: current?.verdict === verdict ? without(decisions[kind], key) : { ...decisions[kind], [key]: { ...current, verdict } } };
  if (kind === "relations" && verdict === "ok" && current?.verdict !== "ok") {
    const r = ontology.relations.find((x) => x.key === key);
    const types = { ...next.types };
    for (const end of [r.from, r.to]) types[end] = { ...types[end], verdict: "ok" };
    next = { ...next, types };
  }
  if (kind === "types" && verdict === "wrong" && current?.verdict !== "wrong") {
    const relations = { ...next.relations };
    for (const r of ontology.relations) if ((r.from === key || r.to === key) && relations[r.key]?.verdict === "ok") relations[r.key] = { verdict: "wrong" };
    next = { ...next, relations };
  }
  return next;
}

export function renameType(decisions, key, label) {
  const { label: _old, ...rest } = decisions.types[key] || {};
  const name = label.trim();
  return { ...decisions, types: { ...decisions.types, [key]: name ? { ...rest, label: name } : rest } };
}

export function addType(ontology, decisions, label) {
  const name = label.trim();
  const taken = new Set([...ontology.object_types.map((t) => t.label || t.key), ...decisions.added]);
  return !name || taken.has(name) ? decisions : { ...decisions, added: [...decisions.added, name] };
}

export const removeAdded = (decisions, label) => ({ ...decisions, added: decisions.added.filter((x) => x !== label) });

export function confirmProgress(ontology, decisions) {
  const all = [...Object.values(decisions.types), ...Object.values(decisions.relations)].filter((d) => d.verdict);
  return { judged: all.length, total: ontology.object_types.length + ontology.relations.length,
    ok: all.filter((d) => d.verdict === "ok").length, wrong: all.filter((d) => d.verdict === "wrong").length, added: decisions.added.length };
}
