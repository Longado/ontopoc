// What may be uploaded together, said before anything is sent: tables go in one batch, a document goes alone.
import { ACCEPT, fileProblem } from "./ontologyStudioModel.js";

export const MAX_TOTAL = 10 * 1024 * 1024;
const DOCUMENT = [".md", ".txt", ".docx", ".pdf"];
const suffix = (name) => (name.match(/\.[^.]+$/)?.[0] || "").toLowerCase();
export const isDoc = (file) => DOCUMENT.includes(suffix(file.name));

export const sizeText = (n) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** "" when this batch can be sent, else why not. */
export function batchProblem(files) {
  if (!files.length) return "先选择文件";
  for (const file of files) {
    const why = fileProblem(file);
    if (why) return `${file.name}：${why}`;
  }
  const documents = files.filter(isDoc);
  if (documents.length && files.length > 1) {
    const names = documents.map((d) => d.name).join("、");
    return documents.length === files.length ? `一次只能传一份文档（${names}）；几张表可以一起传`
      : `${names}：一次只能传数据表，或者单独传一份文档，不能混在一起`;
  }
  const total = files.reduce((n, f) => n + f.size, 0);
  if (total > MAX_TOTAL) return `这些文件一共 ${sizeText(total)}，上限 ${sizeText(MAX_TOTAL)}，请分批上传`;
  return "";
}

export function batchSummary(files) {
  const total = files.reduce((n, f) => n + f.size, 0);
  const together = files.length > 1 ? " · 会放在一起建模" : "";
  return `${files.length} 个文件 · ${sizeText(total)}${together}`;
}

/** One file keeps the request the service has always taken; several go in the batch shape. */
export function uploadPayload(files, purpose, contents, mode = null) {
  const base64 = (i) => contents[i] ?? contents[0];
  const extra = mode ? { mode } : {};
  if (files.length === 1) return { filename: files[0].name, content_base64: base64(0), purpose, ...extra };
  return { files: files.map((f, i) => ({ filename: f.name, content_base64: base64(i) })), purpose, ...extra };
}

// The preview of what goes to the model: the counts code took on every row, read as plain sentences.
export function previewFactText(f) {
  if (f.filled === undefined) return "—";   // a service from before the counts
  if (!f.filled) return "全空";
  if (f.distinct === 1 && f.filled > 1) return `${f.filled} 个有值 · 全是同一个值`;
  return `${f.filled} 个有值 · ${f.distinct} 种${f.unique ? "，各不相同" : ""}`;
}

export function previewKeysText(src) {
  if (src.unique_columns?.length) return `每行都不同的列：${src.unique_columns.join("、")}`;
  if (src.unique_pairs?.length) return `没有一列每行都不同；两列合起来每行都不同的有：${src.unique_pairs.map((p) => p.join(" + ")).join("、")}`;
  if (src.unique_pairs) return "每行都有值的列里，没有一列或两列合起来每行都不同";
  return src.unique_columns ? "没有一列每行都不同" : null;   // nothing at all: a one-row table
}

export const previewLinkText = (l) => `${l.field} 的 ${l.of} 个不同值里，有 ${l.found} 个在 ${l.to_table}.${l.to_field}`;

export { ACCEPT };
