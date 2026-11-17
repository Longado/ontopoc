import React, { useEffect, useState } from "react";
import { checkTypeKey, createType, getDataset, getDatasets, getType, updateType } from "./api.js";
import { typeLabel } from "./format.js";
import { Select } from "./Select.jsx";
import { hrefFor, parseRoute } from "./routeModel.js";
import { TYPE_CHOICES, keyProblem, suggestEnglish, typePayload } from "./typeModel.js";
import { useLoad } from "./useLoad.js";

const ENUM_TYPES = ["integer", "text"];

/** The dataset's columns as form rows; `was` (the saved type, when editing) fills in what the person chose before. */
function columnRows(dataset, was) {
  return dataset.columns.map((c) => {
    const saved = was?.properties.find((p) => p.column === c.name);
    const meanings = Object.fromEntries((saved?.meanings?.values ?? []).map((v) => [v.value, v.label]));
    return {
      name: c.name, type: c.type, include: Boolean(saved), label: saved?.name ?? "", declared: saved?.type ?? c.type, values: c.values,
      candidate: ENUM_TYPES.includes(c.type) && c.values != null, enum: Boolean(saved?.enum), meanings,
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
            {k.repeated.map((r, i) => <li key={i}>{r.key.join(" + ")}，{r.rows} 行</li>)}
            {k.repeated_values > k.repeated.length && <li className="muted">还有 {k.repeated_values - k.repeated.length} 个重复的值</li>}
          </ul>
        )}
      </div>
    );
  }
  return (
    <div>
      <p>查了全部 {result.rows_checked} 行，没有重复，没有空值。</p>
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
      const t = saved.data;
      getDataset(t.dataset).then((d) => setForm({ english: t.id, name: t.name, description: t.description, dataset: t.dataset, key: t.key, columns: columnRows(d, t) }),
        (e) => setError({ message: e.message }));
    } else if (ready && !editing && !form) {
      const list = datasets.data;
      const wanted = parseRoute(window.location.hash).dataset;   // 用它建对象类型 arrives with the dataset
      const start = list.find((d) => d.name === wanted)?.name ?? (list.length === 1 ? list[0].name : "");   // the only dataset is the one to use
      const name = start;
      setForm({ english: suggestEnglish(name), name, description: "", dataset: "", key: [], columns: [] });
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
        {editing ? saved.data?.name ?? "对象类型" : "对象类型"}
      </a>
      <div className="page-head"><h1 tabIndex={-1}>{editing ? "修改对象类型" : "新建对象类型"}</h1></div>
      {[saved, datasets].map((s, i) => s.status === "error" && <p key={i} className="error">{s.error}</p>)}
      {form && (
        <div className="stack wide">
          <label className="field">
            <span className="caption">名称</span>
            <input type="text" value={form.name} placeholder="例如：订单" onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span className="caption">英文名（程序里用的名字，字母、数字、下划线；{editing ? "建好后不能改" : "确认前也不能再改"}）</span>
            <input type="text" value={form.english} disabled={editing} placeholder="例如：order、customer_ticket" onChange={(e) => { setEnglishTyped(true); setForm({ ...form, english: e.target.value }); }} />
            {!editing && (form.english
              ? <span className="muted small">按名称自动写了“{form.english}”，不合适可以改。</span>
              : <span className="muted small">{form.name.trim() ? "没认出这个词，请自己写一个英文名，比如“订单”写 order。" : "写好名称后会自动给一个建议。"}</span>)}
          </label>
          <details className="fold" open={Boolean(form.description)}>
            <summary>说明（可以不写）</summary>
            <input type="text" aria-label="说明" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </details>
          <div className="field">
            <span className="caption">来自哪个数据集（用它现在的版本）</span>
            <Select label="数据集" value={form.dataset} disabled={editing} onChange={pickDataset}>
              <option value="">请选择</option>
              {datasets.data.map((d) => <option key={d.name} value={d.name}>{d.name}（{d.rows} 行）</option>)}
            </Select>
          </div>

          {form.columns.length > 0 && (
            <>
              <h2 className="section">属性</h2>
              <p className="hint">通常选能唯一认出每一行的那一列做主键（比如订单号），其余列都勾上做属性。</p>
              <div className="table-wrap">
                <table className="props">
                  <thead>
                    <tr><th>主键</th><th>列</th><th>用作属性</th><th>属性名称</th>{advanced && <th>类型</th>}{advanced && <th>代码列</th>}</tr>
                  </thead>
                  <tbody>
                    {form.columns.map((c) => {
                      const isKey = form.key.includes(c.name);
                      return (
                        <tr key={c.name}>
                          <td><input type="checkbox" aria-label={`${c.name} 做主键`} checked={isKey} onChange={(e) => toggleKey(c, e.target.checked)} /></td>
                          <td>{c.name} <span className="muted small">{typeLabel(c.type)}</span></td>
                          <td><input type="checkbox" aria-label={`${c.name} 做属性`} checked={c.include || isKey} disabled={isKey} onChange={(e) => setColumn(c.name, { include: e.target.checked })} /></td>
                          <td><input type="text" aria-label={`${c.name} 的属性名称`} value={c.label} placeholder={c.name} disabled={!(c.include || isKey)} onChange={(e) => setColumn(c.name, { label: e.target.value })} /></td>
                          {advanced && <td>
                            <Select label={`${c.name} 的类型`} value={c.declared} disabled={!(c.include || isKey) || c.enum} onChange={(v) => setColumn(c.name, { declared: v })}>
                              {TYPE_CHOICES[c.type].map((t) => <option key={t} value={t}>{typeLabel(t)}</option>)}
                            </Select>
                          </td>}
                          {advanced && <td>
                            {c.candidate ? (
                              <input type="checkbox" aria-label={`${c.name} 是代码列`} checked={c.enum} disabled={!(c.include || isKey)} onChange={(e) => setColumn(c.name, { enum: e.target.checked })} />
                            ) : <span className="faint">—</span>}
                          </td>}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="inline"><button className="plain" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>{advanced ? "收起高级设置" : "高级设置：属性类型、代码列"}</button></div>
              {problems.map((p, i) => <p key={i} className="error">{p}</p>)}
              <div className="inline">
                <button className="secondary" onClick={check} disabled={!form.key.length || problems.length > 0}>检查主键</button>
                <span className="muted small">按全部行查有没有重复和空值；保存时也会查一遍</span>
              </div>
              <KeyResult result={keyResult} />
              {advanced && <p className="hint">代码列不会存成是/否：0、1、2 这样的取值保持整数，由人给每个取值写含义。</p>}

              {form.columns.filter((c) => c.enum && (c.include || form.key.includes(c.name))).map((c) => (
                <section key={c.name}>
                  <h2 className="section">{c.name} 的含义</h2>
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>取值</th><th className="num">行数</th><th>含义</th></tr></thead>
                      <tbody>
                        {Object.entries(c.values).map(([value, rows]) => (
                          <tr key={value}>
                            <td>{value}</td>
                            <td className="num">{rows}</td>
                            <td><input type="text" aria-label={`${c.name} = ${value} 的含义`} value={c.meanings[value] ?? ""} placeholder="还没有含义"
                              onChange={(e) => setColumn(c.name, { meanings: { ...c.meanings, [value]: e.target.value } })} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="hint">没写含义的取值保持“含义未确认”。写了的，要另一位建设者确认才算数。</p>
                </section>
              ))}
            </>
          )}

          {error && (
            <div className="refusal">
              <p className="error">{error.message}</p>
              {error.keyCheck?.repeated?.length > 0 && <ul className="readers">{error.keyCheck.repeated.map((r, i) => <li key={i}>{r.key.join(" + ")}，{r.rows} 行</li>)}</ul>}
            </div>
          )}
          <div className="inline">
            <button className="primary" onClick={save} disabled={!complete || sending}>{sending ? "保存中" : editing ? "保存" : "创建"}</button>
            <a href={editing ? hrefFor({ page: "type", id, tab: "props" }) : hrefFor({ page: "types" })}>取消</a>
          </div>
        </div>
      )}
    </main>
  );
}
