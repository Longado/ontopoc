import React, { useState } from "react";
import { getDatasets } from "./api.js";
import { filterDatasets, originLink, sortDatasets } from "./datasetModel.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { UploadDialog } from "./UploadDialog.jsx";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { Icon } from "./ui/Icon.jsx";

const COLUMNS = [
  { key: "name", label: "名称" },
  { key: "origin", label: "来源", sortable: false },
  { key: "rows", label: "行数", num: true },
  { key: "columns", label: "列数", num: true },
  { key: "version", label: "版本", num: true },
  { key: "used_by", label: "被用到", num: true },
  { key: "updated_at", label: "更新时间" },
];

export function DatasetList() {
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
      <PageHeader crumbs={[{ label: "数据" }, { label: "数据集" }]} title="数据集" sub="每个数据集是一张表，每次上传或同步会留下一个新版本。"
        actions={mayBuild && <button className="primary" onClick={() => setUploading(true)}>上传</button>} />
      {state.status === "error" && (
        <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>
      )}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !datasets.length && (mayBuild
        ? <EmptyState icon="upload" title="还没有数据集" text="上传 .xlsx 或 .csv 表格，或接入一个数据库，就有了第一个数据集。" action={{ label: "上传表格", onClick: () => setUploading(true) }} />
        : <EmptyState icon="table" title="还没有数据集" text="建设者上传后会出现在这里。" />)}
      {datasets.length > 0 && (
        <>
          <div className="toolbar list-tools">
            <label className="search-box">
              <Icon name="search" size={14} />
              <input type="search" value={query} placeholder="按名称或来源搜索" aria-label="搜索数据集" onChange={(e) => setQuery(e.target.value)} />
            </label>
            <span className="muted small">{query.trim() ? `${shown.length} / ${datasets.length} 个` : `共 ${datasets.length} 个`}</span>
          </div>
          <div className="table-wrap">
            <table className="clickable">
              <thead>
                <tr>
                  {COLUMNS.map((c) => (
                    <th key={c.key} className={c.num ? "num" : ""} aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                      {c.sortable === false ? c.label : (
                        <button className="th-sort" onClick={() => toggle(c.key)}>{c.label}<span aria-hidden="true">{sort.key === c.key ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}</span></button>
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
                      <td><a href={hrefFor({ page: "dataset", name: d.name, tab: "fields" })}>{d.name}</a></td>
                      <td className="muted">{from.href && mayBuild ? <a href={from.href}>{from.label}</a> : from.label}</td>
                      <td className="num">{d.rows}</td>
                      <td className="num">{d.columns}</td>
                      <td className="num">{d.version}</td>
                      <td className="num">{d.used_by ? `${d.used_by} 处` : <span className="faint">—</span>}</td>
                      <td>{timeText(d.updated_at)}</td>
                    </tr>
                  );
                })}
                {!shown.length && <tr><td colSpan={COLUMNS.length} className="muted">没有名称或来源含“{query.trim()}”的数据集。</td></tr>}
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
