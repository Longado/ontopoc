// The assistant's modes and cards as plain functions, so they can be tested without a browser.
// One turn is one user message, one mode, one bounded call (or none) and one result card. Nothing here saves, runs or confirms anything.

export const MODES = ["ask", "query", "model", "pipeline"];

/** The modes a person sees as chips: a viewer gets Ask only (the others are absent, not disabled); a builder gets all. */
export const modesFor = (mayBuild) => (mayBuild ? MODES : ["ask"]);

/** A mode this person may use: anything else is Ask. */
export const allowedMode = (mode, mayBuild) => (modesFor(mayBuild).includes(mode) ? mode : "ask");

/** What the scope chip in the composer is about: confirmed types (Ask, Query), datasets (Model), a dataset or a pipeline (Pipeline). */
export const scopeKind = (mode) => (mode === "model" ? "datasets" : mode === "pipeline" ? "target" : "types");

/** Slash commands: "/model ...", "/pipeline ...", "/query ..." (and "/ask ...") switch the mode; the rest of the line is the message.
 * Returns {mode, text} when the text starts with a command this person may use, else null. A viewer's "/model" is just text. */
export function parseCommand(input, mayBuild) {
  const m = /^\s*\/([a-z]+)(?:\s+([\s\S]*))?$/i.exec(String(input ?? ""));
  if (!m) return null;
  const mode = m[1].toLowerCase();
  if (!MODES.includes(mode) || !modesFor(mayBuild).includes(mode)) return null;
  return { mode, text: (m[2] ?? "").replace(/^\s+/, "") };
}

/** The commands to offer while the person types "/": those this person may use and that start with what is typed. */
export function commandChoices(input, mayBuild) {
  const m = /^\s*\/([a-z]*)$/i.exec(String(input ?? ""));
  if (!m) return [];
  return modesFor(mayBuild).filter((mode) => mode.startsWith(m[1].toLowerCase()));
}

/** True when the model is the thing that is missing: the server says it holds no model credentials. */
export const isNoModel = (message) => /no model credentials|没有模型凭据/i.test(String(message ?? ""));

/** What each mode shows as the line under the composer, as an i18n key: the model sees what that agent's card in docs/AGENTS.md says. */
export const privacyKey = (mode) => `ask.assistant.privacy.${MODES.includes(mode) ? mode : "ask"}`;

const sum = (list) => (list ?? []).reduce((a, n) => a + (Number(n) || 0), 0);

/** The plan card for a pipeline draft (the response of the AI draft endpoint) and the answers given to its questions so far.
 * {steps, flow, assumptions, open, done, notDone, canApply, blocked}: `done` and `notDone` are keys with vars, worded by the component,
 * worked out only from what the response contains. Nothing has been saved or run, and the card says so. */
export function planCard(draft, answers = {}) {
  const d = draft ?? {};
  const steps = (d.steps ?? []).map((s) => ({
    id: s.id, summary: s.summary, kind: s.step?.type ?? "", rowsIn: s.rows_in ?? null, rowsOut: s.rows_out ?? null, calls: s.to_call ?? null,
    operators: (s.operators ?? []).map((o) => o.text), failures: s.failures ?? [],
  }));
  const counted = steps.length > 0 && steps.every((s) => s.rowsOut != null && s.rowsIn);
  const flow = counted ? [sum(steps[0].rowsIn), ...steps.map((s) => s.rowsOut)] : [];
  const questions = d.questions ?? [];
  const chosen = (q) => (answers[q.id] ?? []).length > 0;
  const open = questions.filter((q) => !chosen(q));
  const assumptions = [
    ...(d.cites ?? []).map((c) => ({ text: c.text, state: "confirmed" })),
    ...questions.map((q) => ({ text: q.ask, state: chosen(q) ? "answered" : "open", id: q.id, answer: chosen(q) ? (q.options ?? []).filter((o) => answers[q.id].includes(o.value)).map((o) => o.text).join(", ") : "" })),
  ];
  const ok = Boolean(d.check?.ok);
  const done = [];
  const notDone = [];
  if (ok) done.push({ key: "columns" });
  if (ok && d.check.dry_run) done.push({ key: "dry", text: d.check.dry_run });
  if (counted) done.push({ key: "counts", count: steps.length });
  if ((d.cites ?? []).length) done.push({ key: "cites", count: d.cites.length });
  if (!ok) notDone.push({ key: "failed", text: d.check?.error ?? "" });
  if (open.length) notDone.push({ key: "open", count: open.length });
  const failing = steps.filter((s) => s.failures.length).length;
  if (failing) notDone.push({ key: "stepFailures", count: failing });
  notDone.push({ key: "fullRun" }, { key: "saved" });
  const canApply = ok && steps.length > 0 && open.length === 0;
  const blocked = !ok ? "failed" : steps.length === 0 ? "empty" : open.length ? "open" : "";
  return { steps, flow, assumptions, open: open.length, done, notDone, canApply, blocked };
}

