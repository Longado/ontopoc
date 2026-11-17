// The dataset list and page, as plain functions: search, sort, and where a dataset comes from and who uses it, as links.
import { sourceOrigin } from "./sourceModel.js";

const enc = encodeURIComponent;

const sourceText = (origin) => {
  const s = sourceOrigin(origin);
  if (s) return `${s.source} ${s.table}`;
  const p = /^pipeline:(.+?)(?:@run\d+)?$/.exec(origin ?? "");
  return p ? p[1] : origin === "upload" ? "上传" : "";
};

/** The datasets whose name or source contains what was typed (case ignored); nothing typed keeps them all. */
export function filterDatasets(list, query) {
  const q = String(query ?? "").trim().toLowerCase();
  if (!q) return list;
  return list.filter((d) => `${d.name} ${sourceText(d.origin)}`.toLowerCase().includes(q));
}

/** A sorted copy. `key`: name, rows, columns, version, updated_at (the time text of the service sorts as text); `dir`: asc or desc. */
export function sortDatasets(list, key, dir = "asc") {
  const sign = dir === "desc" ? -1 : 1;
  const cmp = key === "name" ? (a, b) => a.name.localeCompare(b.name, "zh")
    : key === "updated_at" ? (a, b) => String(a.updated_at ?? "").localeCompare(String(b.updated_at ?? ""))
      : (a, b) => (a[key] ?? 0) - (b[key] ?? 0);
  return [...list].sort((a, b) => sign * cmp(a, b));
}

/** Where a dataset came from: {kind: upload | source | pipeline | other, label, href}. href is null where there is no page to go to (an upload; a pipeline the person may not see). */
export function originLink(origin) {
  if (origin === "upload") return { kind: "upload", label: "上传", href: null };
  const s = sourceOrigin(origin);
  if (s) return { kind: "source", label: `数据源 ${s.source}（表 ${s.table}）`, href: `#/sources/${enc(s.source)}` };
  if (origin === "pipeline") return { kind: "pipeline", label: "管道（你没有权限看）", href: null };
  const p = /^pipeline:(.+?)(?:@run(\d+))?$/.exec(origin ?? "");
  if (p) return { kind: "pipeline", label: `管道 ${p[1]}${p[2] ? `（第 ${p[2]} 次运行）` : ""}`, href: `#/pipelines/${enc(p[1])}` };
  return { kind: "other", label: "建模运行", href: null };
}

/** The things that read a dataset ({kind: "管道" | "对象类型", name}) with the page each opens. A type is found by its id, which `typeIds` maps from its name; an unknown one has no link. */
export function readerLinks(readers, typeIds = {}) {
  return readers.map((r) => {
    if (r.kind === "管道") return { ...r, href: `#/pipelines/${enc(r.name)}` };
    const id = typeIds[r.name];
    return { ...r, href: id ? `#/types/${enc(id)}/props` : null };
  });
}
