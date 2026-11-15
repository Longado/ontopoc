import React, { useEffect, useState } from "react";
import { createRelation, getRelation, getRelationForm, updateRelation } from "./api.js";
import { typeLabel } from "./format.js";
import { CARDINALITY_LABEL, relationPayload, relationProblem, suggestedColumns } from "./relationModel.js";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

/** One page for making a relation and changing one: the two types, the column of each dataset that holds the same value, and the cardinality. */
export function RelationForm({ id }) {
  const editing = id != null;
  const [saved] = useLoad(() => (editing ? getRelation(id) : Promise.resolve(null)), [id]);
  const [types] = useLoad(getRelationForm, []);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const ready = saved.status === "ready" && types.status === "ready";

  useEffect(() => {
    if (!ready || form) return;
    const r = saved.data;
    setForm(r
      ? { english: r.id, name: r.name, description: r.description, from: r.from, to: r.to, cardinality: r.cardinality, fromColumn: r.from_column, toColumn: r.to_column }
      : { english: "", name: "", description: "", from: "", to: "", cardinality: "many_to_one", fromColumn: "", toColumn: "" });
  }, [ready]);

  const byId = Object.fromEntries((types.data ?? []).map((t) => [t.id, t]));
  const pickType = (end, value) => {
    const next = { ...form, [end]: value, [`${end}Column`]: "" };
    const suggested = suggestedColumns(byId[next.from], byId[next.to], next.cardinality);
    setForm({ ...next, fromColumn: suggested.fromColumn || next.fromColumn, toColumn: suggested.toColumn || next.toColumn });
  };
  const pickCardinality = (value) => {   // the one side changes with it: start from that side's key again
    const suggested = suggestedColumns(byId[form.from], byId[form.to], value);
    setForm({ ...form, cardinality: value, fromColumn: suggested.fromColumn || form.fromColumn, toColumn: suggested.toColumn || form.toColumn });
  };
  const save = async () => {
    setSending(true);
    setError("");
    try {
      const payload = relationPayload(form);
      const done = editing ? await updateRelation({ ...payload, id, version: saved.data.version }) : await createRelation(payload);
      window.location.hash = hrefFor({ page: "relation", id: done.id });
    } catch (e) {
      setError(e.message);
      setSending(false);
    }
  };
  const columns = (typeId) => byId[typeId]?.columns ?? [];
  const problem = form ? relationProblem(form, editing) : "";
  const end = (which, label) => (
    <div className="end">
      <div className="field">
        <span className="caption">{label}</span>
        <Select label={label} value={form[which]} onChange={(v) => pickType(which, v)}>
          <option value="">请选择对象类型</option>
          {(types.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}（{t.dataset}）</option>)}
        </Select>
      </div>
      <div className="field">
        <span className="caption">{label}的列（和另一边同一个值）</span>
        <Select label={`${label}的列`} value={form[`${which}Column`]} disabled={!form[which]} onChange={(v) => setForm({ ...form, [`${which}Column`]: v })}>
          <option value="">请选择列</option>
          {columns(form[which]).map((c) => <option key={c.name} value={c.name}>{c.name}（{typeLabel(c.type)}）{byId[form[which]].key.includes(c.name) ? " 主键" : ""}</option>)}
        </Select>
      </div>
    </div>
  );
  const back = editing ? hrefFor({ page: "relation", id }) : hrefFor({ page: "relations" });
  return (
    <main className="page">
      <a className="back" href={back}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {editing ? saved.data?.name ?? "关系" : "关系"}
      </a>
      <div className="page-head"><h1 tabIndex={-1}>{editing ? "修改关系" : "新建关系"}</h1></div>
      {[saved, types].map((s, i) => s.status === "error" && <p key={i} className="error">{s.error}</p>)}
      {form && (
        <div className="stack wide">
          <label className="field">
            <span className="caption">名称</span>
            <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="field">
            <span className="caption">英文名（字母、数字、下划线；{editing ? "建好后不能改" : "确认前也不能再改"}）</span>
            <input type="text" value={form.english} disabled={editing} onChange={(e) => setForm({ ...form, english: e.target.value })} />
          </label>
          <label className="field">
            <span className="caption">说明</span>
            <input type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          {end("from", "起点")}
          <div className="field">
            <span className="caption">一个起点对象对应几个终点对象</span>
            <Select label="基数" value={form.cardinality} onChange={pickCardinality}>
              {Object.entries(CARDINALITY_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </div>
          {end("to", "终点")}
          <p className="hint">保存时会按两个数据集现在的全部行，数出有多少行连得上、哪些键找不到、哪些键重复。多对多要靠一张连接两边的表，这一版还没有。</p>
          {error && <div className="refusal"><p className="error">{error}</p></div>}
          <div className="inline">
            <button className="primary" onClick={save} disabled={Boolean(problem) || sending}>{sending ? "保存中" : editing ? "保存" : "创建"}</button>
            <a href={back}>取消</a>
            {problem && <span className="muted small">{problem}</span>}
          </div>
        </div>
      )}
    </main>
  );
}
