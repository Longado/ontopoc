import React, { useEffect, useRef, useState } from "react";
import { checkDerivedExpression, confirmDerived, createDerived, getDerivedLog, getTypeDerived, shapeDerived, trialDerived, updateDerived } from "./api.js";
import { timeText, typeLabel } from "./format.js";
import { t } from "./i18n/index.js";
import { OP_LABEL, derivedPayload, derivedProblem, emptyDerivedForm, fnOptions, formFromLine, hopText, nextRelations, offerChange, sampleText, usedByText, waitingText } from "./derivedModel.js";
import { fieldRef, insertAt } from "./pipelineModel.js";
import { Select } from "./Select.jsx";
import { State } from "./TypesPage.jsx";
import { confirmersText, joinList, stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

/** What the trial found, as the sentences a person reads before confirming, a few values and, for a formula, the sample it was tried on. */
function Trial({ trial }) {
  if (!trial) return null;
  return (
    <>
      <ul className="checks">
        {trial.lines.map((l, i) => <li key={i} className={l.ok ? "" : "warn"}>{l.text}</li>)}
      </ul>
      {trial.sample && <p className="muted small">{sampleText(trial.sample)}</p>}
      {trial.examples.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("types.derived.objectCol")}</th><th>{t("types.derived.valueCol")}</th></tr></thead>
            <tbody>{trial.examples.map((e) => <tr key={e.object}><td>{e.object}</td><td>{e.value}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </>
  );
}

function History({ type, name }) {
  const [state] = useLoad(() => getDerivedLog(type, name), [type, name]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">{t("common.loading")}</p>;
  if (!state.data.confirmations.length) return <p className="muted small">{t("types.derived.noneConfirmed")}</p>;
  return (
    <ul className="plain-list">
      {state.data.confirmations.map((c, i) => (
        <li key={i}>
          {t("types.derived.confirmedLine", { who: c.confirmed_by, time: timeText(c.confirmed_at), says: c.says })}
          {c.trial?.lines?.[0] && <span className="muted small block">{t("types.derived.atConfirm", { text: c.trial.lines[0].text })}</span>}
        </li>
      ))}
    </ul>
  );
}

function DerivedCard({ line, mayBuild, onChanged, onEdit }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState(false);
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmDerived(line.type, line.id, line.version, line.seen);
      onChanged();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) onChanged();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  const standing = stateLine(line, t("types.derived.noun"));
  return (
    <section className="card">
      <div className="page-head">
        <h2 className="item-title">{line.name} <span className="muted small">{t("types.derived.tag", { kind: line.kind_name })}</span></h2>
        <State item={line} />
      </div>
      <p>{line.says}</p>
      <p className="facts">
        <span>{t("types.derived.output", { type: typeLabel(line.output_type) })}</span>
        <span>{usedByText(line.used_by)}</span>
        {line.description && <span>{line.description}</span>}
      </p>
      {line.problems.map((p) => <p key={p} className="warn">{p}</p>)}
      {standing && <p className="muted small">{standing}</p>}
      {waitingText(line) && <p className="warn">{waitingText(line)}</p>}
      {confirmersText(line) && <p className="muted small">{confirmersText(line)}</p>}
      {line.state === "needs_look" && line.reason && (
        <div className="reason">
          <strong>{t("types.page.whyLook")}</strong>
          <p>{line.reason}</p>
        </div>
      )}
      <Trial trial={line.trial} />
      <div className="inline wide">
        {mayBuild && line.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>{t("types.derived.confirm")}</button>}
        {mayBuild && <button className="secondary" onClick={onEdit}>{t("types.page.edit")}</button>}
        {mayBuild && <button className="plain" onClick={() => setHistory(!history)}>{history ? t("types.derived.historyHide") : t("types.derived.history")}</button>}
      </div>
      {history && <History type={line.type} name={line.id} />}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

/** The formula: the text, the functions and the fields to click into it, Validate (is it written right) before it is tried on the rows. */
function Formula({ type, options, form, setForm }) {
  const area = useRef(null);
  const [checked, setChecked] = useState(null);
  const [error, setError] = useState("");
  const insert = (what) => {
    const el = area.current;
    const at = insertAt(form.expression, el?.selectionStart, el?.selectionEnd, what);
    setForm({ ...form, expression: at.text });
    setChecked(null);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at.caret, at.caret);
    });
  };
  const check = async () => {
    setError("");
    try {
      setChecked(await checkDerivedExpression(type, form.expression));
    } catch (e) {
      setError(e.message);
    }
  };
  const groups = [...new Set(options.functions.map((f) => f.group))];
  return (
    <div className="expr-columns">
      <div className="expr-main">
        <label className="caption" htmlFor="derived-expression">{t("types.derived.formula")}</label>
        <textarea id="derived-expression" ref={area} rows={4} spellCheck={false} value={form.expression} onChange={(e) => { setForm({ ...form, expression: e.target.value }); setChecked(null); }} />
        <div className="inline">
          <button className="secondary" onClick={check} disabled={!form.expression.trim()}>{t("types.derived.validate")}</button>
        </div>
        {checked && (checked.ok ? <p className="ok">{t("types.derived.formulaOk", { type: typeLabel(checked.column_type) })}</p>
          : checked.errors.map((e, i) => <p key={i} className="error">{e.message}{e.pos ? t("types.derived.charPos", { pos: e.pos + 1 }) : ""}</p>))}
        {error && <p className="error">{error}</p>}
        <p className="muted small">{options.hint}</p>
      </div>
      <div className="expr-list" aria-label={t("types.derived.functionsAria")}>
        <p className="caption">{t("types.derived.functionsCaption")}</p>
        {groups.map((g) => (
          <div key={g}>
            <p className="group-name">{g}</p>
            {options.functions.filter((f) => f.group === g).map((f) => <button key={f.name} className="plain fn" title={f.template} onClick={() => insert(f.template)}>{f.name}<span className="muted small">{f.does}</span></button>)}
          </div>
        ))}
      </div>
      <div className="expr-list" aria-label={t("types.derived.columnsAria")}>
        <p className="caption">{t("types.derived.columnsCaption")}</p>
        {options.columns.map((c) => <button key={c.name} className="plain fn" onClick={() => insert(fieldRef(c.name))}>{c.name}<span className="muted small">{t("types.derived.columnSample", { type: typeLabel(c.type), sample: c.sample ?? t("types.derived.sampleNone") })}</span></button>)}
      </div>
    </div>
  );
}

/** The path from this type through confirmed relations, the measured column, how the many rows become one, and the conditions. */
function Statistic({ type, options, form, setForm, shape }) {
  const hops = shape?.hops ?? [];
  const next = form.path.length < 3 ? nextRelations(options.relations, type, hops) : [];
  const m = shape?.measured;
  const column = m?.columns.find((c) => c.name === form.column);
  const fns = form.column ? fnOptions(column, options.aggregations) : [{ id: "count", label: options.aggregations.count }];
  const setPath = (path) => setForm({ ...form, path, column: "", fn: "", latest: { order: "", tie: "" }, conditions: [{ column: "", op: "is", label: "" }] });
  const setCondition = (i, next) => setForm({ ...form, conditions: form.conditions.map((c, j) => (j === i ? next : c)) });
  return (
    <>
      <div className="field">
        <span className="caption">{t("types.derived.path")}</span>
        {hops.length > 0 && (
          <ol className="plain-list">
            {hops.map((h, i) => <li key={`${h.relation}-${i}`}>{i + 1}. {hopText(h)}</li>)}
          </ol>
        )}
        {shape?.problems?.map((p) => <p key={p} className="error">{p}</p>)}
        <div className="inline wide">
          {next.length > 0 && (
            <Select label={t("types.derived.addStep")} value="" onChange={(key) => key && setPath([...form.path, key])}>
              <option value="">{form.path.length ? t("types.derived.nextStep") : t("types.derived.firstStep")}</option>
              {next.map((r) => <option key={r.key} value={r.key}>{r.name} ({r.from_name} → {r.to_name})</option>)}
            </Select>
          )}
          {form.path.length > 0 && <button className="plain" onClick={() => setPath(form.path.slice(0, -1))}>{t("types.derived.removeStep")}</button>}
        </div>
        {!next.length && !form.path.length && <p className="muted small">{t("types.derived.noRelations")}</p>}
      </div>
      {m && (
        <>
          <div className="field">
            <span className="caption">{t("types.derived.measureCaption", { name: m.name })}</span>
            <Select label={t("types.derived.measureLabel")} value={form.column} onChange={(c) => setForm({ ...form, column: c, fn: shape.many ? (c ? "" : "count") : "" })}>
              <option value="">{shape.many ? t("types.derived.countRows") : t("types.derived.pickColumn")}</option>
              {m.columns.map((c) => <option key={c.name} value={c.name}>{t("types.derived.columnCode", { name: c.name, type: typeLabel(c.type), code: c.code ? t("types.derived.codeSuffix") : "" })}</option>)}
            </Select>
          </div>
          {m.layers.length > 0 && <p className="muted small">{t("types.derived.layers", { name: m.name, columns: joinList(m.layers.map((l) => l.column)), kind: t(m.layers[0].kind === "snapshot" ? "types.derived.snapshot" : "types.derived.version") })}</p>}
          {shape.many ? (
            <div className="field">
              <span className="caption">{t("types.derived.aggCaption")}</span>
              <Select label={t("types.derived.aggLabel")} value={form.fn} onChange={(fn) => setForm({ ...form, fn })}>
                <option value="">{t("types.derived.pickAgg")}</option>
                {fns.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
              </Select>
            </div>
          ) : <p className="muted small">{t("types.derived.oneSide")}</p>}
          {form.fn === "latest" && (
            <div className="field">
              <span className="caption">{t("types.derived.latestCaption")}</span>
              <div className="inline wide">
                <Select label={t("types.derived.latestOrder")} value={form.latest.order} onChange={(order) => setForm({ ...form, latest: { ...form.latest, order } })}>
                  <option value="">{t("types.derived.pickColumn")}</option>
                  {m.columns.filter((c) => c.orderable && c.name !== form.column).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                </Select>
                <Select label={t("types.derived.latestTie")} value={form.latest.tie} onChange={(tie) => setForm({ ...form, latest: { ...form.latest, tie } })}>
                  <option value="">{t("types.derived.noTie")}</option>
                  {m.columns.filter((c) => c.orderable && c.name !== form.latest.order).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                </Select>
              </div>
            </div>
          )}
          <div className="field">
            <span className="caption">{t("types.derived.conditions", { name: m.name })}</span>
            {form.conditions.map((row, i) => (
              <div className="inline wide" key={i}>
                <Select label={t("types.derived.condColumn")} value={row.column} onChange={(c) => setCondition(i, { ...row, column: c, label: "" })}>
                  <option value="">{t("types.derived.pickColumn")}</option>
                  {m.codes.map((c) => <option key={c.column} value={c.column}>{c.name}</option>)}
                </Select>
                <Select label={t("types.derived.condOp")} value={row.op} onChange={(op) => setCondition(i, { ...row, op })}>
                  {Object.entries(OP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
                <Select label={t("types.derived.condMeaning")} value={row.label} disabled={!row.column} onChange={(label) => setCondition(i, { ...row, label })}>
                  <option value="">{t("types.derived.pickMeaning")}</option>
                  {(m.codes.find((c) => c.column === row.column)?.labels ?? []).map((l) => <option key={l} value={l}>{l}</option>)}
                </Select>
                {form.conditions.length > 1 && <button className="plain" onClick={() => setForm({ ...form, conditions: form.conditions.filter((_, j) => j !== i) })}>{t("types.derived.remove")}</button>}
              </div>
            ))}
            {form.conditions.length < 5 && <button className="plain" style={{ alignSelf: "flex-start" }} onClick={() => setForm({ ...form, conditions: [...form.conditions, { column: "", op: "is", label: "" }] })}>{t("types.derived.addCondition")}</button>}
            {m.codes.every((c) => !c.labels.length) && <p className="muted small">{t("types.derived.noCodes", { name: m.name })}</p>}
          </div>
        </>
      )}
    </>
  );
}

/** A new property, or (with `editing`) the change of a saved one: it is a new version and is put forward again as this person's. */
function DerivedForm({ type, options, editing, onSaved, onCancel }) {
  const [form, setForm] = useState(editing ? formFromLine(editing) : emptyDerivedForm());
  const [shape, setShape] = useState(null);
  const [trial, setTrial] = useState(null);
  const [error, setError] = useState("");
  const [offers, setOffers] = useState([]);
  const [busy, setBusy] = useState(false);
  const pathKey = form.path.join(",");
  useEffect(() => {
    if (form.kind !== "statistic" || !form.path.length) {
      setShape(null);
      return undefined;
    }
    let live = true;
    shapeDerived(type, form.path).then((s) => live && setShape(s), (e) => live && setError(e.message));
    return () => { live = false; };
  }, [type, pathKey, form.kind]);
  const problem = derivedProblem(form, shape);
  const refused = (e) => {
    setError(e.message);
    setOffers(e.offer ?? []);
  };
  const run = async (go) => {
    setBusy(true);
    setError("");
    setOffers([]);
    try {
      await go();
    } catch (e) {
      refused(e);
    }
    setBusy(false);
  };
  const payload = derivedPayload(type, form);
  const tryIt = () => run(async () => setTrial(await trialDerived(payload)));
  const save = () => run(async () => {
    await (editing ? updateDerived(payload, editing.version) : createDerived(payload));
    onSaved();
  });
  const edit = (next) => {
    setForm(next);
    setTrial(null);
    setOffers([]);
    setError("");
  };
  return (
    <section>
      <h2 className="section">{editing ? t("types.derived.editTitle", { name: editing.name }) : t("types.derived.newTitle")}</h2>
      {editing && <p className="muted small">{t("types.derived.editNote")}</p>}
      {!editing && (
        <div className="inline">
          {Object.entries(options.kinds).map(([k, label]) => (
            <label key={k} className="check"><input type="radio" name="derived-kind" checked={form.kind === k} onChange={() => edit({ ...form, kind: k })} />{label}</label>
          ))}
        </div>
      )}
      <label className="field">
        <span className="caption">{t("types.derived.name")}</span>
        <input type="text" value={form.name} maxLength={40} placeholder={form.kind === "function" ? t("types.derived.namePlaceholderFn") : t("types.derived.namePlaceholderStat")} onChange={(e) => edit({ ...form, name: e.target.value })} />
      </label>
      <label className="field">
        <span className="caption">{t("types.derived.english")}</span>
        <input type="text" value={form.english_name} maxLength={40} disabled={!!editing} placeholder={t("types.derived.englishPlaceholder")} onChange={(e) => edit({ ...form, english_name: e.target.value })} />
      </label>
      {form.kind === "function"
        ? <Formula type={type} options={options} form={form} setForm={edit} />
        : <Statistic type={type} options={options} form={form} setForm={edit} shape={shape} />}
      <label className="field">
        <span className="caption">{t("types.derived.description")}</span>
        <input type="text" value={form.description} maxLength={200} onChange={(e) => edit({ ...form, description: e.target.value })} />
      </label>
      <div className="inline wide">
        <button className="secondary" onClick={tryIt} disabled={busy || !!problem}>{t("types.derived.try")}</button>
        <button className="primary" onClick={save} disabled={busy || !!problem}>{editing ? t("types.derived.saveVersion") : t("common.save")}</button>
        {onCancel && <button className="plain" onClick={onCancel}>{t("common.cancel")}</button>}
        {problem && <span className="muted small">{problem}</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {offers.length > 0 && (
        <div className="inline wide">
          {offers.filter((o) => o.fn).map((o, i) => {
            const change = offerChange(form, o, options.aggregations);
            return <button key={i} className="secondary" onClick={() => edit(change.apply())}>{change.label}</button>;
          })}
        </div>
      )}
      {trial && (trial.problems.length ? trial.problems.map((p) => <p key={p} className="error">{p}</p>) : <Trial trial={trial} />)}
    </section>
  );
}

export function TypeDerived({ type, mayBuild }) {
  const [state, reload] = useLoad(() => getTypeDerived(type.id), [type.id]);
  const [editing, setEditing] = useState(null);   // the line being changed, or "new"
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">{t("common.loading")}</p>;
  const { derived, form } = state.data;
  const done = () => {
    setEditing(null);
    reload();
  };
  return (
    <>
      {!derived.length && <p className="muted">{t("types.derived.empty")}</p>}
      <div className="cards">
        {derived.map((d) => <DerivedCard key={`${d.id}@${d.version}`} line={d} mayBuild={mayBuild} onChanged={reload} onEdit={() => setEditing(d)} />)}
      </div>
      {mayBuild && form && <DerivedForm key={editing?.id ?? "new"} type={type.id} options={form} editing={editing} onSaved={done} onCancel={editing ? () => setEditing(null) : null} />}
    </>
  );
}
