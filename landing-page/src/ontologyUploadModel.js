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
export function uploadPayload(files, purpose, ...contents) {
  const base64 = (i) => contents[i] ?? contents[0];
  if (files.length === 1) return { filename: files[0].name, content_base64: base64(0), purpose };
  return { files: files.map((f, i) => ({ filename: f.name, content_base64: base64(i) })), purpose };
}

export { ACCEPT };
