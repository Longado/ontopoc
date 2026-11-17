import React, { useState } from "react";
import { createSource, getSources, updateSource } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isAdmin } from "./authModel.js";
import { CopyButton } from "./CopyButton.jsx";
import { portAfterKind } from "./connectModel.js";
import { timeText } from "./format.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { SourceWizard } from "./SourceWizard.jsx";
import { KINDS, TLS_MODES, TLS_WARNING, sourceBody, sourceProblem, statusText, tlsDefault } from "./sourceModel.js";
import { useLoad } from "./useLoad.js";
import { FormDialog } from "./FormDialog.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

const CHIP = { ok: "confirmed", failed: "failed", untested: "draft" };

export function SourceState({ source }) {
  return <StatusChip state={CHIP[source.status] ?? source.status} label={statusText(source)} />;
}

const ASK_ADMIN = [
  "请帮我把一个数据库接进 OntoPoc（只读）。请提供：",
  "1. 数据库类型（PostgreSQL 或 MySQL）",
  "2. 主机地址和端口（运行 OntoPoc 的服务器要能访问到）",
  "3. 数据库名",
  "4. 一个只有 SELECT 权限的账号和密码",
  "5. 如果数据库用公司内部证书：公司 CA 证书",
].join("\n");

/** What a builder who is not an admin sees instead of the 新建 button: who connects databases and what to ask them. */
function AskAdmin() {
  return (
    <section className="card ask-admin">
      <h2>数据库由管理员接入</h2>
      <p>连接数据库要用到数据库的账号密码，所以只有管理员能建数据源。你可以先把想用的库告诉管理员，接好之后，数据源里的表就能在这里读成数据集。</p>
      <p className="muted">发给管理员的话（点一下复制）：</p>
      <pre className="ask-text">{ASK_ADMIN}</pre>
      <CopyButton text={ASK_ADMIN} label="复制这段话" />
      <p className="hint">只有 Excel 或 CSV 的话，不用等管理员：到“数据集”直接上传。</p>
    </section>
  );
}

/** Make a source, or (with `source`) change its connection. The password is never filled in: a blank one keeps the saved one. */
export function SourceForm({ source, onClose, onDone }) {
  const editing = !!source;
  const [f, setF] = useState({
    name: source?.name ?? "", kind: source?.kind ?? "postgresql", host: source?.host ?? "", port: String(source?.port ?? 5432),
    database: source?.database ?? "", username: source?.username ?? "", password: "", tls: source?.tls ?? null,   // null: the default for this host until one is chosen
    ca: "", dropCa: false,   // the CA is never sent back: a saved one shows as set, a pasted one replaces it
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const problem = sourceProblem(f, editing, source);
  const tls = f.tls ?? tlsDefault(f.host);
  const body = sourceBody(f, tls);
  return (
    <FormDialog title={editing ? `修改“${source.name}”` : "新建数据源"} submitLabel={editing ? "保存" : "创建"} onClose={onClose} valid={!problem}
      onSubmit={async () => { await (editing ? updateSource(body) : createSource(body)); onDone(); }}>
      {!editing && <label className="field"><span className="caption">名字（数据集会写“来自这个名字”）</span><input type="text" value={f.name} maxLength={60} onChange={set("name")} /></label>}
      {!editing && (
        <div className="field">
          <span className="caption">数据库类型</span>
          <Select label="数据库类型" value={f.kind} onChange={(kind) => setF({ ...f, kind, port: portAfterKind(kind) })}>
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
      <p className="hint">内网的库报证书错误时，选“不用”（只限内网），或在下面贴公司 CA。</p>
      {tls === "none" && <p className="warn">{TLS_WARNING}</p>}
      {tls === "required" && (
        <label className="field">
          <span className="caption">{source?.custom_ca ? "CA 证书（已设置；贴新的会替换它）" : "CA 证书（可选：数据库的证书由公司内部 CA 签发时，贴这个 CA 的 PEM）"}</span>
          <textarea rows={4} value={f.ca} placeholder="-----BEGIN CERTIFICATE-----" spellCheck={false} onChange={set("ca")} />
        </label>
      )}
      {tls === "required" && source?.custom_ca && !f.ca.trim() && (
        <label className="check"><input type="checkbox" checked={f.dropCa} onChange={(e) => setF({ ...f, dropCa: e.target.checked })} /> 不再用这张 CA，改回用系统的证书核对</label>
      )}
      <p className="hint">密码在这台服务器上加密保存，页面和接口都读不出来；但能拿到服务器上文件的人，有办法还原它，所以请用只读账号。读数据时用只读会话。</p>
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
      <PageHeader crumbs={[{ label: "数据" }, { label: "数据源" }]} title="数据源" sub="连上公司的数据库（只读），把里面的表读成数据集。"
        actions={admin && <button className="primary" onClick={() => setMaking(true)}>接入数据库</button>} />
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>重试</button></p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !admin && <AskAdmin />}
      {state.data && !sources.length && admin && <EmptyState icon="plug" title="还没有数据源" text="按向导走五步：选类型、填连接、测试、选表、定时同步。只读，不会改库里的数据。" action={{ label: "接入数据库", onClick: () => setMaking(true) }} />}
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
      {making && <SourceWizard onClose={() => setMaking(false)} onDone={reload} />}
    </main>
  );
}
