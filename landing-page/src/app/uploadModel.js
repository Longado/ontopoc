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

const KIND_WORD = { type: "对象类型", view: "视图", meaning: "取值含义", relation: "关系", derived: "派生属性", pipeline: "管道", action: "行为" };

/** Whether the upload changes a dataset that exists, so it is worth asking what that sends back before it is made. */
export const changesExisting = (payload) => payload.files.some((f) => f.mode === "overwrite" || f.mode === "update_by_key");

/** The definitions an upload would send back to needs another look, one line each: what it is and why. */
export const movedLines = (moved) => moved.map((m) => ({ key: m.element, what: `${KIND_WORD[m.kind] ?? m.kind}「${m.title}」`, reason: m.reason }));

const WAY = {
  new: { kind: "new", label: "新数据集", consequence: "数据放进一个新的数据集，不动现有的。" },
  update_by_key: { kind: "update_by_key", label: "按主键更新", consequence: "对上主键的行改成新值，新主键的行追加；不会删除任何行。" },
  overwrite: { kind: "overwrite", label: "覆盖", consequence: "整张表换成新文件，写成新的一版；旧版本还留在版本页，但现在的行不会保留。" },
};

/** The ways a file can go in: a new dataset is always offered; updating one that exists is folded away ("更新已有数据集") and is not offered at all when there is no dataset to update. */
export const waysFor = (datasetNames) => ({ primary: [WAY.new], folded: datasetNames.length ? [WAY.update_by_key, WAY.overwrite] : [] });

/** Whether a file's fold of update ways starts open: when the file's name is a dataset already (nothing chosen yet) or the person chose an update. */
export const updateWays = (choice) => ({ open: choice.kind === null || choice.kind === "update_by_key" || choice.kind === "overwrite" });

/** The buttons after an upload: look at the dataset (the list when several were made), and make an object type from it when a new dataset was made.
 * The type form does not take a dataset in its address yet, so that link goes to the empty form. */
export function afterUpload(results) {
  const first = results[0];
  const view = { label: "查看数据集", href: results.length === 1 ? `#/datasets/${encodeURIComponent(first.name)}/fields` : "#/datasets" };
  return results.some((r) => r.mode === "new" || !r.mode) ? [view, { label: "用它建对象类型", href: "#/types/new" }] : [view];
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