/** The proposal card for the type suggester's answer ({proposed: [{id, name}], rejected: [{name, reason}]}) and each proposed type as read back
 * (the type's own page data: key, properties with what each is needed for, basis). Each type carries its basis; the rejected carry their reasons. */
export function proposalCard(result, details = []) {
  const byId = Object.fromEntries((details ?? []).filter(Boolean).map((x) => [x.id, x]));
  const types = (result?.proposed ?? []).map((p) => {
    const x = byId[p.id] ?? {};
    return {
      id: p.id, name: p.name, dataset: x.dataset ?? "", key: x.key ?? [], basis: x.basis ?? "", version: x.version ?? null,
      properties: (x.properties ?? []).map((q) => ({ column: q.column, name: q.name && q.name !== q.column ? q.name : "", why: q.needed_for ?? "" })),
      loaded: Boolean(byId[p.id]),
    };
  });
  const rejected = (result?.rejected ?? []).map((r) => ({ name: r.name, reason: r.reason }));
  const done = types.length ? [{ key: "checked", count: types.length }, { key: "kept", count: types.length }] : [];
  const notDone = [...(types.length ? [{ key: "confirmed" }] : []), ...(rejected.length ? [{ key: "dropped", count: rejected.length }] : [])];
  return { types, rejected, done, notDone, canPropose: types.some((x) => x.loaded) };
}

/** The payload that proposes a model-suggested type through the normal update path (what saving it from the type's own form sends), or null if it is not fully read back. */
export function proposePayload(type) {
  if (!type?.id || !type.dataset || !type.key?.length || type.version == null) return null;
  const props = type.properties ?? [];
  const enums = Object.fromEntries(props.filter((p) => p.enum && p.meanings?.values?.length).map((p) => [p.column, p.meanings.values.map((v) => ({ value: v.value, label: v.label }))]));
  return {
    id: type.id, version: type.version, english_name: type.id, name: type.name, description: type.description ?? "", dataset: type.dataset, key: type.key,
    properties: props.map((p) => ({ column: p.column, name: p.name || p.column, type: p.type, enum: Boolean(p.enum) })), enums,
  };
}

// Handing a draft to the pipeline editor: the steps wait in this tab's session storage under the pipeline's name until the editor opens it,
// which applies them the way the editor's own AI panel does. A draft for a pipeline that does not exist yet waits under "new:<dataset>"
// and is moved to the pipeline's name when the person creates it.
const stashKey = (target) => `assistant-draft:${target}`;
export function stashDraft(storage, target, steps) {
  storage.setItem(stashKey(target), JSON.stringify(steps));
}
/** The steps waiting for `target`, taken out (so they apply once); null when there are none. */
export function takeDraft(storage, target) {
  const raw = storage.getItem(stashKey(target));
  if (raw == null) return null;
  storage.removeItem(stashKey(target));
  try {
    const steps = JSON.parse(raw);
    return Array.isArray(steps) && steps.length ? steps : null;
  } catch {
    return null;
  }
}
export function moveDraft(storage, from, to) {
  const raw = storage.getItem(stashKey(from));
  if (raw == null) return;
  storage.removeItem(stashKey(from));
  storage.setItem(stashKey(to), raw);
}

/** The pipeline's step the assistant works from when the person names a pipeline: the last step that is not an output. */
export const defaultSelected = (spec) => [...(spec?.steps ?? [])].reverse().find((s) => s.type !== "output")?.id ?? null;
/** The spec the assistant drafts over when the scope is a dataset: one input step, the way a new pipeline starts. */
export const datasetSpec = (dataset) => ({ steps: [{ id: "in1", type: "input", dataset }] });
