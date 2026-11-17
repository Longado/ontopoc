import React, { useState } from "react";
import { createSchedule, createSource, pullTable, testSource, updateSource } from "./api.js";
import { ConnectFailure } from "./ConnectFailure.jsx";
import { STEPS, errorReport, portAfterKind } from "./connectModel.js";
import { Select } from "./Select.jsx";
import { WhenFields, newScheduleForm } from "./SchedulesPage.jsx";
import { KINDS, TLS_MODES, TLS_WARNING, estimateText, scheduleBody, scheduleProblem, sourceBody, sourceProblem, tlsDefault } from "./sourceModel.js";
import { Drawer } from "./ui/Drawer.jsx";
import { Icon } from "./ui/Icon.jsx";
import { hrefFor } from "./routeModel.js";
import { timeText } from "./format.js";

const KIND_HINT = { postgresql: "常见端口 5432", mysql: "常见端口 3306（MariaDB 也选这个）" };

function Stepper({ at, reached }) {
  return (
    <ol className="wiz-steps" aria-label="连接向导的步骤">
      {STEPS.map((s, i) => (
        <li key={s.key} className={i === at ? "now" : i < at ? "done" : ""} aria-current={i === at ? "step" : undefined}>
          <span className="wiz-dot">{i < at && i < reached ? <Icon name="check" size={12} /> : i + 1}</span>{s.label}
        </li>
      ))}
    </ol>
  );
}

function TypeStep({ f, setF }) {
  return (
    <>
      <p className="wiz-lead">选你要连的数据库。OntoPoc 只读取它，不会改库里的任何东西。</p>
      <div className="radio-cards" role="radiogroup" aria-label="数据库类型">
        {KINDS.map((k) => (
          <label key={k.key} className={`radio-card${f.kind === k.key ? " on" : ""}`}>
            <input type="radio" name="kind" checked={f.kind === k.key} onChange={() => setF({ ...f, kind: k.key, port: portAfterKind(k.key) })} />
            <span className="radio-card-title">{k.label}</span>
            <span className="radio-card-text">{KIND_HINT[k.key]}</span>
          </label>
        ))}
      </div>
      <p className="hint">没有数据库、只有 Excel？关掉这个向导，到“数据集”上传 .xlsx 或 .csv。</p>
    </>
  );
}

