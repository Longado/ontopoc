import React, { useState } from "react";
import { getDatasets } from "./api.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { UploadDialog } from "./UploadDialog.jsx";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";

export function DatasetList() {
  const [state, reload] = useLoad(getDatasets, []);
  const [uploading, setUploading] = useState(false);
  const mayBuild = canBuild(useAuth().user);   // the service refuses a viewer's upload anyway; the button is just not offered
  const datasets = state.data ?? [];
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: "数据" }, { label: "数据集" }]} title="数据集" sub="每个数据集是一张表，每次上传或同步会留下一个新版本。"
        actions={mayBuild && <button className="primary" onClick={() => setUploading(true)}>上传</button>} />
      {state.status === "error" && (
        <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>
      )}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !datasets.length && (mayBuild
        ? <EmptyState icon="upload" title="还没有数据集" text="放入 .xlsx 或 .csv 表格，就有了第一个数据集。" action={{ label: "上传", onClick: () => setUploading(true) }} />
        : <EmptyState icon="table" title="还没有数据集" text="建设者上传后会出现在这里。" />)}
      {datasets.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th className="num">行数</th>
                <th className="num">列数</th>
                <th className="num">版本</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr key={d.name}>
                  <td><a href={hrefFor({ page: "dataset", name: d.name, tab: "fields" })}>{d.name}</a></td>
                  <td className="num">{d.rows}</td>
                  <td className="num">{d.columns}</td>
                  <td className="num">{d.version}</td>
                  <td>{timeText(d.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {uploading && (
        <UploadDialog presetTarget={null} onClose={() => setUploading(false)} onDone={reload} />
      )}
    </main>
  );
}
