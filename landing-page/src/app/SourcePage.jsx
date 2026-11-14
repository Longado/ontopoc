import React, { useState } from "react";
import { deleteSource, getSource, getSourceTables, pullTable, refreshDataset, testSource } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isAdmin } from "./authModel.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { SourceForm, SourceState } from "./SourcesPage.jsx";
import { keyColumnsFrom, reasonText, runStatusText, runSummary } from "./sourceModel.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./UsersPage.jsx";

const MODE_TEXT = { overwrite: "整张覆盖", update_by_key: "按主键更新" };

function PullDialog({ source, table, onClose, onDone }) {
  const [name, setName] = useState(table.split(".").pop());
  const [mode, setMode] = useState("overwrite");
  const [keys, setKeys] = useState("");
  const keyList = keyColumnsFrom(keys);
  const valid = name.trim() && (mode === "overwrite" || keyList.length);
  return (
    <FormDialog title={`把“${table}”读成数据集`} submitLabel="读取" onClose={onClose} valid={valid}
      onSubmit={async () => {
        const run = await pullTable({ source, table, name: name.trim(), mode, ...(mode === "update_by_key" ? { key_columns: keyList } : {}) });
        if (run.status !== "success") throw new Error(run.error || "没有读成");
        onDone();
      }}>
      <label className="field"><span className="caption">数据集的名字</span><input type="text" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} /></label>
      <div className="field">
        <span className="caption">以后每次刷新怎么写进数据集</span>
        <Select label="刷新方式" value={mode} onChange={setMode}>
          <option value="overwrite">整张覆盖：用库里现在的整张表换掉</option>
          <option value="update_by_key">按主键更新：改了的行和新增的行更新进来，库里删掉的行保留</option>
        </Select>
      </div>
      {mode === "update_by_key" && (
        <label className="field"><span className="caption">主键列（多列用逗号隔开）</span><input type="text" value={keys} placeholder="订单号" onChange={(e) => setKeys(e.target.value)} /></label>
      )}
    </FormDialog>
  );
}

function DeleteSource({ source, onClose }) {
  return (
    <FormDialog title={`删除“${source.name}”`} submitLabel="删除" onClose={onClose} valid
      onSubmit={async () => { await deleteSource(source.name); window.location.hash = hrefFor({ page: "sources" }); }}>
      <p>数据源和它的调度会删掉。还有数据集来自它时删不了：先删掉那些数据集。</p>
    </FormDialog>
  );
}

