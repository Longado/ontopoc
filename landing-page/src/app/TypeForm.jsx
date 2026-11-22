import React, { useEffect, useState } from "react";
import { checkTypeKey, createType, getDataset, getDatasets, getType, updateType } from "./api.js";
import { typeLabel } from "./format.js";
import { t } from "./i18n/index.js";
import { Select } from "./Select.jsx";
import { hrefFor, parseRoute } from "./routeModel.js";
import { TYPE_CHOICES, keyProblem, otherNamesText, suggestEnglish, typePayload } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

const ENUM_TYPES = ["integer", "text"];

/** The dataset's columns as form rows; `was` (the saved type, when editing) fills in what the person chose before. */
function columnRows(dataset, was) {
  return dataset.columns.map((c) => {
    const saved = was?.properties.find((p) => p.column === c.name);
    const meanings = Object.fromEntries((saved?.meanings?.values ?? []).map((v) => [v.value, v.label]));
    const meaningOthers = Object.fromEntries((saved?.meanings?.values ?? []).map((v) => [v.value, otherNamesText(v.other_names)]));
    return {
      name: c.name, type: c.type, include: Boolean(saved), label: saved?.name ?? "", otherNames: otherNamesText(saved?.other_names), declared: saved?.type ?? c.type, values: c.values,
      candidate: ENUM_TYPES.includes(c.type) && c.values != null, enum: Boolean(saved?.enum), meanings, meaningOthers,
    };
  });
}

function KeyResult({ result }) {
  if (!result) return null;
  if (result.error) {
    const k = result.keyCheck;
    return (
      <div className="refusal">
        <p className="error">{result.error}</p>
        {k?.repeated?.length > 0 && (
          <ul className="readers">
            {k.repeated.map((r, i) => <li key={i}>{t("types.form.keyRepeat", { key: r.key.join(" + "), rows: r.rows, count: r.rows })}</li>)}
            {k.repeated_values > k.repeated.length && <li className="muted">{t("types.form.keyRepeatMore", { count: k.repeated_values - k.repeated.length })}</li>}
          </ul>
        )}
      </div>
    );
  }
  return (
    <div>
      <p>{t("types.form.keyOk", { rows: result.rows_checked })}</p>
      {result.warnings.map((w, i) => <p key={i} className="warn">{w}</p>)}
    </div>
  );
}

