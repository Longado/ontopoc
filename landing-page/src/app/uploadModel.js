import { t } from "./i18n/index.js";

// The upload dialog's decisions, before anything is sent. A file whose name is already a dataset is never guessed about:
// the person says whether it makes a new dataset, updates one by key, or overwrites one.
export const MAX_TOTAL = 10 * 1024 * 1024;
export const ACCEPT = ".xlsx,.csv";
const MAX_NAME = 100;

export const stem = (filename) => filename.replace(/\.[^.]+$/, "").trim();
const suffix = (filename) => (filename.match(/\.[^.]+$/)?.[0] || "").toLowerCase();

export const sizeText = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** "" when these files can be sent, else why not. */
export function filesProblem(files) {
  if (!files.length) return t("data.upl.chooseFile");
  for (const file of files) {
    if (![".xlsx", ".csv"].includes(suffix(file.name))) return t("data.upl.onlyTypes", { file: file.name });
  }
  const total = files.reduce((n, f) => n + f.size, 0);
  return total > MAX_TOTAL ? t("data.upl.tooBig", { total: sizeText(total), max: sizeText(MAX_TOTAL) }) : "";
}

/**
 * What a file starts as. A free name is a new dataset. A taken name starts with nothing chosen, so the person has to say;
 * opened from a dataset's own page, that dataset is the target and the way is still theirs to pick.
 */
export function firstChoice(filename, datasetNames, presetTarget = null) {
  const name = stem(filename);
  if (presetTarget) return { kind: null, name, target: presetTarget, keyColumns: [] };
  if (datasetNames.includes(name)) return { kind: null, name, target: name, keyColumns: [] };
  return { kind: "new", name, target: null, keyColumns: [] };
}

/** Switching the way keeps what still applies: the target stays, key columns go when the target changes. */
export const withKind = (choice, kind) => ({ ...choice, kind });
export const withTarget = (choice, target) => ({ ...choice, target, keyColumns: [] });
export const withKeyColumn = (choice, column, on) => ({
  ...choice,
  keyColumns: on ? [...choice.keyColumns.filter((c) => c !== column), column] : choice.keyColumns.filter((c) => c !== column),
});

/** Why this file's choice cannot be sent yet, or "". */
export function choiceProblem(filename, choice, datasetNames) {
  if (choice.kind === null) return t("data.upl.pickWay", { file: filename });
  if (choice.kind === "new") {
    const name = choice.name.trim();
    if (!name || name.length > MAX_NAME) return t("data.upl.needName", { file: filename, max: MAX_NAME });
    if (datasetNames.includes(name)) return t("data.upl.nameTaken", { file: filename, name });
    return "";
  }
  if (!choice.target) return t("data.upl.pickTarget", { file: filename });
  if (choice.kind === "update_by_key" && !choice.keyColumns.length) return t("data.upl.pickKeys", { file: filename });
  return "";
}

/** The first problem across all files, or "" — including two files that would write the same dataset. */
export function uploadProblem(files, choices, datasetNames) {
  const whole = filesProblem(files);
  if (whole) return whole;
  for (let i = 0; i < files.length; i += 1) {
    const why = choiceProblem(files[i].name, choices[i], datasetNames);
    if (why) return why;
  }
  const written = choices.map((c) => (c.kind === "new" ? c.name.trim() : c.target));
  const twice = written.find((name, i) => written.indexOf(name) !== i);
  return twice ? t("data.upl.twice", { name: twice }) : "";
}

/** The request body; the new-name field is sent only when the person changed it from the file's name. */
export function uploadPayload(who, files, contents, choices) {
  return {
    who: who.trim(),
    files: files.map((file, i) => {
      const choice = choices[i];
      const base = { filename: file.name, content_base64: contents[i] };
      if (choice.kind === "new") return choice.name.trim() === stem(file.name) ? base : { ...base, name: choice.name.trim() };
      if (choice.kind === "overwrite") return { ...base, target: choice.target, mode: "overwrite" };
      return { ...base, target: choice.target, mode: "update_by_key", key_columns: choice.keyColumns };
    }),
  };
}

const KIND_WORDS = ["type", "view", "meaning", "relation", "derived", "pipeline", "action"];

/** Whether the upload changes a dataset that exists, so it is worth asking what that sends back before it is made. */
export const changesExisting = (payload) => payload.files.some((f) => f.mode === "overwrite" || f.mode === "update_by_key");

/** The definitions an upload would send back to needs another look, one line each: what it is and why. */
export const movedLines = (moved) => moved.map((m) => ({ key: m.element, what: t("data.upl.moved", { kind: KIND_WORDS.includes(m.kind) ? t(`data.upl.kind.${m.kind}`) : m.kind, title: m.title }), reason: m.reason }));

/** The three ways a file can go in, with their words in the current language (getters: read at use time). */
const way = (kind) => ({ kind, get label() { return t(`data.upl.way.${kind}`); }, get consequence() { return t(`data.upl.way.${kind}.text`); } });
const WAY = { new: way("new"), update_by_key: way("update_by_key"), overwrite: way("overwrite") };

/** The ways a file can go in: a new dataset is always offered; updating one that exists is folded away ("Update an existing dataset") and is not offered at all when there is no dataset to update. */
export const waysFor = (datasetNames) => ({ primary: [WAY.new], folded: datasetNames.length ? [WAY.update_by_key, WAY.overwrite] : [] });

/** Whether a file's fold of update ways starts open: when the file's name is a dataset already (nothing chosen yet) or the person chose an update. */
export const updateWays = (choice) => ({ open: choice.kind === null || choice.kind === "update_by_key" || choice.kind === "overwrite" });

/** The buttons after an upload: look at the dataset (the list when several were made), and make an object type from it when a new dataset was made.
 * The type form does not take a dataset in its address yet, so that link goes to the empty form. */
export function afterUpload(results) {
  const first = results[0];
  const view = { label: t(results.length === 1 ? "data.upl.view" : "data.upl.viewAll"), href: results.length === 1 ? `#/datasets/${encodeURIComponent(first.name)}/fields` : "#/datasets" };
  return results.some((r) => r.mode === "new" || !r.mode) ? [view, { label: t("data.upl.makeType"), href: "#/types/new" }] : [view];
}

const blankText = (n) => (n ? t("data.upl.blank", { count: n }) : "");

/** One saved file as a sentence for the dialog. A skipped update is a plain line, not an error. */
export function resultLine(r) {
  const failed = r.key_check?.status === "failed" ? t("data.upl.keyFailed") : "";
  if (r.mode === "overwrite" && !r.created_version) return t("data.upl.r.sameOverwrite", { name: r.name });
  const same = r.same_as ? t("data.upl.r.same", { n: r.same_as }) : "";
  if (r.mode === "update_by_key" && !r.created_version) return t("data.upl.r.noChange", { name: r.name, blank: r.changes.blank_kept ? t("data.upl.r.parens", { text: blankText(r.changes.blank_kept) }) : "" });
  if (r.mode === "update_by_key") {
    const c = r.changes;
    return t("data.upl.r.update", { name: r.name, changed: c.changed, added: c.added, unchanged: c.unchanged, count: r.rows, version: r.version, same, blank: r.changes.blank_kept ? `${t("data.semi")}${blankText(r.changes.blank_kept)}` : "", failed });
  }
  if (r.mode === "overwrite") return t("data.upl.r.overwrite", { name: r.name, count: r.rows, version: r.version, same });
  return t("data.upl.r.new", { name: r.name, count: r.rows });
}