function Tables({ name, tables, reload }) {
  const [pulling, setPulling] = useState(null);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>表</th><th>类型</th><th>行数</th><th>数据集</th></tr></thead>
        <tbody>
          {tables.map((t) => (
            <tr key={t.name}>
              <td>{t.name}</td>
              <td>{t.kind}</td>
              <td>{t.rows == null ? <span className="warn small" title={t.note ?? ""}>数不出来</span> : t.rows.toLocaleString()}</td>
              <td>
                {t.dataset ? <a href={hrefFor({ page: "dataset", name: t.dataset, tab: "fields" })}>{t.dataset}</a>
                  : <button className="plain" onClick={() => setPulling(t.name)}>读成数据集</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {pulling && <PullDialog source={name} table={pulling} onClose={() => setPulling(null)} onDone={reload} />}
    </div>
  );
}

function Runs({ runs }) {
  if (!runs.length) return <p className="muted">还没有拉取过。</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>开始</th><th>结束</th><th>表</th><th>方式</th><th>谁</th><th>结果</th><th></th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{timeText(r.started_at)}</td>
              <td>{r.finished_at ? timeText(r.finished_at) : <span className="faint">—</span>}</td>
              <td>{r.item}</td>
              <td>{reasonText(r)}</td>
              <td>{r.who}</td>
              <td><span className={`state ${r.status === "success" ? "state-confirmed" : r.status === "failed" ? "state-rejected" : r.status === "skipped" ? "state-needs_look" : ""}`}>{runStatusText(r)}</span></td>
              <td className="keep">{runSummary(r)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SourcePage({ route }) {
  const { name } = route;
  const admin = isAdmin(useAuth().user);
  const [state, reload] = useLoad(() => getSource(name), [name]);
  const [live, setLive] = useState(null);   // {status: "loading" | "ready" | "error", tables, error}: the tables in the database now
  const [dialog, setDialog] = useState(null);   // "edit" | "delete"
  const [refreshing, setRefreshing] = useState("");
  const [message, setMessage] = useState("");
  const source = state.data;

  const look = async () => {
    setLive({ status: "loading" });
    try {
      setLive({ status: "ready", tables: await getSourceTables(name) });
    } catch (e) {
      setLive({ status: "error", error: e.message });
    }
  };
  const test = async () => {
    setLive({ status: "loading" });
    setMessage("");
    try {
      const result = await testSource(name);
      setLive(result.status === "ok" ? { status: "ready", tables: result.tables } : { status: "error", error: result.note });
      setMessage(result.status === "ok" ? result.note ?? "" : "");
    } catch (e) {
      setLive({ status: "error", error: e.message });
    }
    reload();
  };
  const refresh = async (dataset) => {
    setRefreshing(dataset);
    setMessage("");
    try {
      const run = await refreshDataset(dataset);
      setMessage(run.status === "success" ? `“${dataset}”：${runSummary(run)}` : `“${dataset}”没有刷新：${run.error}`);
    } catch (e) {
      setMessage(e.message);
    }
    setRefreshing("");
    reload();
  };
  const afterPull = () => { reload(); look(); };

  return (
    <main className="page">
      <a className="back" href={hrefFor({ page: "sources" })}>数据源</a>
      <div className="page-head">
        <h1 tabIndex={-1}>{name}</h1>
        {source && admin && (
          <div className="head-actions">
            <button className="plain" onClick={() => setDialog("delete")}>删除</button>
            <button className="secondary" onClick={() => setDialog("edit")}>修改连接</button>
            <button className="primary" onClick={test}>测试连接</button>
          </div>
        )}
      </div>
      {state.status === "error" && <p className="error">{state.error} {!state.missing && <button className="plain" onClick={reload}>重试</button>}</p>}
      {state.status === "loading" && !source && <p className="muted">加载中</p>}
      {source && (
        <>
          <p className="facts">
            <span>{source.kind_label}</span>
            {admin && <span>{source.host}:{source.port}/{source.database}，账号 {source.username}</span>}
            <span><SourceState source={source} />{source.status_at && ` ${timeText(source.status_at)}`}</span>
          </p>
          {admin && source.local && <p className="hint">这个数据库在运行本服务的这台机器上。</p>}
          {source.status === "failed" && source.status_note && <p className="error">{source.status_note}</p>}
          {source.can_write && <p className="warn">这个账号不是只读的：{source.write_note}。服务只用只读会话读数据，但建议换成只有 SELECT 权限的账号。</p>}
          {message && <p className="muted">{message}</p>}

          <h2>库里的表</h2>
          {!live && <p><button className="secondary" onClick={look}>查看库里的表</button></p>}
          {live?.status === "loading" && <p className="muted">正在连接，数每张表的行数</p>}
          {live?.status === "error" && <p className="error">{live.error} <button className="plain" onClick={look}>重试</button></p>}
          {live?.status === "ready" && (live.tables.length ? <Tables name={name} tables={live.tables} reload={afterPull} /> : <p className="muted">库里没有表，或这个账号看不到。</p>)}

          <h2>已读成的数据集</h2>
          {!source.tables.length ? <p className="muted">还没有。从上面的表里选一张读成数据集。</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>数据集</th><th>来自的表</th><th>刷新方式</th><th></th></tr></thead>
                <tbody>
                  {source.tables.map((t) => (
                    <tr key={t.table}>
                      <td><a href={hrefFor({ page: "dataset", name: t.dataset, tab: "fields" })}>{t.dataset}</a></td>
                      <td>{t.table}</td>
                      <td>{MODE_TEXT[t.mode]}{t.key_columns && `（${t.key_columns.join("、")}）`}</td>
                      <td className="keep"><button className="plain" disabled={refreshing === t.dataset} onClick={() => refresh(t.dataset)}>{refreshing === t.dataset ? "刷新中" : "现在刷新"}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2>调度</h2>
          {source.schedules.length ? (
            <ul className="plain-list">
              {source.schedules.map((s) => <li key={s.id}><a href="#/schedules">{s.name}</a> {s.when}{!s.enabled && <span className="faint">（已关）</span>}</li>)}
            </ul>
          ) : <p className="muted">没有。<a href="#/schedules">去设一个定时刷新</a></p>}

          <h2>拉取记录</h2>
          <Runs runs={source.runs} />
        </>
      )}
      {dialog === "edit" && <SourceForm source={source} onClose={() => setDialog(null)} onDone={reload} />}
      {dialog === "delete" && <DeleteSource source={source} onClose={() => setDialog(null)} />}
    </main>
  );
}
