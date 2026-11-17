import React, { useState } from "react";
import { createSchedule, createSource, pullTable, testSource, updateSource } from "./api.js";
import { ConnectFailure } from "./ConnectFailure.jsx";
import { STEPS, errorReport, portAfterKind } from "./connectModel.js";
import { t, useT } from "./i18n/index.js";
import { Select } from "./Select.jsx";
import { WhenFields, newScheduleForm } from "./SchedulesPage.jsx";
import { KINDS, TLS_MODES, estimateText, scheduleBody, scheduleProblem, sourceBody, sourceProblem, tlsDefault, tlsWarning } from "./sourceModel.js";
import { Drawer } from "./ui/Drawer.jsx";
import { Icon } from "./ui/Icon.jsx";
import { hrefFor } from "./routeModel.js";
import { timeText } from "./format.js";

const kindHint = (kind) => t(`sources.wiz.kindHint.${kind}`);

function Stepper({ at, reached }) {
  return (
    <ol className="wiz-steps" aria-label={t("sources.wiz.stepsAria")}>
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
      <p className="wiz-lead">{t("sources.wiz.typeLead")}</p>
      <div className="radio-cards" role="radiogroup" aria-label={t("sources.form.kind")}>
        {KINDS.map((k) => (
          <label key={k.key} className={`radio-card${f.kind === k.key ? " on" : ""}`}>
            <input type="radio" name="kind" checked={f.kind === k.key} onChange={() => setF({ ...f, kind: k.key, port: portAfterKind(k.key) })} />
            <span className="radio-card-title">{k.label}</span>
            <span className="radio-card-text">{kindHint(k.key)}</span>
          </label>
        ))}
      </div>
      <p className="hint">{t("sources.wiz.excel")}</p>
    </>
  );
}

