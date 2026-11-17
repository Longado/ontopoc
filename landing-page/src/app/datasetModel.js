// The dataset list and page, as plain functions: search, sort, and where a dataset comes from and who uses it, as links.
import { t } from "./i18n/index.js";
import { PIPELINE_READER } from "./serverWords.js";
import { sourceOrigin } from "./sourceModel.js";

const enc = encodeURIComponent;

const sourceText = (origin) => {
  const s = sourceOrigin(origin);
  if (s) return `${s.source} ${s.table}`;
  const p = /^pipeline:(.+?)(?:@run\d+)?$/.exec(origin ?? "");
  return p ? p[1] : origin === "upload" ? t("data.origin.upload") : "";
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
  if (origin === "upload") return { kind: "upload", label: t("data.origin.upload"), href: null };
  const s = sourceOrigin(origin);
  if (s) return { kind: "source", label: t("data.origin.source", { source: s.source, table: s.table }), href: `#/sources/${enc(s.source)}` };
  if (origin === "pipeline") return { kind: "pipeline", label: t("data.origin.pipelineHidden"), href: null };
  const p = /^pipeline:(.+?)(?:@run(\d+))?$/.exec(origin ?? "");
  if (p) return { kind: "pipeline", label: t(p[2] ? "data.origin.pipelineRun" : "data.origin.pipeline", { name: p[1], run: p[2] }), href: `#/pipelines/${enc(p[1])}` };
  return { kind: "other", label: t("data.origin.modeling"), href: null };
}

/** The things that read a dataset ({kind: the service's word for a pipeline or an object type, name}) with the page each opens. A type is found by its id, which `typeIds` maps from its name; an unknown one has no link. */
export function readerLinks(readers, typeIds = {}) {
  return readers.map((r) => {
    if (r.kind === PIPELINE_READER) return { ...r, href: `#/pipelines/${enc(r.name)}` };
    const id = typeIds[r.name];
    return { ...r, href: id ? `#/types/${enc(id)}/props` : null };
  });
}
