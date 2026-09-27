export const mappingKey = row => JSON.stringify([row.kind, row.owner || "", row.reference]);

/** API responses replace object references; only changed correspondence inputs invalidate a draft. */
export function referenceRevision(run) {
  const inputs = { ontology: run.ontology, decisions: run.confirmation?.decisions,
    fields: run.evaluation?.handover?.sources?.map(source => ({ name: source.name, fields: source.fields })),
    record: run.evaluation?.domain_reference };
  return JSON.stringify(inputs, (_, value) => value && typeof value === "object" && !Array.isArray(value)
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]])) : value);
}

export function graphSelection(run, row, side) {
  const key = side === "reference" ? (row.kind === "property" ? row.owner : row.reference)
    : (row.kind === "property" ? row.local_owner : row.local);
  const kind = row.kind === "relation" ? "edge" : "node";
  const items = kind === "edge" ? run?.ontology.relations : run?.ontology.object_types;
  return items?.some(item => item.key === key) ? { kind, key } : null;
}

/** Changing an object invalidates its dependent decisions, never silently retargets them. */
export function updateMapping(mappings, row, next, definition) {
  const removed = new Set(row.kind === "object"
    ? definition.relationships.filter(r => r.from === row.reference || r.to === row.reference).map(r => r.id) : []);
  const remaining = mappings.filter(m => mappingKey(m) !== mappingKey(row) && !(row.kind === "object" &&
    ((m.kind === "property" && m.owner === row.reference) || (m.kind === "relation" && removed.has(m.reference)))));
  return next ? [...remaining, next] : remaining;
}
