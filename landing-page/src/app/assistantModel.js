// The assistant's modes and cards as plain functions, so they can be tested without a browser.
// One turn is one user message, one mode, one bounded call (or none) and one result card. Nothing here saves, runs or confirms anything.

export const MODES = ["ask", "query", "model", "pipeline", "meanings"];
const PUT_AWAY = ["pipeline"];   // kept in the code and in past turns, not offered: the gate does not need the assistant to write pipelines

/** The modes a person sees as chips: a viewer gets Ask only (the others are absent, not disabled); a builder gets the rest but the modes put away. */
export const modesFor = (mayBuild) => (mayBuild ? MODES.filter((m) => !PUT_AWAY.includes(m)) : ["ask"]);

/** A mode this person may use: anything else is Ask. */
export const allowedMode = (mode, mayBuild) => (modesFor(mayBuild).includes(mode) ? mode : "ask");

/** What the scope chip in the composer is about: confirmed types (Ask, Query), datasets (Model), a dataset or a pipeline (Pipeline), one object type (Meanings). */
export const scopeKind = (mode) => (mode === "model" ? "datasets" : mode === "pipeline" ? "target" : mode === "meanings" ? "type" : "types");

/** The modes whose message is optional: the scope alone says what to do (the datasets for Model, the type for Meanings). */
export const textOptional = (mode) => mode === "model" || mode === "meanings";

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
    operators: (s.operators ?? []).map((o) => o.text), failures: s.failures ?? {},
  }));
  const counted = steps.length > 0 && steps.every((s) => s.rowsOut != null && s.rowsIn);
  const flow = counted ? [sum(steps[0].rowsIn), ...steps.map((s) => s.rowsOut)] : [];
  const questions = d.questions ?? [];
  const chosen = (q) => (answers[q.id] ?? []).length > 0;
  const open = questions.filter((q) => !chosen(q));
  // the service works the assumptions and the self-check out by code; an older one sends none, and then they are worked out here from the same facts
  const served = Array.isArray(d.assumptions)
    ? d.assumptions.map((a) => ({ text: a.text, state: a.status === "open" ? "open" : "confirmed", id: a.question, definition: a.definition ?? null, by: a.by ?? null }))
    : null;
  const assumptions = served ?? [
    ...(d.cites ?? []).map((c) => ({ text: c.text, state: "confirmed" })),
    ...questions.map((q) => ({ text: q.ask, state: chosen(q) ? "answered" : "open", id: q.id, answer: chosen(q) ? (q.options ?? []).filter((o) => answers[q.id].includes(o.value)).map((o) => o.text).join(", ") : "" })),
  ];
  const ok = Boolean(d.check?.ok);
  const openCount = served ? served.filter((a) => a.state === "open").length : open.length;
  const done = [];
  const notDone = [];
  if (ok) done.push({ key: "columns" });
  if (ok && d.check.dry_run) done.push({ key: "dry", text: d.check.dry_run });
  if (counted) done.push({ key: "counts", count: steps.length });
  if ((d.cites ?? []).length) done.push({ key: "cites", count: d.cites.length });
  if (!ok) notDone.push({ key: "failed", text: d.check?.error ?? "" });
  if (openCount) notDone.push({ key: "open", count: openCount });
  const failing = steps.filter((s) => Object.keys(s.failures).length).length;
  if (failing) notDone.push({ key: "stepFailures", count: failing });
  notDone.push({ key: "fullRun" }, { key: "saved" });
  const canApply = ok && steps.length > 0 && openCount === 0;
  const blocked = !ok ? "failed" : steps.length === 0 ? "empty" : openCount ? "open" : "";
  return { steps, flow, assumptions, open: openCount, done: d.self_check?.done ?? done, notDone: d.self_check?.not_done ?? notDone, canApply, blocked };
}

/** The proposal card for the type suggester's answer ({proposed: [{id, name}], rejected: [{name, reason}]}) and each proposed type as read back
 * (the type's own page data: key, properties with what each is needed for; `basis` too when the page data carries it). Each type carries its basis; the rejected carry their reasons. */
