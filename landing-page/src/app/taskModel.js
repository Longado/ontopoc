// The 任务 page: each task of the list as the words of one table row.
import { hrefFor } from "./routeModel.js";
import { modeLabel, versionChangeText } from "./versionText.js";

export const STATE_LABEL = { running: "进行中", done: "完成", failed: "失败", interrupted: "中断" };
export const KIND_LABEL = { draft: "起草本体", upload: "上传数据集" };

/** "1 分 30 秒", "45 秒"; "" when either time is missing or unreadable. */
export function durationText(from, to) {
  const seconds = Math.round((Date.parse(to) - Date.parse(from)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  return seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`;
}

function uploadText(t) {
  if (!t.created_version) return `${modeLabel(t.mode)}：没有变化，没有新版本`;
  const c = t.changes;
  return `${modeLabel(t.mode)}：${versionChangeText({ mode: t.mode, rows: t.rows, changed: c.changed, added: c.added, unchanged: c.unchanged, blank_kept: c.blank_kept, replaced_rows: c.replaced_rows })}，第 ${t.version} 版`;
}

function draftText(t) {
  if (t.state === "failed") return t.error || "没有说明原因";
  if (t.state === "interrupted") return "服务在中途重启过，这次中断了，需要重新上传文件";
  if (t.state === "done") return durationText(t.at, t.ended_at) ? `用了 ${durationText(t.at, t.ended_at)}` : "";
  return "";
}

/** One task as a row: what it is, what it is called, its state (bad: shown as a problem), and a sentence about it. */
export function taskRow(t) {
  return {
    key: t.id,
    at: t.at,
    kind: KIND_LABEL[t.kind] ?? t.kind,
    title: t.title,
    // an upload opens its dataset's versions; a modelling job opens the old workbench, where its run is kept (it has no page of its own yet)
    href: t.kind === "upload" ? hrefFor({ page: "dataset", name: t.title, tab: "versions" }) : "/legacy.html",
    state: STATE_LABEL[t.state] ?? t.state,
    bad: t.state === "failed" || t.state === "interrupted",
    who: t.who ?? "",
    text: t.kind === "upload" ? uploadText(t) : draftText(t),
  };
}

export const anyRunning = (tasks) => tasks.some((t) => t.state === "running");
