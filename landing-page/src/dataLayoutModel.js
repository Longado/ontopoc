/** The data view and the ask box: what was uploaded, how it hangs together, and what to ask of it. */

/** One sentence per column that would connect tables the ontology left apart. */
export function bridgeLines(run) {
  return (run.evaluation?.data_fit?.bridges || []).map((b) =>
    `${b.from_source} 的「${b.from_field}」有 ${b.linked_rows} / ${b.rows} 行，能在 ${b.to_source} 的「${b.to_field}」里找到`);
}

/** Every uploaded table with its size, skipped title lines, column shapes (null for runs saved before these were
 *  kept) and the connected group it belongs to. */
export function layoutTables(run) {
  const groups = run.evaluation?.data_fit?.source_groups || [];
  const profiled = Object.fromEntries((run.evaluation?.handover?.sources || []).map((s) => [s.name, s]));
  return run.sources.map((s) => ({
    name: s.name, rows: s.rows, fieldCount: s.fields,
    skipped: profiled[s.name]?.skipped_rows || s.skipped_rows || [],
    fields: profiled[s.name]?.fields || null,
    group: Math.max(0, groups.findIndex((g) => g.includes(s.name))),
  }));
}

/** Questions this run already answered, as starting points: clicking one shows its answer, no model call. */
export function askSuggestions(run) {
  return (run.evaluation?.questions?.items || []).filter((i) => i.status === "answered").slice(0, 3);
}

/** The last question asked in the box, or the error it ended with. */
export function latestAsked(run) {
  const last = (run.evaluation?.asked || []).at(-1);
  if (!last) return null;
  return last.error ? { error: last.error } : last.items.at(-1) || null;
}
