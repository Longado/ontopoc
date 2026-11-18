// The assistant's history rail as plain functions, so they can be tested without a browser.
// The rail lists the saved Ask questions and the builder-mode turns (query, model, pipeline, and any mode that comes after) together.
// A rail item is {key, mode, question, asked_at, id, turn}: `turn` is true for a builder-mode turn (opened in place), false for an Ask question (opened at #/qa/<id>).
import { MODES } from "./assistantModel.js";

/** The saved Ask questions and the builder-mode turns as one list of rail items. */
export function railItems(askHistory, turns) {
  const asks = (askHistory ?? []).map((h) => ({ ...h, key: `a${h.id}`, mode: "ask", turn: false }));
  const made = (turns ?? []).map((x) => ({ id: x.id, key: `t${x.id}`, mode: x.mode, question: x.message, asked_at: x.asked_at, outcome: x.outcome ?? null, turn: true }));
  return [...asks, ...made];
}

/** The modes to offer as a filter: every mode this assistant has (read from MODES, not a fixed four) and any mode a stored turn carries; none when there is only one to tell apart. */
export function filterModes(items) {
  const present = new Set((items ?? []).map((x) => x.mode));
  const listed = [...MODES.filter((m) => present.has(m)), ...[...present].filter((m) => !MODES.includes(m)).sort()];
  return listed.length > 1 ? listed : [];
}

/** The items of one mode, or all of them when no mode is chosen. */
export const filterByMode = (items, mode) => (mode ? (items ?? []).filter((x) => x.mode === mode) : (items ?? []));

/** What "Draft again" puts back in the composer: the mode, the message and the scope as they were. It only fills the composer; nothing is run and nothing is applied.
 * `datasets` and `target` are what the person still sees (a hidden entry has no name and is left out). */
export function draftAgain(turn) {
  const scope = turn?.scope ?? {};
  const datasets = (scope.datasets ?? []).filter((d) => !d.hidden && d.name).map((d) => d.name);
  const target = scope.target && !scope.target.hidden && scope.target.name ? { kind: scope.target.kind, name: scope.target.name, label: scope.target.label || scope.target.name } : null;
  return { mode: turn?.mode ?? "ask", text: turn?.message ?? "", datasets, target };
}

/** The scope a turn is kept with, from what the composer had when it was sent: {datasets} (Model), {target} (Pipeline), nothing for a query. */
export function scopeOf(mode, { chosen = [], target = null, type = null } = {}) {
  if (mode === "model") return { datasets: [...chosen] };
  if (mode === "meanings" && type) return { types: [type.id] };
  if (mode === "pipeline" && target) return { target: { kind: target.kind, name: target.name, label: target.label ?? target.name } };
  return {};
}

/** The outcome line of a rail item or an opened turn as {key, name}: applied / saved (as <name>) / not applied; null when nothing is known. */
export function outcomeLine(outcome) {
  if (!outcome?.state) return null;
  return { key: outcome.state, name: outcome.hidden ? "" : outcome.name ?? "" };
}

/** A thread whose one turn is a past builder-mode turn, shown read-only. */
export const isPast = (turn) => turn?.kind === "past";
/** A thread of one for a past turn opened from the rail. */
export const pastTurn = (turnId) => ({ id: `p${turnId}`, kind: "past", turnId, text: "", status: "done", record: null, error: "" });
