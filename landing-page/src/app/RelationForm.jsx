import React, { useEffect, useState } from "react";
import { createRelation, getRelation, getRelationForm, previewRelation, updateRelation } from "./api.js";
import { typeLabel } from "./format.js";
import { t } from "./i18n/index.js";
import { CARDINALITY_LABEL, previewPayload, previewText, relationPayload, relationProblem, suggestedColumns } from "./relationModel.js";
import { RelationPage, RelationsPage } from "./RelationsPage.jsx";
import { hrefFor } from "./routeModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { Drawer } from "./ui/Drawer.jsx";

/** What the two columns would connect, read before anything is saved: a line under the two ends ("157/160 rows can connect, 3 have no match"). */
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
  if (state.status === "idle") return <p className="preview muted small">{t("relations.form.previewIdle")}</p>;
  if (state.status === "loading") return <p className="preview muted small">{t("relations.form.previewLoading")}</p>;
  if (state.status === "error") return <p className="preview warn small">{state.error}</p>;
  const d = state.data;
  const bad = d.unmatched > 0 || d.empty > 0 || d.matched < d.rows;
  return (
    <div className={`preview ${bad ? "preview-warn" : "preview-ok"}`} role="status">
      <strong>{previewText(d)}</strong>
      <span className="muted small">{t("relations.form.previewNote", { many: d.many_name, one: d.one_name, fan: d.fan_keys > 0 ? t("relations.form.previewFan", { one: d.one_name, count: d.fan_keys }) : "" })}</span>
    </div>
  );
}

/** Making a relation and changing one, in a drawer over the relation's own page: the names, then the two ends side by side (From / To, each a type and its column) with the
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

  const byId = Object.fromEntries((types.data ?? []).map((ty) => [ty.id, ty]));
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
        <span className="caption">{t("relations.form.type")}</span>
        <Select label={t("relations.form.typeLabel", { end: label })} value={form[which]} onChange={(v) => pickType(which, v)}>
          <option value="">{t("relations.form.pickType")}</option>
          {(types.data ?? []).map((ty) => <option key={ty.id} value={ty.id}>{t("relations.form.typeOption", { name: ty.name, dataset: ty.dataset })}</option>)}
        </Select>
      </div>
      <div className="field">
        <span className="caption">{t("relations.form.column")}</span>
        <Select label={t("relations.form.columnLabel", { end: label })} value={form[`${which}Column`]} disabled={!form[which]} onChange={(v) => setForm({ ...form, [`${which}Column`]: v })}>
          <option value="">{t("relations.form.pickColumn")}</option>
          {columns(form[which]).map((c) => <option key={c.name} value={c.name}>{t("relations.form.columnOption", { name: c.name, type: typeLabel(c.type), key: byId[form[which]].key.includes(c.name) ? t("relations.form.keyMark") : "" })}</option>)}
        </Select>
      </div>
    </div>
  );
  return (
    <>
      {editing ? <RelationPage route={{ id }} /> : <RelationsPage route={{}} />}
      <Drawer open title={editing ? t("relations.form.edit") : t("relations.form.new")} onClose={close} width={760}
        footer={(
          <>
            {problem && <span className="save-reason" role="status">{problem}</span>}
            <button className="secondary" onClick={close}>{t("common.cancel")}</button>
            <button className="primary" onClick={save} disabled={Boolean(problem) || sending}>{sending ? t("relations.form.saving") : editing ? t("common.save") : t("relations.form.create")}</button>
          </>
        )}>
        {[saved, types].map((s, i) => s.status === "error" && <p key={i} className="error">{s.error}</p>)}
        {!form && !(saved.status === "error" || types.status === "error") && <p className="muted">{t("common.loading")}</p>}
        {form && (
          <div className="rel-form">
            <div className="rel-form-names">
              <label className="field">
                <span className="caption">{t("relations.form.name")}</span>
                <input type="text" value={form.name} maxLength={40} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="field">
                <span className="caption">{t("relations.form.english", { fixed: editing ? t("relations.form.fixedEdit") : t("relations.form.fixedNew") })}</span>
                <input type="text" value={form.english} disabled={editing} onChange={(e) => setForm({ ...form, english: e.target.value })} />
              </label>
              <label className="field">
                <span className="caption">{t("relations.form.description")}</span>
                <input type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </label>
            </div>
            <div className="rel-form-ends">
              {end("from", t("relations.form.from"), t("relations.form.fromHint"))}
              <span className="rel-arrow" aria-hidden="true">→</span>
              {end("to", t("relations.form.to"), t("relations.form.toHint"))}
            </div>
            <div className="field">
              <span className="caption">{t("relations.form.cardinality")}</span>
              <Select label={t("relations.form.cardinalityLabel")} value={form.cardinality} onChange={pickCardinality}>
                {Object.entries(CARDINALITY_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </Select>
            </div>
            <Preview form={form} />
            <p className="hint">{t("relations.form.manyToMany")}</p>
            {error && <div className="refusal"><p className="error">{error}</p></div>}
          </div>
        )}
      </Drawer>
    </>
  );
}
