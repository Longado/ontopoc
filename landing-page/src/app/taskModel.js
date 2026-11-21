import { t as say } from "./i18n/index.js";
// The Tasks page: each task of the list as the words of one table row.
import { hrefFor } from "./routeModel.js";
import { modeLabel, noChangeText, versionChangeText } from "./versionText.js";

const STATES = ["running", "done", "failed", "interrupted"];
const KINDS = ["draft", "upload", "suggest"];
const stateLabel = (state) => (STATES.includes(state) ? say(`data.task.state.${state}`) : state);
const kindLabel = (kind) => (KINDS.includes(kind) ? say(`data.task.kind.${kind}`) : kind);

/** "1 min 30 sec", "45 sec"; "" when either time is missing or unreadable. */
export function durationText(from, to) {
  const seconds = Math.round((Date.parse(to) - Date.parse(from)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  return seconds >= 60 ? say("data.task.minSec", { m: Math.floor(seconds / 60), s: seconds % 60 }) : say("data.task.sec", { s: seconds });
}

function uploadText(t) {
  if (t.mode === "deleted") return say("data.task.deleted", { versions: t.changes.versions, rows: t.changes.rows });
  if (!t.created_version) return t.mode === "overwrite" ? noChangeText({ mode: "overwrite" }) : say("data.task.noChange", { mode: modeLabel(t.mode) });
  const c = t.changes;
  return say("data.task.changed", { mode: modeLabel(t.mode), version: t.version, what: versionChangeText({ mode: t.mode, rows: t.rows, changed: c.changed, added: c.added, unchanged: c.unchanged, blank_kept: c.blank_kept, replaced_rows: c.replaced_rows, same_as: c.same_as }) });
}

function draftText(t) {
  if (t.state === "failed") return t.error || say("data.task.noReason");
  if (t.state === "interrupted") return say("data.task.restarted");
  if (t.state === "done") return durationText(t.at, t.ended_at) ? say("data.task.took", { duration: durationText(t.at, t.ended_at) }) : "";
  return "";
}

function suggestText(t) {
  if (t.state === "failed") return t.error || say("data.task.noReason");
  const made = t.proposed.length ? say("data.task.proposed", { names: t.proposed.map((p) => p.name).join(say("data.listSep")) }) : say("data.task.noneProposed");
  return t.rejected.length ? say("data.task.rejected", { made, names: t.rejected.map((r) => r.name).join(say("data.listSep")) }) : made;
}

/** One task as a row: what it is, what it is called, its state (bad: shown as a problem), and a sentence about it. */
export function taskRow(t) {
  return {
    key: t.id,
    at: t.at,
    kind: kindLabel(t.kind),
    title: t.title,
    // an upload opens its dataset's versions, a suggestion the types; a modelling job belongs to the earlier screen, which the team app does not link into
    href: t.mode === "deleted" ? null : t.kind === "upload" ? hrefFor({ page: "dataset", name: t.title, tab: "versions" }) : t.kind === "suggest" ? hrefFor({ page: "types" }) : null,   // a deleted dataset has no page
    state: stateLabel(t.state),
    bad: t.state === "failed" || t.state === "interrupted",
    who: t.who ?? "",
    text: t.kind === "upload" ? uploadText(t) : t.kind === "suggest" ? suggestText(t) : draftText(t),
  };
}

export const anyRunning = (tasks) => tasks.some((t) => t.state === "running");
