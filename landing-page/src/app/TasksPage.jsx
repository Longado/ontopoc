import React, { useEffect } from "react";
import { getTasks } from "./api.js";
import { timeText } from "./format.js";
import { t, useT } from "./i18n/index.js";
import { anyRunning, taskRow } from "./taskModel.js";
import { useLoad } from "./useLoad.js";

export function TasksPage() {
  useT();
  const [state, reload] = useLoad(getTasks, []);
  const tasks = state.data?.tasks ?? [];
  const rows = tasks.map(taskRow);
  const running = anyRunning(tasks);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setTimeout(reload, 3000);   // a job in progress changes by itself; nothing else on this page does
    return () => clearTimeout(timer);
  }, [running, state]);

  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>{t("data.tasks.title")}</h1>
        <button className="secondary" onClick={reload}>{t("data.tasks.refresh")}</button>
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("common.loading")}</p>}
      {state.data?.unreadable > 0 && <p className="muted">{t("data.tasks.unreadable", { count: state.data.unreadable })}</p>}
      {state.data && !rows.length && <p className="muted">{t("data.tasks.empty")}</p>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="tasks">
            <thead>
              <tr><th>{t("data.tasks.time")}</th><th>{t("data.tasks.type")}</th><th>{t("data.tasks.name")}</th><th>{t("data.tasks.state")}</th><th>{t("data.tasks.by")}</th><th>{t("data.tasks.note")}</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key + r.at}>
                  <td className="keep">{timeText(r.at)}</td>
                  <td className="keep">{r.kind}</td>
                  <td>{r.href ? <a href={r.href}>{r.title}</a> : r.title}</td>
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