function ConnectStep({ f, setF, problem, error, locked }) {
  const [show, setShow] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const tls = f.tls ?? tlsDefault(f.host);
  return (
    <>
      <label className="field"><span className="caption">{t("sources.form.name")}</span><input type="text" value={f.name} maxLength={60} placeholder={t("sources.wiz.namePlaceholder")} disabled={locked} title={locked ? t("sources.wiz.nameLocked") : undefined} onChange={set("name")} /></label>
      <div className="field-row">
        <label className="field grow"><span className="caption">{t("sources.form.host")}</span><input type="text" value={f.host} placeholder="db.example.com" autoComplete="off" onChange={set("host")} /></label>
        <label className="field port"><span className="caption">{t("sources.form.port")}</span><input type="text" inputMode="numeric" value={f.port} onChange={set("port")} /></label>
      </div>
      <label className="field"><span className="caption">{t("sources.form.database")}</span><input type="text" value={f.database} autoComplete="off" onChange={set("database")} /></label>
      <div className="field-row">
        <label className="field grow"><span className="caption">{t("sources.form.username")}</span><input type="text" value={f.username} autoComplete="off" onChange={set("username")} /></label>
        <label className="field grow">
          <span className="caption">{t("sources.form.password")}</span>
          <span className="secret">
            <input type={show ? "text" : "password"} value={f.password} autoComplete="new-password" onChange={set("password")} />
            <button type="button" className="plain" onClick={() => setShow(!show)} aria-pressed={show}>{show ? t("users.hide") : t("users.show")}</button>
          </span>
        </label>
      </div>
      <div className="field">
        <span className="caption">{t("sources.form.tls")}</span>
        <Select label={t("sources.form.tls")} value={tls} onChange={(v) => setF({ ...f, tls: v })}>
          {TLS_MODES.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
        </Select>
        <span className="hint tight">{t("sources.wiz.tlsHint")}</span>
      </div>
      {tls === "none" && <p className="warn">{tlsWarning()}</p>}
      {tls === "required" && (
        <label className="field">
          <span className="caption">{t("sources.wiz.ca")}</span>
          <textarea rows={3} value={f.ca} placeholder="-----BEGIN CERTIFICATE-----" spellCheck={false} onChange={set("ca")} />
        </label>
      )}
      <p className="hint">{t("sources.wiz.passwordNote")}</p>
      {problem && f.name && <p className="hint">{problem}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </>
  );
}

function TestStep({ f, kindLabel, result, onRetry, onBack }) {
  if (!result) return <p className="wiz-busy"><span className="spinner" aria-hidden="true" />{t("sources.wiz.connecting", { address: `${f.host}:${f.port}` })}</p>;
  if (result.status === "ok") {
    return (
      <div className="wiz-result ok-card">
        <p className="wiz-result-title"><Icon name="check" /> {t("sources.wiz.connected")}</p>
        <p>{t("sources.wiz.connectedText", { address: `${f.host}:${f.port}`, count: result.tables.length })}</p>
        {result.can_write && <p className="warn">{t("sources.page.writable", { note: result.write_note })}</p>}
      </div>
    );
  }
  const report = errorReport({ source: f.name, kind: kindLabel, host: f.host, port: f.port, database: f.database, username: f.username, tls: f.tls ?? tlsDefault(f.host), message: result.note ?? "", at: timeText(new Date().toISOString()) });
  return (
    <ConnectFailure message={result.note} report={report} note={t("sources.wiz.failNote")}>
      <button className="secondary" onClick={onBack}>{t("sources.wiz.backEdit")}</button>
      <button className="primary" onClick={onRetry}>{t("sources.page.retest")}</button>
    </ConnectFailure>
  );
}

function TablesStep({ tables, picked, setPicked, names, setNames, outcome }) {
  const free = tables.filter((t) => !t.dataset && !t.hidden && t.supported !== false);
  return (
    <>
      <p className="wiz-lead">{t("sources.wiz.tablesLead")}</p>
      <div className="table-wrap wiz-tables">
        <table>
          <thead><tr><th></th><th>{t("sources.tables.table")}</th><th className="num">{t("sources.tables.rows")}</th><th>{t("sources.wiz.datasetName")}</th></tr></thead>
          <tbody>
            {tables.map((tb) => {
              const can = free.includes(tb);
              const done = outcome[tb.name];
              return (
                <tr key={tb.name} className={can ? "" : "note"}>
                  <td><input type="checkbox" aria-label={t("sources.wiz.readAria", { table: tb.name })} disabled={!can || !!done?.ok} checked={!!picked[tb.name]} onChange={(e) => setPicked({ ...picked, [tb.name]: e.target.checked })} /></td>
                  <td>{tb.name}</td>
                  <td className="num" title={t("sources.tables.estimateTip")}>{tb.rows == null ? <span className="faint">—</span> : estimateText(tb.rows)}</td>
                  <td>
                    {done?.ok ? <span className="ok">{t("sources.wiz.readDone", { count: done.rows })}</span>
                      : done ? <span className="error small">{done.error}</span>
                        : can ? <input type="text" aria-label={t("sources.wiz.nameAria", { table: tb.name })} value={names[tb.name] ?? ""} maxLength={100} onChange={(e) => setNames({ ...names, [tb.name]: e.target.value })} />
                          : <span className="faint small">{tb.dataset ? t("sources.wiz.alreadyDataset", { dataset: tb.dataset }) : tb.note || t("sources.wiz.unsupported")}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!tables.length && <p className="muted">{t("sources.wiz.noTables")}</p>}
    </>
  );
}

function ScheduleStep({ sourceName, form, setForm, problem, saved }) {
  const set = (k) => (v) => setForm({ ...form, [k]: v });
  if (saved) return <div className="wiz-result ok-card"><p className="wiz-result-title"><Icon name="check" /> {t("sources.wiz.scheduled")}</p><p>{saved}</p></div>;
  return (
    <>
      <p className="wiz-lead">{t("sources.wiz.scheduleLead")}</p>
      <label className="field"><span className="caption">{t("sources.wiz.scheduleName")}</span><input type="text" value={form.name} maxLength={60} placeholder={t("sources.wiz.scheduleNameHint", { name: sourceName })} onChange={(e) => set("name")(e.target.value)} /></label>
      <WhenFields f={form} set={set} allowUpstream={false} />
      {problem && form.name && <p className="hint">{problem}</p>}
    </>
  );
}

/** The guide for connecting a database, in a side panel: type, connection, test, tables, schedule. Making the source tests it at once, so there is never a source "created but untested".
 * Closing at any point keeps what was already made (the source, the datasets); the list behind it refreshes through `onDone`. */
export function SourceWizard({ onClose, onDone }) {
  useT();
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
  const scheduleIssue = scheduleProblem({ ...form, name: form.name || t("sources.wiz.defaultScheduleName", { name: f.name }), kind: "source", target: f.name }, sourceForSchedule, []);
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
    for (const tb of chosen) {
      try {
        const run = await pullTable({ source: f.name, table: tb.name, name: names[tb.name].trim(), mode: "overwrite" });
        setOutcome((o) => ({ ...o, [tb.name]: run.status === "success" ? { ok: true, rows: run.rows } : { error: run.error || t("sources.pull.failed") } }));
      } catch (e) {
        setOutcome((o) => ({ ...o, [tb.name]: { error: e.message } }));
      }
    }
    setBusy(false);
    onDone();
  };
  const makeSchedule = async () => {
    setBusy(true);
    setError("");
    try {
      await createSchedule(scheduleBody({ ...form, name: form.name || t("sources.wiz.defaultScheduleName", { name: f.name }), kind: "source", target: f.name }));
      setScheduled(t("sources.wiz.scheduledText", { when: form.cadence === "hourly" ? t("sources.wiz.whenHourly", { minute: form.minute }) : form.cadence === "weekly" ? t("sources.wiz.whenWeekly", { time: form.time }) : t("sources.wiz.whenDaily", { time: form.time }), tz: form.tz, count: pulled.length }));
      onDone();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  const finish = () => { onClose(); window.location.hash = hrefFor({ page: "source", name: f.name }); };

  const duplicateName = chosen.find((tb, i) => chosen.findIndex((u) => names[u.name]?.trim() === names[tb.name]?.trim()) !== i);
  const tablesProblem = !chosen.length && !pulled.length ? t("sources.wiz.pickOne") : chosen.some((tb) => !names[tb.name]?.trim()) ? t("sources.wiz.nameEmpty") : duplicateName ? t("sources.wiz.nameDuplicate") : "";

  let footer;
  if (step === 0) footer = <><button className="plain" onClick={onClose}>{t("common.cancel")}</button><button className="primary" onClick={() => go(1)}>{t("sources.wiz.next")}</button></>;
  else if (step === 1) footer = <><span className="foot-note">{saved ? t("sources.wiz.footSaved") : t("sources.wiz.footNew")}</span><button className="plain" onClick={() => (saved ? onClose() : go(0))}>{saved ? t("common.close") : t("sources.wiz.back")}</button><button className="primary" disabled={!!problem || busy} onClick={connect}>{busy ? t("sources.wiz.busy") : saved ? t("sources.wiz.saveRetest") : t("sources.wiz.createTest")}</button></>;
  else if (step === 2) footer = result?.status === "ok"
    ? <><button className="plain" onClick={onClose}>{t("sources.wiz.stopHere")}</button><button className="primary" onClick={() => go(3)}>{t("sources.wiz.nextTables")}</button></>
    : <button className="plain" onClick={onClose}>{t("common.close")}</button>;
  else if (step === 3) footer = <>
    <span className="foot-note">{tablesProblem}</span>
    <button className="plain" onClick={() => (pulled.length ? go(4) : onClose())}>{pulled.length ? t("sources.wiz.continue") : t("sources.wiz.stopHere")}</button>
    <button className="primary" disabled={busy || !!tablesProblem || !chosen.length} onClick={readTables}>{busy ? t("sources.wiz.reading") : t("sources.wiz.readN", { count: chosen.length })}</button>
  </>;
  else footer = scheduled
    ? <button className="primary" onClick={finish}>{t("data.upl.done")}</button>
    : <><button className="plain" onClick={finish}>{t("sources.wiz.skip")}</button><button className="primary" disabled={busy || !!scheduleIssue || !pulled.length} onClick={makeSchedule}>{busy ? t("sources.wiz.saving") : t("sources.wiz.setSchedule")}</button></>;

  return (
    <Drawer open title={t("sources.connect")} onClose={onClose} width={620} footer={footer}>
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