export function proposalCard(result, details = [], acked = {}) {
  const byId = Object.fromEntries((details ?? []).filter(Boolean).map((x) => [x.id, x]));
  const types = (result?.proposed ?? []).map((p) => {
    const x = byId[p.id] ?? {};
    return {
      id: p.id, name: p.name, dataset: x.dataset ?? p.dataset ?? "", key: x.key ?? p.key ?? [], basis: p.basis ?? x.basis ?? "", leftOut: p.left_out ?? [], version: x.version ?? null,
      // the key columns are shown as the key, not as properties
      properties: (x.properties ?? []).filter((q) => !q.key).map((q) => ({ column: q.column, name: q.name && q.name !== q.column ? q.name : "", why: q.needed_for ?? "" })),
      loaded: Boolean(byId[p.id]),
    };
  });
  const rejected = (result?.rejected ?? []).map((r) => ({ name: r.name, reason: r.reason }));
  const assumptions = (result?.proposed ?? []).flatMap((p) => (p.assumptions ?? []).map((a) => ({ id: a.id, type: p.id, text: a.text, definition: a.definition ?? null, by: a.by ?? null, state: a.status === "open" ? (acked[a.id] ? "answered" : "open") : "confirmed" })));
  const open = assumptions.filter((a) => a.state === "open").length;
  const done = result?.self_check?.done ?? (types.length ? [{ key: "checked", count: types.length }, { key: "kept", count: types.length }] : []);
  const notDone = result?.self_check?.not_done ?? [...(types.length ? [{ key: "confirmed" }] : []), ...(rejected.length ? [{ key: "dropped", count: rejected.length }] : [])];
  // an open assumption blocks Propose until it is acknowledged, and nothing else
  return { types, rejected, assumptions, open, done, notDone, canPropose: types.some((x) => x.loaded) && open === 0, blocked: open ? "open" : "" };
}

/** The payload that proposes a model-suggested type through the normal update path (what saving it from the type's own form sends), or null if it is not fully read back. */
export function proposePayload(type) {
  if (!type?.id || !type.dataset || !type.key?.length || type.version == null) return null;
  const props = type.properties ?? [];
  const enums = Object.fromEntries(props.filter((p) => p.enum && p.meanings?.values?.length).map((p) => [p.column, p.meanings.values.map((v) => ({ value: v.value, label: v.label }))]));
  return {
    id: type.id, version: type.version, english_name: type.id, name: type.name, description: type.description ?? "", dataset: type.dataset, key: type.key,
    properties: props.map((p) => ({ column: p.column, name: p.name || p.column, type: p.type, enum: Boolean(p.enum) })), enums,
    ...(type.receipt ? { draft_receipt: type.receipt } : {}),   // the service's receipt for this suggestion: it decides whether the saved type counts as drafted by the assistant
  };
}

/** The Meanings card for the draft of one type (the response of the meanings-draft endpoint) and the person's keep/skip choices ({"column|value": boolean}).
 * Each column lists its codes with the drafted meaning, what is on file, and flags worked out by code. A drafted meaning is kept unless the person skips it;
 * a confirmed column has no drafts and is only shown. {columns, kept, canApply, blocked, ...}. */
export function meaningsCard(result, choices = {}) {
  const columns = (result?.columns ?? []).map((c) => {
    const unmeant = new Set(c.checks?.no_meaning ?? []);
    const values = c.values.map((v) => {
      const flags = [];
      if (v.draft && v.current && v.current !== v.draft.label) flags.push("differs");
      if (v.draft && !v.pattern) flags.push("noPattern");
      if (unmeant.has(v.value)) flags.push("unmeant");
      const keep = Boolean(v.draft) && (choices[`${c.column}|${v.value}`] ?? true);
      return { value: v.value, rows: v.rows, label: v.draft?.label ?? "", description: v.draft?.description ?? "", basis: v.draft?.basis ?? "", current: v.current ?? "", facts: v.facts ?? [], flags, hasDraft: Boolean(v.draft), keep };
    });
    return { column: c.column, rows: c.rows, confirmed: Boolean(c.confirmed), values, gone: c.checks?.never_seen ?? [], kept: values.filter((v) => v.keep).length };
  });
  const kept = columns.reduce((a, c) => a + c.kept, 0);
  return {
    columns, kept, canApply: kept > 0, blocked: kept > 0 ? "" : "none", skipped: result?.skipped ?? [], rejected: result?.rejected ?? [],
    assumptions: (result?.assumptions ?? []).map((a) => ({ id: a.id, text: a.text, state: a.status === "open" ? "open" : "confirmed", definition: a.definition ?? null, by: a.by ?? null })),
    done: result?.self_check?.done ?? [], notDone: result?.self_check?.not_done ?? [],
  };
}

/** What Apply sends for a Meanings card: one meanings update per column with kept values, exactly what the type's own meanings editor sends
 * ({id, column, values: [{value, label, description}]}), so the service runs the same checks. Skipped values and confirmed columns send nothing. */
export function meaningsPayloads(result, choices = {}) {
  return meaningsCard(result, choices).columns.filter((c) => !c.confirmed && c.kept).map((c) => ({
    id: result.type, column: c.column, values: c.values.filter((v) => v.keep).map((v) => ({ value: v.value, label: v.label, description: v.description })),
  }));
}

