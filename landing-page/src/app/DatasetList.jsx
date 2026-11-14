import React, { useState } from "react";
import { getDatasets } from "./api.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { UploadDialog } from "./UploadDialog.jsx";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { useLoad } from "./useLoad.js";

export function DatasetList() {
  const [state, reload] = useLoad(getDatasets, []);
  const [uploading, setUploading] = useState(false);
  const mayBuild = canBuild(useAuth().user);   // the service refuses a viewer's upload anyway; the button is just not offered
  const datasets = state.data ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>数据集</h1>
        {mayBuild && <button className="primary" onClick={() => setUploading(true)}>上传</button>}
      </div>
      {state.status === "error" && (
        <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>
      )}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !datasets.length && <p className="muted">还没有数据集。{mayBuild ? "点“上传”放入 .xlsx 或 .csv 表格。" : "建设者上传后会出现在这里。"}</p>}
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
