/** New versions of a client's file: offering the link, and drawing what changed. */

/** The kept run these files may be the next version of: same file names, latest run that verified. */
export function earlierVersionOf(runs, files) {
  if (!Array.isArray(runs) || !files.length) return null;
  const names = [...files.map((f) => f.name)].sort().join("|");
  const run = runs.find((r) => r.status === "auto_built_verified" && r.file && r.file.split("、").sort().join("|") === names);
  return run ? { saved_as: run.saved_as, file: run.file } : null;
}

/** One row per object, all drawn on one scale so a big change looks big next to a small one. */
export function versionRows(version) {
  const scale = Math.max(1, ...version.objects.flatMap((o) => [o.before, o.after]));
  return version.objects.map((o) => ({ ...o, changed: Boolean(o.added || o.removed), scale }));
}
