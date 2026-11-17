import React, { useEffect, useState } from "react";
import { createRelation, getRelation, getRelationForm, previewRelation, updateRelation } from "./api.js";
import { typeLabel } from "./format.js";
import { CARDINALITY_LABEL, previewPayload, previewText, relationPayload, relationProblem, suggestedColumns } from "./relationModel.js";
import { RelationPage, RelationsPage } from "./RelationsPage.jsx";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { Drawer } from "./ui/Drawer.jsx";

/** What the two columns would connect, read before anything is saved: a line under the two ends ("能连上 157/160 行，3 行找不到"). */
function Preview({ form }) {
  const [state, setState] = useState({ status: "idle" });
  const payload = previewPayload(form);
  const key = payload ? JSON.stringify(payload) : "";
  useEffect(() => {
    if (!key) {
      setState({ status: "idle" });
      return undefined;
    }
    let alive = true;
    setState({ status: "loading" });
    const timer = setTimeout(() => {
      previewRelation(JSON.parse(key)).then((data) => alive && setState({ status: "ready", data }), (e) => alive && setState({ status: "error", error: e.message }));
    }, 250);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [key]);
  if (state.status === "idle") return <p className="preview muted small">选好两边的对象类型和列，这里会先数出能连上多少行。</p>;
  if (state.status === "loading") return <p className="preview muted small">正在数…</p>;
  if (state.status === "error") return <p className="preview warn small">{state.error}</p>;
  const d = state.data;
  const bad = d.unmatched > 0 || d.empty > 0 || d.matched < d.rows;
  return (
    <div className={`preview ${bad ? "preview-warn" : "preview-ok"}`} role="status">
      <strong>{previewText(d)}</strong>
      <span className="muted small">{d.many_name} → {d.one_name}，按现在的全部数据数的，保存后还会再数一次。{d.fan_keys > 0 ? `“${d.one_name}”里有 ${d.fan_keys} 个键重复。` : ""}</span>
    </div>
  );
}

/** Making a relation and changing one, in a drawer over the relation's own page: the names, then the two ends side by side (起点 / 终点, each a type and its column) with the
 * cardinality between them, and the match preview before anything is saved. */
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
  const back = editing ? hrefFor({ page: "relation", id }) : hrefFor({ page: "relations" });
  const close = () => { window.location.hash = back; };
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
  const end = (which, label, hint) => (
    <div className="end">
      <h3 className="end-title">{label}<span className="muted small"> {hint}</span></h3>
      <div className="field">
        <span className="caption">对象类型</span>
        <Select label={`${label}的对象类型`} value={form[which]} onChange={(v) => pickType(which, v)}>
          <option value="">请选择对象类型</option>
          {(types.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}（{t.dataset}）</option>)}
        </Select>
      </div>
      <div className="field">
        <span className="caption">用哪一列连（和另一边同一个值）</span>
        <Select label={`${label}的列`} value={form[`${which}Column`]} disabled={!form[which]} onChange={(v) => setForm({ ...form, [`${which}Column`]: v })}>
          <option value="">请选择列</option>
          {columns(form[which]).map((c) => <option key={c.name} value={c.name}>{c.name}（{typeLabel(c.type)}）{byId[form[which]].key.includes(c.name) ? " 主键" : ""}</option>)}
        </Select>
      </div>
    </div>
  );
  return (
    <>
      {editing ? <RelationPage route={{ id }} /> : <RelationsPage route={{}} />}
      <Drawer open title={editing ? "修改关系" : "新建关系"} onClose={close} width={760}
        footer={(
          <>
            {problem && <span className="save-reason" role="status">{problem}</span>}
            <button className="secondary" onClick={close}>取消</button>
            <button className="primary" onClick={save} disabled={Boolean(problem) || sending}>{sending ? "保存中" : editing ? "保存" : "创建"}</button>
          </>
        )}>
        {[saved, types].map((s, i) => s.status === "error" && <p key={i} className="error">{s.error}</p>)}
        {!form && !(saved.status === "error" || types.status === "error") && <p className="muted">加载中</p>}
        {form && (
          <div className="rel-form">
            <div className="rel-form-names">
              <label className="field">
                <span className="caption">名称（线上会写这个，比如“订单属于客户”）</span>
                <input type="text" value={form.name} maxLength={40} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="field">
                <span className="caption">英文名（字母、数字、下划线；{editing ? "建好后不能改" : "确认前也不能再改"}）</span>
                <input type="text" value={form.english} disabled={editing} onChange={(e) => setForm({ ...form, english: e.target.value })} />
              </label>
              <label className="field">
                <span className="caption">说明（可以不写）</span>
                <input type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </label>
            </div>
            <div className="rel-form-ends">
              {end("from", "起点", "“多”的一端，比如订单")}
              {end("to", "终点", "“一”的一端，比如客户")}
            </div>
            <div className="field">
              <span className="caption">一个起点对象对应几个终点对象</span>
              <Select label="基数" value={form.cardinality} onChange={pickCardinality}>
                {Object.entries(CARDINALITY_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </Select>
            </div>
            <Preview form={form} />
            <p className="hint">多对多要靠一张连接两边的表，这一版还没有。</p>
            {error && <div className="refusal"><p className="error">{error}</p></div>}
          </div>
        )}
      </Drawer>
    </>
  );
}
