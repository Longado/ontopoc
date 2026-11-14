import React, { useState } from "react";
import { createSource, getSources, updateSource } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isAdmin } from "./authModel.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { KINDS, TLS_MODES, TLS_WARNING, kindPort, sourceProblem, statusText, tlsDefault } from "./sourceModel.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./UsersPage.jsx";

export function SourceState({ source }) {
  const cls = source.status === "ok" ? "state-confirmed" : source.status === "failed" ? "state-rejected" : "";
  return <span className={`state ${cls}`}>{statusText(source)}</span>;
}

/** Make a source, or (with `source`) change its connection. The password is never filled in: a blank one keeps the saved one. */
export function SourceForm({ source, onClose, onDone }) {
  const editing = !!source;
  const [f, setF] = useState({
    name: source?.name ?? "", kind: source?.kind ?? "postgresql", host: source?.host ?? "", port: String(source?.port ?? 5432),
    database: source?.database ?? "", username: source?.username ?? "", password: "", tls: source?.tls ?? null,   // null: the default for this host until one is chosen
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const problem = sourceProblem(f, editing, source);
  const tls = f.tls ?? tlsDefault(f.host);
  const body = { ...f, tls, port: Number(f.port), ...(f.password ? {} : { password: undefined }) };
  return (
    <FormDialog title={editing ? `修改“${source.name}”` : "新建数据源"} submitLabel={editing ? "保存" : "创建"} onClose={onClose} valid={!problem}
      onSubmit={async () => { await (editing ? updateSource(body) : createSource(body)); onDone(); }}>
      {!editing && <label className="field"><span className="caption">名字（数据集会写“来自这个名字”）</span><input type="text" value={f.name} maxLength={60} onChange={set("name")} /></label>}
      {!editing && (
        <div className="field">
          <span className="caption">数据库类型</span>
          <Select label="数据库类型" value={f.kind} onChange={(kind) => setF({ ...f, kind, port: String(kindPort(kind)) })}>
            {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </Select>
        </div>
      )}
      <label className="field"><span className="caption">主机</span><input type="text" value={f.host} placeholder="db.example.com" autoComplete="off" onChange={set("host")} /></label>
      <label className="field"><span className="caption">端口</span><input type="text" inputMode="numeric" value={f.port} onChange={set("port")} /></label>
      <label className="field"><span className="caption">数据库名</span><input type="text" value={f.database} autoComplete="off" onChange={set("database")} /></label>
      <label className="field"><span className="caption">账号（建议只给 SELECT 权限）</span><input type="text" value={f.username} autoComplete="off" onChange={set("username")} /></label>
      <label className="field">
        <span className="caption">{editing ? "密码（主机、端口、数据库名、账号都没改时，不改就留空）" : "密码"}</span>
        <input type="password" value={f.password} autoComplete="new-password" onChange={set("password")} />
      </label>
      <div className="field">
        <span className="caption">加密连接</span>
        <Select label="加密连接" value={tls} onChange={(v) => setF({ ...f, tls: v })}>
          {TLS_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </Select>
      </div>
      {tls === "none" && <p className="warn">{TLS_WARNING}</p>}
      <p className="hint">密码保存时打散，页面和接口不会再返回它。读数据用只读会话。</p>
      {problem && <p className="hint">{problem}</p>}
    </FormDialog>
  );
}

export function SourcesPage() {
  const admin = isAdmin(useAuth().user);
  const [state, reload] = useLoad(getSources, []);
  const [making, setMaking] = useState(false);
  const sources = state.data ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>数据源</h1>
        {admin && <button className="primary" onClick={() => setMaking(true)}>新建数据源</button>}
      </div>
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !sources.length && <p className="muted">还没有数据源。{admin ? "新建一个，把库里的表读成数据集。" : "要接数据库，请管理员先建一个。"}</p>}
      {sources.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>名称</th><th>类型</th>{admin && <th>地址</th>}<th>状态</th><th>读成的数据集</th></tr></thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.name}>
                  <td><a href={hrefFor({ page: "source", name: s.name })}>{s.name}</a></td>
                  <td>{s.kind_label}</td>
                  {admin && <td>{s.host}:{s.port}/{s.database}{s.local && <span className="faint"> 本机</span>}</td>}
                  <td><SourceState source={s} />{s.status_at && <span className="faint small"> {timeText(s.status_at)}</span>}</td>
                  <td>
                    {s.tables.length ? s.tables.map((t) => (
                      <span key={t.table} className="output-chip"><a href={hrefFor({ page: "dataset", name: t.dataset, tab: "fields" })}>{t.dataset}</a> </span>
                    )) : <span className="faint">还没有</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {making && <SourceForm onClose={() => setMaking(false)} onDone={reload} />}
    </main>
  );
}
