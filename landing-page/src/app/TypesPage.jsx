import React, { useEffect, useRef, useState } from "react";
import { getDatasets, getTypes, suggestTypes } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { hrefFor } from "./routeModel.js";
import { stateText } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

export function State({ item }) {
  return <span className={`state state-${item.model_draft ? "draft" : item.state ?? "none"}`}>{stateText(item)}</span>;
}

/** Asks the model for object types from some datasets. It runs as a task: what it proposed and what the checks dropped are listed, nothing is confirmed. */
function SuggestDialog({ onClose, onDone }) {
  const ref = useRef(null);
  const [datasets, setDatasets] = useState([]);
  const [chosen, setChosen] = useState([]);
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const [waited, setWaited] = useState(0);
  useEffect(() => {
    ref.current.showModal();
    getDatasets().then(setDatasets, (e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!sending) return undefined;
    setWaited(0);
    const timer = setInterval(() => setWaited((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [sending]);
  const close = () => {
    if (sending) return;   // the service keeps writing the drafts when the page goes: closing now would lose the list and invite a second run
    ref.current.close();
    onClose();
  };
  const send = async () => {
    setSending(true);
    setError("");
    try {
      setResult(await suggestTypes(chosen, purpose));
      onDone();
    } catch (e) {
      setError(e.message);
    }
    setSending(false);
  };
  const toggle = (name, on) => setChosen(on ? [...chosen, name] : chosen.filter((n) => n !== name));
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); close(); }}>
      <div className="dialog-body">
        <h2>从数据集建议对象类型</h2>
        {!result && (
          <>
            <fieldset className="keys">
              <legend>读哪几个数据集</legend>
              {datasets.map((d) => (
                <label key={d.name}>
                  <input type="checkbox" checked={chosen.includes(d.name)} onChange={(e) => toggle(d.name, e.target.checked)} />
                  {d.name}
                </label>
              ))}
            </fieldset>
            <label className="field">
              <span className="caption">要拿它回答什么</span>
              <input type="text" value={purpose} maxLength={400} placeholder="例如：数每个客户已取消的订单" onChange={(e) => setPurpose(e.target.value)} />
            </label>
            <p className="hint">模型只看到数据集名、列名、类型和每列有几种取值，看不到任何一行。它只能提议，提议出来的都是“模型草稿”，要有人看过、再由另一位确认才算数。</p>
          </>
        )}
        {result && (
          <>
            <p>提议了 {result.proposed.length} 个对象类型{result.proposed.length > 0 && "："}</p>
            <ul className="results">
              {result.proposed.map((p) => <li key={p.id}><a href={hrefFor({ page: "type", id: p.id, tab: "props" })}>{p.name}</a></li>)}
            </ul>
            {result.rejected.length > 0 && (
              <>
                <p style={{ marginTop: 12 }}>没通过检查、没有保存的 {result.rejected.length} 个：</p>
                <ul className="results">
                  {result.rejected.map((r, i) => <li key={i}>{r.name}：<span className="muted">{r.reason}</span></li>)}
                </ul>
              </>
            )}
          </>
        )}
      </div>
      <div className="actions">
        {error ? <span className="error">{error}</span> : <span></span>}
        {result ? (
          <button className="primary" onClick={close}>关闭</button>
        ) : (
          <>
            {sending && <span className="muted">模型在看，通常 15–40 秒，已等 {waited} 秒</span>}
            <button className="plain" onClick={close} disabled={sending}>取消</button>
            <button className="primary" onClick={send} disabled={sending || !chosen.length}>{sending ? "模型在看" : "开始"}</button>
          </>
        )}
      </div>
    </dialog>
  );
}

export function TypesPage() {
  const [state, reload] = useLoad(getTypes, []);
  const [suggesting, setSuggesting] = useState(false);
  const [filter, setFilter] = useState("");
  const mayBuild = canBuild(useAuth().user);
  const types = (state.data ?? []).filter((t) => `${t.name} ${t.id}`.toLowerCase().includes(filter.trim().toLowerCase()));
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>对象类型</h1>
        {mayBuild && (
          <div className="head-actions">
            <button className="secondary" onClick={() => setSuggesting(true)}>从数据集建议</button>
            <a className="button primary" href={hrefFor({ page: "typenew" })}>新建对象类型</a>
          </div>
        )}
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !state.data.length && <p className="muted">还没有对象类型。{mayBuild ? "从一个数据集新建，或让模型先提议。" : "建设者确认后会出现在这里。"}</p>}
      {state.data?.length > 8 && <label className="field"><span className="caption">按名称筛选</span><input type="text" value={filter} onChange={(e) => setFilter(e.target.value)} /></label>}
      {types.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>名称</th><th>英文名</th><th>来源</th><th>状态</th><th className="num">对象</th><th>确认人</th></tr>
            </thead>
            <tbody>
              {types.map((t) => (
                <tr key={t.id}>
                  <td><a href={hrefFor({ page: "type", id: t.id, tab: "props" })}>{t.name}</a></td>
                  <td className="id">{t.id}</td>
                  <td>{t.dataset}{t.dataset_version != null && <span className="muted"> 第 {t.dataset_version} 版</span>}</td>
                  <td><State item={t} />{t.meanings_waiting > 0 && <span className="muted small"> 有 {t.meanings_waiting} 组含义没确认</span>}</td>
                  <td className="num">{t.rows ?? "—"}</td>
                  <td>{t.confirmed_by ?? <span className="faint">没有</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {suggesting && <SuggestDialog onClose={() => setSuggesting(false)} onDone={reload} />}
    </main>
  );
}
