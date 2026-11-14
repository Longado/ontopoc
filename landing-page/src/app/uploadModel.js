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
  if (!files.length) return "先选择文件";
  for (const file of files) {
    if (![".xlsx", ".csv"].includes(suffix(file.name))) return `${file.name}：数据集只收 .xlsx 和 .csv 文件`;
  }
  const total = files.reduce((n, f) => n + f.size, 0);
  return total > MAX_TOTAL ? `这些文件一共 ${sizeText(total)}，上限 ${sizeText(MAX_TOTAL)}，请分批上传` : "";
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
  if (choice.kind === null) return `${filename}：选一种方式：新数据集、按主键更新或覆盖`;
  if (choice.kind === "new") {
    const name = choice.name.trim();
    if (!name || name.length > MAX_NAME) return `${filename}：给新数据集起个名字（1 到 ${MAX_NAME} 个字）`;
    if (datasetNames.includes(name)) return `${filename}：已经有叫“${name}”的数据集，请改名，或选择更新或覆盖`;
    return "";
  }
  if (!choice.target) return `${filename}：选一个要更新的数据集`;
  if (choice.kind === "update_by_key" && !choice.keyColumns.length) return `${filename}：选出主键列`;
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
  return twice ? `有两个文件都要写入“${twice}”，一次上传里一个数据集只能写一次` : "";
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

const blankText = (n) => (n ? `新文件里 ${n} 个空格子，保留了原值` : "");

/** One saved file as a sentence for the dialog. A skipped update is a plain line, not an error. */
export function resultLine(r) {
  const failed = r.key_check?.status === "failed" ? "；主键检查没通过" : "";
  if (r.mode === "overwrite" && !r.created_version) return `${r.name}：内容和当前版本完全一样，没有新版本`;
  const same = r.same_as ? `；内容同第 ${r.same_as} 版` : "";
  if (r.mode === "update_by_key" && !r.created_version) return `${r.name}：没有变化，没有新版本${r.changes.blank_kept ? `（${blankText(r.changes.blank_kept)}）` : ""}`;
  if (r.mode === "update_by_key") {
    const c = r.changes;
    return `${r.name}：按主键更新，改 ${c.changed}、增 ${c.added}、未变 ${c.unchanged}；现在 ${r.rows} 行，第 ${r.version} 版${same}${r.changes.blank_kept ? `；${blankText(r.changes.blank_kept)}` : ""}${failed}`;
  }
  if (r.mode === "overwrite") return `${r.name}：已覆盖，现在 ${r.rows} 行，第 ${r.version} 版${same}`;
  return `${r.name}：新建，${r.rows} 行`;
}
