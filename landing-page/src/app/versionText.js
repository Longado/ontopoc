// The 版本 tab: each version's mode and counts in words, and the updates that wrote no version, in time order with them.
export const MODE_LABEL = { new: "新建", update_by_key: "按主键更新", overwrite: "覆盖", upload: "导入" };

export const modeLabel = (mode) => MODE_LABEL[mode] ?? "导入";

/** What a version changed, as the row of the version list says it. */
export function versionChangeText(v) {
  if (v.mode === "update_by_key") return `改 ${v.changed}，增 ${v.added}，未变 ${v.unchanged}${v.blank_kept ? `，${v.blank_kept} 个空格子保留原值` : ""}`;
  if (v.mode === "overwrite" && v.replaced_rows != null) return `原 ${v.replaced_rows} 行，现 ${v.rows} 行`;
  return `${v.rows} 行`;
}

/** An update that matched every row and changed none: one plain sentence. */
export const noChangeText = (u) => `按主键更新（${u.key_columns.join("、")}）：没有变化，没有新版本${u.blank_kept ? `（${u.blank_kept} 个空格子保留原值）` : ""}`;

/** Versions and skipped updates as one list, newest first; an update skipped in the same second as a version comes first. */
export function timeline(versions, skipped) {
  const rows = [
    ...versions.map((v) => ({ type: "version", at: v.at, ...v })),
    ...skipped.map((u) => ({ type: "no_change", ...u })),
  ];
  const rank = (r) => (r.type === "no_change" ? 1 : 0);
  return rows.sort((a, b) => (a.at === b.at ? rank(b) - rank(a) || (b.version ?? 0) - (a.version ?? 0) : a.at < b.at ? 1 : -1));
}
