// A person's item-by-item judgement of an ontology. Every change returns new decisions; the old ones are never edited.
import { tableChecks } from "./dataLayoutModel.js";
import { savedAcceptance } from "./ontologyAcceptanceModel.js";

export function decisionsOf(run) {
  const saved = run.confirmation?.decisions || run.evaluation?.reference?.suggested;   // a rerun starts from the last confirmation
  return saved ? { types: { ...saved.types }, relations: { ...saved.relations }, added: [...(saved.added || [])], variants: [...(saved.variants || [])] }
    : { types: {}, relations: {}, added: [], variants: [] };
}

/** Whether the confirmation kept with `after` differs from the one kept with `before`: the page's own copy of the decisions is then out of date. */
export const savedDecisionsChanged = (before, after) => JSON.stringify(before?.confirmation?.decisions ?? null) !== JSON.stringify(after?.confirmation?.decisions ?? null);

/** The relations the run keeps a verdict for that the page's decisions no longer judge: clicked off, which the service reads as taking the verdict
 *  back (a relation the page never held, because it loaded before it was judged, is not in this list). */
export const clearedRelations = (run, decisions) => Object.entries(run.confirmation?.decisions?.relations ?? {})
  .filter(([key, d]) => d?.verdict && !decisions.relations[key]?.verdict).map(([key]) => key);

/** The page's decisions after what is kept changed under it (a bulk approval): what the person has touched since the page last had the kept ones
 *  stays, everything else comes from the server. `base` is the kept decisions the page last had, `server` the ones that arrived. */
export function mergeDecisions(local, base, server) {
  const json = (v) => JSON.stringify(v ?? null);
  const pick = (kind) => {
    const out = {};
    for (const key of new Set([...Object.keys(local[kind]), ...Object.keys(base[kind]), ...Object.keys(server[kind])])) {
      const value = json(local[kind][key]) !== json(base[kind][key]) ? local[kind][key] : server[kind][key];
      if (value !== undefined) out[key] = value;
    }
    return out;
  };
  const list = (field) => (json(local[field]) === json(base[field]) ? server[field] : local[field]);
  return { ...server, types: pick("types"), relations: pick("relations"), added: list("added"), variants: list("variants") };
}

/** What was saved for one object ("types") or relation: the decision, who made it, when, which version, and the stored
 *  key checks it rests on as sentences. Null when nothing was saved for it (or the run was saved before this was kept). */
export function elementNote(run, kind, key) {
  const saved = run.confirmation?.elements?.[`${kind}:${key}`];
  if (!saved) return null;
  const ids = (saved.evidence_ref || "").split(",").filter(Boolean).map((ref) => Number(ref.split(":")[1]));
  const evidence = (run.data_checks?.keys || []).filter((k) => ids.includes(k.check_id)).map((k) => {
    const line = tableChecks(run, k.dataset)?.keys.find((x) => x.checkId === k.check_id);
    return line ? `${k.dataset}（${line.columns}）：${line.text}` : null;
  }).filter(Boolean);
  return { state: saved.state, who: saved.confirmed_by, at: saved.confirmed_at, version: saved.version, evidence };
}

/** 重传时，模型又提出了哪些上次被判错的对象；这次重新确认过就不再提。 */
export function returnedNote(run) {
  const returned = run.confirmation ? [] : run.evaluation?.reference?.suggested?.returned || [];
  return returned.length ? `模型又提出了你上次判错的：${returned.join("、")}` : "";
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