/** One page for both making a type and changing one: the dataset's columns with the key, the properties, the code columns and their meanings. */
export function TypeForm({ id }) {
  const editing = id != null;
  const [saved] = useLoad(() => (editing ? getType(id) : Promise.resolve(null)), [id]);
  const [datasets] = useLoad(getDatasets, []);
  const [form, setForm] = useState(null);
  const [keyResult, setKeyResult] = useState(null);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [englishTyped, setEnglishTyped] = useState(false);   // once the person writes the English name themselves, the name no longer rewrites it
  const [advanced, setAdvanced] = useState(false);
  const ready = saved.status === "ready" && datasets.status === "ready";

  useEffect(() => {
    if (ready && editing && !form) {
      const ty = saved.data;
      getDataset(ty.dataset).then((d) => setForm({ english: ty.id, name: ty.name, otherNames: otherNamesText(ty.other_names), description: ty.description, dataset: ty.dataset, key: ty.key, columns: columnRows(d, ty) }),
        (e) => setError({ message: e.message }));
    } else if (ready && !editing && !form) {
      const list = datasets.data;
      const wanted = parseRoute(window.location.hash).dataset;   // 用它建对象类型 arrives with the dataset
      const start = list.find((d) => d.name === wanted)?.name ?? (list.length === 1 ? list[0].name : "");   // the only dataset is the one to use
      const name = start;
      setForm({ english: suggestEnglish(name), name, otherNames: "", description: "", dataset: "", key: [], columns: [] });
      if (start) getDataset(start).then((d) => setForm((f) => ({ ...f, dataset: start, columns: columnRows(d, null) })), (e) => setError({ message: e.message }));
    }
  }, [ready]);
  useEffect(() => {
    if (form && form.columns.some((c) => c.enum)) setAdvanced(true);   // a code column is already chosen: show where it is set
  }, [form?.dataset]);
  const setName = (name) => setForm({ ...form, name, ...(editing || englishTyped ? {} : { english: suggestEnglish(name) }) });

  const pickDataset = async (name) => {
    setKeyResult(null);
    setError(null);
    if (!name) return setForm({ ...form, dataset: "", key: [], columns: [] });
    try {
      setForm({ ...form, dataset: name, key: [], columns: columnRows(await getDataset(name), null) });
    } catch (e) {
      setError({ message: e.message });
    }
  };
  const setColumn = (name, change) => setForm({ ...form, columns: form.columns.map((c) => (c.name === name ? { ...c, ...change } : c)) });
  const toggleKey = (column, on) => {
    setKeyResult(null);
    setForm({ ...form, key: on ? [...form.key, column.name] : form.key.filter((k) => k !== column.name) });
  };
  const check = async () => {
    try {
      setKeyResult(await checkTypeKey(form.dataset, form.key));
    } catch (e) {
      setKeyResult({ error: e.message, keyCheck: e.keyCheck });
    }
  };
  const save = async () => {
    setSending(true);
    setError(null);
    try {
      const payload = typePayload(form);
      const done = editing ? await updateType({ ...payload, id, version: saved.data.version }) : await createType(payload);
      window.location.hash = hrefFor({ page: "type", id: done.id, tab: "props" });
    } catch (e) {
      setError({ message: e.message, keyCheck: e.keyCheck });
      setSending(false);
    }
  };

  const problems = form ? form.key.map((k) => keyProblem(form.columns.find((c) => c.name === k))).filter(Boolean) : [];
  const complete = form && form.name.trim() && (editing || form.english.trim()) && form.dataset && form.key.length > 0 && problems.length === 0;
  return (
    <main className="page">
      <a className="back" href={editing ? hrefFor({ page: "type", id, tab: "props" }) : hrefFor({ page: "types" })}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {editing ? saved.data?.name ?? t("types.form.back") : t("types.form.back")}
      </a>
      <div className="page-head"><h1 tabIndex={-1}>{editing ? t("types.form.titleEdit") : t("types.form.titleNew")}</h1></div>
      {[saved, datasets].map((s, i) => s.status === "error" && <p key={i} className="error">{s.error}</p>)}
      {form && (
        <div className="stack wide">
          <label className="field">
            <span className="caption">{t("types.form.name")}</span>
            <input type="text" value={form.name} placeholder={t("types.form.namePlaceholder")} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span className="caption">{t("types.form.english", { fixed: editing ? t("types.form.fixedEdit") : t("types.form.fixedNew") })}</span>
            <input type="text" value={form.english} disabled={editing} placeholder={t("types.form.englishPlaceholder")} onChange={(e) => { setEnglishTyped(true); setForm({ ...form, english: e.target.value }); }} />
            {!editing && (form.english
              ? <span className="muted small">{t("types.form.englishAuto", { english: form.english })}</span>
              : <span className="muted small">{form.name.trim() ? t("types.form.englishUnknown") : t("types.form.englishWait")}</span>)}
          </label>
          <label className="field">
            <span className="caption">{t("types.otherNames")}</span>
            <input type="text" value={form.otherNames} placeholder={t("types.otherNamesPlaceholder")} onChange={(e) => setForm({ ...form, otherNames: e.target.value })} />
            <span className="muted small">{t("types.otherNamesHint")}</span>
          </label>
          <details className="fold" open={Boolean(form.description)}>
            <summary>{t("types.form.description")}</summary>
            <input type="text" aria-label={t("types.form.descriptionAria")} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </details>
          <div className="field">
            <span className="caption">{t("types.form.dataset")}</span>
            <Select label={t("types.form.datasetLabel")} value={form.dataset} disabled={editing} onChange={pickDataset}>
              <option value="">{t("types.form.pick")}</option>
              {datasets.data.map((d) => <option key={d.name} value={d.name}>{t("types.form.datasetRows", { name: d.name, rows: d.rows })}</option>)}
            </Select>
          </div>

          {form.columns.length > 0 && (
            <>
              <h2 className="section">{t("types.form.properties")}</h2>
              <p className="hint">{t("types.form.propertiesHint")}</p>
              <div className="table-wrap">
                <table className="props">
                  <thead>
                    <tr><th>{t("types.form.col.key")}</th><th>{t("types.form.col.column")}</th><th>{t("types.form.col.use")}</th><th>{t("types.form.col.label")}</th><th>{t("types.form.col.other")}</th>{advanced && <th>{t("types.form.col.type")}</th>}{advanced && <th>{t("types.form.col.code")}</th>}</tr>
                  </thead>
                  <tbody>
                    {form.columns.map((c) => {
                      const isKey = form.key.includes(c.name);
                      return (
                        <tr key={c.name}>
                          <td><input type="checkbox" aria-label={t("types.form.keyAria", { name: c.name })} checked={isKey} onChange={(e) => toggleKey(c, e.target.checked)} /></td>
                          <td>{c.name} <span className="muted small">{typeLabel(c.type)}</span></td>
                          <td><input type="checkbox" aria-label={t("types.form.useAria", { name: c.name })} checked={c.include || isKey} disabled={isKey} onChange={(e) => setColumn(c.name, { include: e.target.checked })} /></td>
                          <td><input type="text" aria-label={t("types.form.labelAria", { name: c.name })} value={c.label} placeholder={c.name} disabled={!(c.include || isKey)} onChange={(e) => setColumn(c.name, { label: e.target.value })} /></td>
                          <td><input type="text" aria-label={t("types.form.otherAria", { name: c.name })} value={c.otherNames ?? ""} disabled={!(c.include || isKey)} onChange={(e) => setColumn(c.name, { otherNames: e.target.value })} /></td>
                          {advanced && <td>
                            <Select label={t("types.form.typeAria", { name: c.name })} value={c.declared} disabled={!(c.include || isKey) || c.enum} onChange={(v) => setColumn(c.name, { declared: v })}>
                              {TYPE_CHOICES[c.type].map((choice) => <option key={choice} value={choice}>{typeLabel(choice)}</option>)}
                            </Select>
                          </td>}
                          {advanced && <td>
                            {c.candidate ? (
                              <input type="checkbox" aria-label={t("types.form.codeAria", { name: c.name })} checked={c.enum} disabled={!(c.include || isKey)} onChange={(e) => setColumn(c.name, { enum: e.target.checked })} />
                            ) : <span className="faint">—</span>}
                          </td>}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="inline"><button className="plain" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>{advanced ? t("types.form.advancedHide") : t("types.form.advancedShow")}</button></div>
              {problems.map((p, i) => <p key={i} className="error">{p}</p>)}
              <div className="inline">
                <button className="secondary" onClick={check} disabled={!form.key.length || problems.length > 0}>{t("types.form.checkKey")}</button>
                <span className="muted small">{t("types.form.checkKeyHint")}</span>
              </div>
              <KeyResult result={keyResult} />
              {advanced && <p className="hint">{t("types.form.codeHint")}</p>}

              {form.columns.filter((c) => c.enum && (c.include || form.key.includes(c.name))).map((c) => (
                <section key={c.name}>
                  <h2 className="section">{t("types.form.meaningsOf", { name: c.name })}</h2>
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>{t("types.form.value")}</th><th className="num">{t("types.form.rows")}</th><th>{t("types.form.meaning")}</th><th>{t("types.form.meaningOthers")}</th></tr></thead>
                      <tbody>
                        {Object.entries(c.values).map(([value, rows]) => (
                          <tr key={value}>
                            <td>{value}</td>
                            <td className="num">{rows}</td>
                            <td><input type="text" aria-label={t("types.meanings.inputAria", { column: c.name, value })} value={c.meanings[value] ?? ""} placeholder={t("types.meanings.placeholder")}
                              onChange={(e) => setColumn(c.name, { meanings: { ...c.meanings, [value]: e.target.value } })} /></td>
                            <td><input type="text" aria-label={t("types.form.meaningOthersAria", { column: c.name, value })} value={c.meaningOthers?.[value] ?? ""} placeholder={t("types.otherNamesPlaceholder")}
                              onChange={(e) => setColumn(c.name, { meaningOthers: { ...(c.meaningOthers ?? {}), [value]: e.target.value } })} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="hint">{t("types.form.meaningsHint")}</p>
                </section>
              ))}
            </>
          )}

          {error && (
            <div className="refusal">
              <p className="error">{error.message}</p>
              {error.keyCheck?.repeated?.length > 0 && <ul className="readers">{error.keyCheck.repeated.map((r, i) => <li key={i}>{t("types.form.keyRepeat", { key: r.key.join(" + "), rows: r.rows, count: r.rows })}</li>)}</ul>}
            </div>
          )}
          <div className="inline">
            <button className="primary" onClick={save} disabled={!complete || sending}>{sending ? t("types.form.saving") : editing ? t("common.save") : t("types.form.create")}</button>
            <a href={editing ? hrefFor({ page: "type", id, tab: "props" }) : hrefFor({ page: "types" })}>{t("common.cancel")}</a>
          </div>
        </div>
      )}
    </main>
  );
}
