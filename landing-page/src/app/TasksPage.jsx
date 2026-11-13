import React, { useEffect } from "react";
import { getTasks } from "./api.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { anyRunning, taskRow } from "./taskModel.js";
import { useLoad } from "./useLoad.js";

export function TasksPage() {
  const [state, reload] = useLoad(getTasks, []);
  const rows = (state.data ?? []).map(taskRow);
  const running = anyRunning(state.data ?? []);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setTimeout(reload, 3000);   // a job in progress changes by itself; nothing else on this page does
    return () => clearTimeout(timer);
  }, [running, state]);

  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>任务</h1>
        <button className="secondary" onClick={reload}>刷新</button>
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !rows.length && <p className="muted">还没有任务。上传数据集或起草本体后会出现在这里。</p>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="tasks">
            <thead>
              <tr><th>时间</th><th>类型</th><th>名称</th><th>状态</th><th>操作人</th><th>说明</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key + r.at}>
                  <td className="keep">{timeText(r.at)}</td>
                  <td className="keep">{r.kind}</td>
                  <td>{r.dataset ? <a href={hrefFor({ page: "dataset", name: r.dataset, tab: "versions" })}>{r.title}</a> : r.title}</td>
                  <td className={`keep${r.bad ? " bad" : ""}`}>{r.state}</td>
                  <td className="keep">{r.who || <span className="faint">—</span>}</td>
                  <td className="text">{r.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