function ConnectStep({ f, setF, problem, error, locked }) {
  const [show, setShow] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const tls = f.tls ?? tlsDefault(f.host);
  return (
    <>
      <label className="field"><span className="caption">名字（数据集会写“来自这个名字”）</span><input type="text" value={f.name} maxLength={60} placeholder="例如 销售订单库" disabled={locked} title={locked ? "数据源建好后名字不能改" : undefined} onChange={set("name")} /></label>
      <div className="field-row">
        <label className="field grow"><span className="caption">主机</span><input type="text" value={f.host} placeholder="db.example.com" autoComplete="off" onChange={set("host")} /></label>
        <label className="field port"><span className="caption">端口</span><input type="text" inputMode="numeric" value={f.port} onChange={set("port")} /></label>
      </div>
      <label className="field"><span className="caption">数据库名</span><input type="text" value={f.database} autoComplete="off" onChange={set("database")} /></label>
      <div className="field-row">
        <label className="field grow"><span className="caption">账号（建议只给 SELECT 权限）</span><input type="text" value={f.username} autoComplete="off" onChange={set("username")} /></label>
        <label className="field grow">
          <span className="caption">密码</span>
          <span className="secret">
            <input type={show ? "text" : "password"} value={f.password} autoComplete="new-password" onChange={set("password")} />
            <button type="button" className="plain" onClick={() => setShow(!show)} aria-pressed={show}>{show ? "隐藏" : "显示"}</button>
          </span>
        </label>
      </div>
      <div className="field">
        <span className="caption">加密连接</span>
        <Select label="加密连接" value={tls} onChange={(v) => setF({ ...f, tls: v })}>
          {TLS_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </Select>
        <span className="hint tight">公司内网的数据库常用自签证书，连接时会报证书错误：这种情况选“不用”（只限内网），或把公司 CA 的证书文字贴在下面。</span>
      </div>
      {tls === "none" && <p className="warn">{TLS_WARNING}</p>}
      {tls === "required" && (
        <label className="field">
          <span className="caption">公司 CA 证书（可选，PEM 文字）</span>
          <textarea rows={3} value={f.ca} placeholder="-----BEGIN CERTIFICATE-----" spellCheck={false} onChange={set("ca")} />
        </label>
      )}
      <p className="hint">密码在这台服务器上加密保存，页面和接口都读不出来；读数据时用只读会话。</p>
      {problem && f.name && <p className="hint">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </>
  );
}

function TestStep({ f, kindLabel, result, onRetry, onBack }) {
  if (!result) return <p className="wiz-busy"><span className="spinner" aria-hidden="true" />正在连接 {f.host}:{f.port}，最多要等十几秒</p>;
  if (result.status === "ok") {
    return (
      <div className="wiz-result ok-card">
        <p className="wiz-result-title"><Icon name="check" /> 连上了</p>
        <p>{f.host}:{f.port}，库里有 {result.tables.length} 张表。</p>
        {result.can_write && <p className="warn">这个账号不是只读的：{result.write_note}。服务只用只读会话读数据，但建议换成只有 SELECT 权限的账号。</p>}
      </div>
    );
  }
  const report = errorReport({ source: f.name, kind: kindLabel, host: f.host, port: f.port, database: f.database, username: f.username, tls: f.tls ?? tlsDefault(f.host), message: result.note ?? "", at: timeText(new Date().toISOString()) });
  return (
    <ConnectFailure message={result.note} report={report} note="数据源已经保存，下次可以从列表里继续；“复制错误信息”不含密码，可以直接发给 DBA。">
      <button className="secondary" onClick={onBack}>返回修改连接</button>
      <button className="primary" onClick={onRetry}>重新测试</button>
    </ConnectFailure>
  );
}

function TablesStep({ tables, picked, setPicked, names, setNames, outcome }) {
  const free = tables.filter((t) => !t.dataset && !t.hidden && t.supported !== false);
  return (
    <>
      <p className="wiz-lead">勾选要读进来的表，每张表成为一个数据集；以后可以随时刷新。</p>
      <div className="table-wrap wiz-tables">
        <table>
          <thead><tr><th></th><th>表</th><th className="num">行数</th><th>数据集名</th></tr></thead>
          <tbody>
            {tables.map((t) => {
              const can = free.includes(t);
              const done = outcome[t.name];
              return (
                <tr key={t.name} className={can ? "" : "note"}>
                  <td><input type="checkbox" aria-label={`读取 ${t.name}`} disabled={!can || !!done?.ok} checked={!!picked[t.name]} onChange={(e) => setPicked({ ...picked, [t.name]: e.target.checked })} /></td>
                  <td>{t.name}</td>
                  <td className="num" title="数据库自己统计的行数，可能不是最新">{t.rows == null ? <span className="faint">—</span> : estimateText(t.rows)}</td>
                  <td>
                    {done?.ok ? <span className="ok">已读入：{done.rows} 行</span>
                      : done ? <span className="error small">{done.error}</span>
                        : can ? <input type="text" aria-label={`${t.name} 的数据集名`} value={names[t.name] ?? ""} maxLength={100} onChange={(e) => setNames({ ...names, [t.name]: e.target.value })} />
                          : <span className="faint small">{t.dataset ? `已经是数据集 ${t.dataset}` : t.note || "不支持读取"}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!tables.length && <p className="muted">库里没有表，或这个账号看不到。请 DBA 给账号加上 SELECT 权限。</p>}
    </>
  );
}

function ScheduleStep({ sourceName, form, setForm, problem, saved }) {
  const set = (k) => (v) => setForm({ ...form, [k]: v });
  if (saved) return <div className="wiz-result ok-card"><p className="wiz-result-title"><Icon name="check" /> 已设好定时同步</p><p>{saved}</p></div>;
  return (
    <>
      <p className="wiz-lead">想让这些数据集自动保持最新，可以现在设一个定时同步；也可以跳过，以后在“调度”里设。</p>
      <label className="field"><span className="caption">调度的名字</span><input type="text" value={form.name} maxLength={60} placeholder={`${sourceName} 每天同步`} onChange={(e) => set("name")(e.target.value)} /></label>
      <WhenFields f={form} set={set} allowUpstream={false} />
      {problem && form.name && <p className="hint">{problem}</p>}
    </>
  );
}

/** The guide for connecting a database, in a side panel: type, connection, test, tables, schedule. Making the source tests it at once, so there is never a source "created but untested".
 * Closing at any point keeps what was already made (the source, the datasets); the list behind it refreshes through `onDone`. */
export function SourceWizard({ onClose, onDone }) {
  const [step, setStep] = useState(0);
  const [f, setF] = useState({ name: "", kind: "postgresql", host: "", port: "5432", database: "", username: "", password: "", tls: null, ca: "", dropCa: false });
  const [saved, setSaved] = useState(null);   // the connection as last saved: {host, port, database, username}; set once the source exists
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState({});
  const [names, setNames] = useState({});
  const [outcome, setOutcome] = useState({});
  const [form, setForm] = useState(() => newScheduleForm());
  const [scheduled, setScheduled] = useState("");
  const [reached, setReached] = useState(0);

  const kindLabel = KINDS.find((k) => k.key === f.kind)?.label ?? f.kind;
  const tls = f.tls ?? tlsDefault(f.host);
  const problem = sourceProblem(f, !!saved, saved);
  const tables = result?.status === "ok" ? result.tables : [];
  const chosen = tables.filter((t) => picked[t.name] && !outcome[t.name]?.ok);
  const pulled = tables.filter((t) => outcome[t.name]?.ok);
  const sourceForSchedule = [{ name: f.name, tables: pulled.map((t) => ({ table: t.name, dataset: names[t.name] })) }];
  const scheduleIssue = scheduleProblem({ ...form, name: form.name || `${f.name} 同步`, kind: "source", target: f.name }, sourceForSchedule, []);
  const go = (n) => { setStep(n); setReached((r) => Math.max(r, n)); };

  const connect = async () => {
    setBusy(true);
    setError("");
    try {
      const body = sourceBody(f, tls);
      if (saved) await updateSource(body); else await createSource(body);
      setSaved({ host: f.host.trim(), port: f.port, database: f.database.trim(), username: f.username.trim() });
      setF((x) => ({ ...x, password: "" }));
      setBusy(false);
      await test();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };
  const test = async () => {
    setResult(null);
    go(2);
    try {
      const r = await testSource(f.name);
      setResult(r);
      if (r.status === "ok") {
        const free = r.tables.filter((t) => !t.dataset && !t.hidden && t.supported !== false);
        setNames(Object.fromEntries(free.map((t) => [t.name, t.name.split(".").pop()])));
        setPicked(Object.fromEntries(free.map((t) => [t.name, free.length <= 5])));
      }
      onDone();
    } catch (e) {
      setResult({ status: "failed", note: e.message, tables: [] });
    }
  };
  const readTables = async () => {
    setBusy(true);
    setError("");
    for (const t of chosen) {
      try {
        const run = await pullTable({ source: f.name, table: t.name, name: names[t.name].trim(), mode: "overwrite" });
        setOutcome((o) => ({ ...o, [t.name]: run.status === "success" ? { ok: true, rows: run.rows } : { error: run.error || "没有读成" } }));
      } catch (e) {
        setOutcome((o) => ({ ...o, [t.name]: { error: e.message } }));
      }
    }
    setBusy(false);
    onDone();
  };
  const makeSchedule = async () => {
    setBusy(true);
    setError("");
    try {
      await createSchedule(scheduleBody({ ...form, name: form.name || `${f.name} 同步`, kind: "source", target: f.name }));
      setScheduled(`${form.cadence === "hourly" ? `每小时第 ${form.minute} 分` : form.cadence === "weekly" ? `每周，${form.time}` : `每天 ${form.time}`}（${form.tz}）刷新 ${pulled.length} 个数据集。`);
      onDone();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  const finish = () => { onClose(); window.location.hash = hrefFor({ page: "source", name: f.name }); };

  const duplicateName = chosen.find((t, i) => chosen.findIndex((u) => names[u.name]?.trim() === names[t.name]?.trim()) !== i);
  const tablesProblem = !chosen.length && !pulled.length ? "勾选至少一张表" : chosen.some((t) => !names[t.name]?.trim()) ? "数据集名不能空" : duplicateName ? "两张表的数据集名一样了" : "";

  let footer;
  if (step === 0) footer = <><button className="plain" onClick={onClose}>取消</button><button className="primary" onClick={() => go(1)}>下一步</button></>;
  else if (step === 1) footer = <><span className="foot-note">{saved ? "数据源已保存，改完会再测一次" : "创建时会马上测试连接"}</span><button className="plain" onClick={() => (saved ? onClose() : go(0))}>{saved ? "关闭" : "上一步"}</button><button className="primary" disabled={!!problem || busy} onClick={connect}>{busy ? "正在连接" : saved ? "保存并重新测试" : "创建并测试连接"}</button></>;
  else if (step === 2) footer = result?.status === "ok"
    ? <><button className="plain" onClick={onClose}>先到这里</button><button className="primary" onClick={() => go(3)}>下一步：选表</button></>
    : <button className="plain" onClick={onClose}>关闭</button>;
  else if (step === 3) footer = <>
    <span className="foot-note">{tablesProblem}</span>
    <button className="plain" onClick={() => (pulled.length ? go(4) : onClose())}>{pulled.length ? "继续" : "先到这里"}</button>
    <button className="primary" disabled={busy || !!tablesProblem || !chosen.length} onClick={readTables}>{busy ? "读取中" : `读成 ${chosen.length} 个数据集`}</button>
  </>;
  else footer = scheduled
    ? <button className="primary" onClick={finish}>完成</button>
    : <><button className="plain" onClick={finish}>跳过，以后再设</button><button className="primary" disabled={busy || !!scheduleIssue || !pulled.length} onClick={makeSchedule}>{busy ? "保存中" : "设定时同步"}</button></>;

  return (
    <Drawer open title="接入数据库" onClose={onClose} width={620} footer={footer}>
      <Stepper at={step} reached={reached} />
      {step === 0 && <TypeStep f={f} setF={setF} />}
      {step === 1 && <ConnectStep f={f} setF={setF} problem={problem} error={error} locked={!!saved} />}
      {step === 2 && <TestStep f={f} kindLabel={kindLabel} result={result} onRetry={test} onBack={() => go(1)} />}
      {step === 3 && <TablesStep tables={tables} picked={picked} setPicked={setPicked} names={names} setNames={setNames} outcome={outcome} />}
      {step === 4 && <ScheduleStep sourceName={f.name} form={form} setForm={setForm} problem={scheduleIssue} saved={scheduled} />}
      {step === 3 && error && <p className="error" role="alert">{error}</p>}
      {step === 4 && error && <p className="error" role="alert">{error}</p>}
    </Drawer>
  );
}
