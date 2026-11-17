import React, { useState } from "react";
import { getDatasets } from "./api.js";
import { filterDatasets, originLink, sortDatasets } from "./datasetModel.js";
import { timeText } from "./format.js";
import { t, useT } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { UploadDialog } from "./UploadDialog.jsx";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { Icon } from "./ui/Icon.jsx";

const COLUMNS = [
  { key: "name", label: "name" },
  { key: "origin", label: "source", sortable: false },
  { key: "rows", label: "rows", num: true },
  { key: "columns", label: "columns", num: true },
  { key: "version", label: "version", num: true },
  { key: "used_by", label: "usedBy", num: true },
  { key: "updated_at", label: "updated" },
];

export function DatasetList() {
  useT();
  const [state, reload] = useLoad(getDatasets, []);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState({ key: "updated_at", dir: "desc" });
  const mayBuild = canBuild(useAuth().user);   // the service refuses a viewer's upload anyway; the button is just not offered
  const datasets = state.data ?? [];
  const shown = sortDatasets(filterDatasets(datasets, query), sort.key, sort.dir);
  const toggle = (key) => setSort(sort.key === key ? { key, dir: sort.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "name" ? "asc" : "desc" });
  const open = (name) => { window.location.hash = hrefFor({ page: "dataset", name, tab: "fields" }); };
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("data.crumb.data") }, { label: t("data.list.title") }]} title={t("data.list.title")} sub={t("data.list.sub")}
        actions={mayBuild && <button className="primary" onClick={() => setUploading(true)}>{t("data.list.upload")}</button>} />
      {state.status === "error" && (
        <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>
      )}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {state.data && !datasets.length && (mayBuild
        ? <EmptyState icon="upload" title={t("data.list.empty.title")} text={t("data.list.empty.text")} action={{ label: t("data.list.empty.action"), onClick: () => setUploading(true) }} />
        : <EmptyState icon="table" title={t("data.list.empty.title")} text={t("data.list.empty.viewer")} />)}
      {datasets.length > 0 && (
        <>
          <div className="toolbar list-tools">
            <label className="search-box">
              <Icon name="search" size={14} />
              <input type="search" value={query} placeholder={t("data.list.search")} aria-label={t("data.list.searchAria")} onChange={(e) => setQuery(e.target.value)} />
            </label>
            <span className="muted small">{query.trim() ? t("data.list.countOf", { shown: shown.length, total: datasets.length }) : t("data.list.count", { count: datasets.length })}</span>
          </div>
          <div className="table-wrap">
            <table className="clickable">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} className={c.num ? "num" : ""} aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                      {c.sortable === false ? t(`data.col.${c.label}`) : (
                        <button className="th-sort" onClick={() => toggle(c.key)}>{t(`data.col.${c.label}`)}<span aria-hidden="true">{sort.key === c.key ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}</span></button>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((d) => {
                  const from = originLink(d.origin);
                  return (
                    <tr key={d.name} onClick={(e) => { if (!e.target.closest("a, button")) open(d.name); }}>
                      <td><a className="name-link" href={hrefFor({ page: "dataset", name: d.name, tab: "fields" })}>{d.name}</a></td>
                      <td className="muted">{from.href && mayBuild ? <a href={from.href}>{from.label}</a> : from.label}</td>
                      <td className="num">{d.rows}</td>
                      <td className="num">{d.columns}</td>
                      <td className="num">{d.version}</td>
                      <td className="num">{d.used_by ? t("data.list.usedByCount", { count: d.used_by }) : <span className="faint">—</span>}</td>
                      <td className="muted">{timeText(d.updated_at)}</td>
                    </tr>
                  );
                })}
                {!shown.length && <tr><td colSpan={COLUMNS.length} className="muted">{t("data.list.noMatch", { query: query.trim() })}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
      {uploading && (
        <UploadDialog presetTarget={null} onClose={() => setUploading(false)} onDone={reload} />
      )}
    </main>
  );
}
