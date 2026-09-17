// A person's item-by-item judgement of an ontology. Every change returns new decisions; the old ones are never edited.
import { savedAcceptance } from "./ontologyAcceptanceModel.js";

export function decisionsOf(run) {
  const saved = run.confirmation?.decisions || run.evaluation?.reference?.suggested;   // a rerun starts from the last confirmation
  return saved ? { types: { ...saved.types }, relations: { ...saved.relations }, added: [...(saved.added || [])], variants: [...(saved.variants || [])] }
    : { types: {}, relations: {}, added: [], variants: [] };
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

/** Against a person's own confirmation, "the ontology has it, the reference does not" means judged wrong or not judged yet. */
export function splitExtras(ontology, decisions, diff) {
  const label = (key) => ontology.object_types.find((t) => t.key === key)?.label || key;
  const typeKey = Object.fromEntries(ontology.object_types.map((t) => [t.label || t.key, t.key]));
  const relKey = Object.fromEntries(ontology.relations.map((r) => [`${label(r.from)} — ${label(r.to)}`, r.key]));
  const split = (names, keyOf, verdicts) => ({
    wrong: names.filter((n) => verdicts[keyOf[n]]?.verdict === "wrong"),
    unjudged: names.filter((n) => verdicts[keyOf[n]]?.verdict !== "wrong"),
  });
  return { types: split(diff.types.only_ours, typeKey, decisions.types), relations: split(diff.relations.only_ours, relKey, decisions.relations) };
}

/** Objects that other runs of this file built and this one did not, offered for adding in one click. */
export function otherRunTypes(run, decisions) {
  const s = run.evaluation?.stability;
  return (s?.elsewhere.types || []).filter((t) => !decisions.added.includes(t.label)).map((t) => ({ ...t, runs: s.runs }));
}

/** The confirmed reference as a file to keep or import: who confirmed it, for which file, and the identities the data check disproved. */
export function referenceDownload(run) {
  const c = run.confirmation;
  const conflicts = run.evaluation.data_fit?.identity_conflicts || [];
  const data_check = run.ontology.object_types.map((t) => ({ t, n: new Set(conflicts.filter((x) => x.type === t.key).map((x) => x.identity)).size }))
    .filter(({ n }) => n).map(({ t, n }) => ({ type: t.key, label: t.label || t.key, note: `识别字段在数据里不唯一：${n} 个编号在不同行里信息不一致` }));
  return { schema: "ontopoc_reference.v1", purpose: run.purpose,
    confirmed: { at: c.confirmed_at, by: c.confirmed_by || null, file: run.file.name, sha256: run.file.sha256 },
    ...c.reference, acceptance: savedAcceptance(run), data_check };
}
