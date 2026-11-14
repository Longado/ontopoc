import React, { useEffect, useState } from "react";
import { createPipeline, getDatasets, getPipelines } from "./api.js";
import { timeText } from "./format.js";
import { STATUS_LABEL, pipelineStateText } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

export function PipelineState({ item }) {
  return <span className={`state state-${item.state}`}>{pipelineStateText(item)}</span>;
}

export function PipelinesPage() {
  const [state, reload] = useLoad(getPipelines, []);
  const pipelines = state.data ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>管道</h1>
        <a className="button primary" href={hrefFor({ page: "pipelinenew" })}>新建管道</a>
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !pipelines.length && <p className="muted">还没有管道。新建一条，把几个数据集连起来、算出新的数据集。</p>}
      {pipelines.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>名称</th><th>状态</th><th>最近一次运行</th><th>输出</th><th>创建人</th></tr>
            </thead>
            <tbody>
              {pipelines.map((p) => (
                <tr key={p.id}>
                  <td><a href={hrefFor({ page: "pipeline", name: p.id, view: "edit" })}>{p.name}</a></td>
                  <td><PipelineState item={p} /></td>
                  <td>
                    {p.last_run ? (
                      <a href={hrefFor({ page: "pipeline", name: p.id, view: "run", run: p.last_run.id })}>
                        {STATUS_LABEL[p.last_run.status] ?? p.last_run.status}，{timeText(p.last_run.started_at)}，{p.last_run.who ?? "未署名"}
                      </a>
                    ) : <span className="faint">还没运行过</span>}
                  </td>
                  <td>
                    {p.outputs.length ? p.outputs.map((o) => (
                      <span key={o.dataset} className="output-chip">
                        <a href={hrefFor({ page: "dataset", name: o.dataset, tab: "fields" })}>{o.dataset}</a>
                        {o.stale && <span className="warn small"> {o.word}</span>}
                      </span>
                    )) : <span className="faint">没有</span>}
                  </td>
                  <td>{p.created_by ?? <span className="faint">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

/** A pipeline starts as one input step; everything else is added on its page. */
export function PipelineNew() {
  const [datasets, setDatasets] = useState([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [dataset, setDataset] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    getDatasets().then((d) => {
      setDatasets(d);
      setDataset((now) => now || d[0]?.name || "");
    }, (e) => setError(e.message));
  }, []);
  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const made = await createPipeline(name.trim(), description.trim(), { steps: [{ id: "in1", type: "input", dataset }] });
      window.location.hash = hrefFor({ page: "pipeline", name: made.id, view: "edit" });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };
  return (
    <main className="page">
      <a className="back" href={hrefFor({ page: "pipelines" })}>管道</a>
      <h1 tabIndex={-1}>新建管道</h1>
      <form className="stack wide" onSubmit={create}>
        <label className="field">
          <span className="caption">名称</span>
          <input type="text" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="例如：客户订单合计" />
        </label>
        <label className="field">
          <span className="caption">说明（可以不写）</span>
          <input type="text" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="field">
          <span className="caption">第一个输入的数据集</span>
          <Select label="第一个输入的数据集" value={dataset} onChange={setDataset}>
            {datasets.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
          </Select>
        </div>
        <div className="inline">
          <button className="primary" type="submit" disabled={busy || !name.trim() || !dataset}>创建</button>
          {error && <span className="error">{error}</span>}
        </div>
      </form>
    </main>
  );
}