// Handing a draft to the pipeline editor: the steps wait in this tab's session storage under the pipeline's name until the editor opens it,
// which applies them the way the editor's own AI panel does. A draft for a pipeline that does not exist yet waits under "new:<dataset>"
// and is moved to the pipeline's name when the person creates it.
const stashKey = (target) => `assistant-draft:${target}`;
const receiptKey = (target) => `assistant-receipt:${target}`;
const turnKey = (target) => `assistant-turn:${target}`;   // the kept assistant turn the card came from, marked "saved" when the editor saves
export function stashDraft(storage, target, steps, receipt, turn) {
  storage.setItem(stashKey(target), JSON.stringify(steps));
  if (receipt) storage.setItem(receiptKey(target), receipt);
  else storage.removeItem(receiptKey(target));
  if (turn != null) storage.setItem(turnKey(target), String(turn));
  else storage.removeItem(turnKey(target));
}
/** The steps waiting for `target`, the service's receipt for that draft and the kept turn it came from, taken out together; null when there are no steps. */
export function takeHandover(storage, target) {
  const receipt = storage.getItem(receiptKey(target));
  storage.removeItem(receiptKey(target));
  const turn = storage.getItem(turnKey(target));
  storage.removeItem(turnKey(target));
  const steps = takeDraft(storage, target);
  return steps ? { steps, receipt: receipt || null, turn: turn ? Number(turn) : null } : null;
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
  const receipt = storage.getItem(receiptKey(from));
  storage.removeItem(receiptKey(from));
  if (receipt) storage.setItem(receiptKey(to), receipt);
  const turn = storage.getItem(turnKey(from));
  storage.removeItem(turnKey(from));
  if (turn) storage.setItem(turnKey(to), turn);
}

/** The pipeline's step the assistant works from when the person names a pipeline: the last step that is not an output. */
export const defaultSelected = (spec) => [...(spec?.steps ?? [])].reverse().find((s) => s.type !== "output")?.id ?? null;
/** The spec the assistant drafts over when the scope is a dataset: one input step, the way a new pipeline starts. */
export const datasetSpec = (dataset) => ({ steps: [{ id: "in1", type: "input", dataset }] });

// The thread of this tab, kept in session storage per user so it survives going to another page and back (and a reload), and goes with the tab.
const threadKey = (user) => `assistant-thread:${user}`;
export function saveThread(storage, user, turns) {
  if (!user) return;
  // a turn still waiting for the service cannot be resumed, so it is not kept
  const keep = (turns ?? []).filter((x) => x.status !== "thinking");
  try {
    if (keep.length) storage.setItem(threadKey(user), JSON.stringify(keep));
    else storage.removeItem(threadKey(user));
  } catch {
    // storage full or unavailable: the thread simply stays in memory
  }
}
export function loadThread(storage, user) {
  if (!user) return [];
  try {
    const list = JSON.parse(storage.getItem(threadKey(user)) ?? "[]");
    if (!Array.isArray(list)) return [];
    return list.filter((x) => x && typeof x.id === "string").map((x) => (x.plan ? { ...x, plan: { ...x.plan, busy: false } } : x.proposal ? { ...x, proposal: { ...x.proposal, busy: false } } : x.meanings ? { ...x, meanings: { ...x.meanings, busy: false } } : x));
  } catch {
    return [];
  }
}

/** The version number of a card made by revising turn `revises`: one more than the highest version already in its chain. */
export function nextVersion(turns, revises) {
  if (!revises) return 1;
  const byId = Object.fromEntries((turns ?? []).map((x) => [x.id, x]));
  let root = byId[revises];
  while (root?.revises && byId[root.revises]) root = byId[root.revises];
  const chain = (turns ?? []).filter((x) => x.kind === "pipeline" && (x.id === root?.id || x.revises === root?.id || (x.revises && byId[x.revises]?.revises === root?.id)));
  return Math.max(1, ...chain.map((x) => x.version ?? 1)) + 1;
}

/** What each action of a plan card can do. Only Apply is ever blocked by the draft (an open question, a failed check, an applied or replaced card);
 * Revise and Discard stay available, except on a card that was replaced or discarded, which is frozen. `reason` is the key of the sentence that says why Apply is off. */
export function actionState(card, plan = {}) {
  const frozen = plan.supersededBy ? "superseded" : plan.discarded ? "discarded" : plan.applied ? "applied" : "";
  const reason = frozen || (plan.busy ? "busy" : card.blocked);
  const closed = frozen === "superseded" || frozen === "discarded";
  return { apply: { enabled: !reason && card.canApply, reason: reason || (card.canApply ? "" : card.blocked) }, revise: !closed, discard: !frozen };
}
