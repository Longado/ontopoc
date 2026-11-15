// The runs kept on this machine, as a library: one folder per file, newest first, each run named by its purpose.
export function folderLabel(file) {
  if (!file) return "没有文件名";
  const parts = file.split("、");
  return parts.length > 1 ? `${parts[0]} 等 ${parts.length} 份` : file;
}

export function runLabel(run) {
  const name = run.purpose?.trim() || "没写建模目的";
  if (run.status && run.status !== "auto_built_verified") return `${name}（没通过核验）`;
  return run.confirmed ? `${name} ✓` : name;
}

/** Runs arrive newest first; a folder takes the place of its newest run. */
export function groupRuns(runs) {
  const folders = new Map();
  for (const r of runs) {
    if (!folders.has(r.file)) folders.set(r.file, { file: r.file, label: folderLabel(r.file), runs: [] });
    folders.get(r.file).runs.push(r);
  }
  return [...folders.values()];
}
