import React, { useState } from "react";
import { BoardCards } from "./BoardsPage.jsx";
import { GroupColumns, GroupShape } from "./ChartView.jsx";
import { createBoard, getBoard, getBoards, getExploreMeta, getTypes, previewBoard, updateBoard } from "./api.js";
import { componentKinds, draftIssue, draftOf, draftProblem, emptyComponent, emptyDraft, isParamIssue, payloadOf, refreshOptions, scopeOptions, specOf } from "./boardModel.js";
import { fnOptions } from "./explorerModel.js";
import { useT } from "./i18n/index.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { useSettled } from "./useSettled.js";

function ComponentForm({ c, metas, types, onChange, onRemove }) {
  const t = useT();
  const meta = metas[c.type];
  const fields = meta?.fields ?? [];
  const numeric = fields.filter((f) => f.numeric);
  const needsNumber = c.kind === "histogram" || c.kind === "table";
  const measure = fields.find((f) => f.key === c.measure);
  const set = (patch) => onChange({ ...c, ...patch });
  const kinds = (
    <Select label={t("boards.form.kind")} value={c.kind} onChange={(v) => set({ kind: v, type: v === "query" ? c.type : c.type || types[0]?.id || "", group: ["histogram", "number", "rows", "query"].includes(v) ? "" : c.group, measure: v === "histogram" || v === "table" ? (numeric[0]?.key ?? "") : c.measure })}>
      {componentKinds().map(([k, label]) => <option key={k} value={k}>{label}</option>)}
    </Select>
  );
  if (c.kind === "query") {
    return (
      <fieldset className="component">
        <div className="inline wide">
          <input type="text" aria-label={t("boards.form.componentTitle")} placeholder={t("boards.form.queryTitlePlaceholder")} value={c.title} onChange={(e) => set({ title: e.target.value })} />
          {kinds}
          <button className="plain" onClick={onRemove}>{t("boards.form.remove")}</button>
        </div>
        <div className="query">
          <textarea aria-label={t("ask.query.aria")} rows={4} spellCheck={false} value={c.text} placeholder={t("boards.form.queryPlaceholder")} onChange={(e) => set({ text: e.target.value })} />
        </div>
        <p className="muted small">{t("boards.form.queryNote")}</p>
      </fieldset>
    );
  }
  return (
    <fieldset className="component">
      <div className="inline wide">
        <input type="text" aria-label={t("boards.form.componentTitle")} placeholder={t("boards.form.titlePlaceholder")} value={c.title} onChange={(e) => set({ title: e.target.value })} />
        <button className="plain" onClick={onRemove}>{t("boards.form.remove")}</button>
      </div>
      <div className="op-row inline wide">
        <Select label={t("boards.form.type")} value={c.type} onChange={(v) => set({ type: v, view: "", group: "", measure: "", fn: "count" })}>
          {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
        <Select label={t("boards.form.view")} value={c.view} onChange={(v) => set({ view: v })}>
          <option value="">{t("boards.form.allRows")}</option>
          {(meta?.views ?? []).map((v) => <option key={v.id} value={v.id}>{v.name}{v.state === "confirmed" ? "" : t("boards.form.unconfirmed")}</option>)}
        </Select>
        {kinds}
      </div>
      {["bar", "pie", "table"].includes(c.kind) && (
        <div className="op-row inline wide">
          <Select label={t("boards.form.group")} value={c.group} onChange={(v) => set({ group: v })}>
            <option value="">{c.kind === "table" ? t("boards.form.noGroup") : t("boards.form.groupBy")}</option>
            <GroupColumns fields={fields} reach={meta?.reach} current={c.group} />
          </Select>
          {c.group && <GroupShape top={c.top} order={c.order} onChange={set} />}
        </div>
      )}
      {c.kind !== "rows" && (
        <div className="op-row inline wide">
          <Select label={t("boards.form.measure")} value={c.measure} onChange={(v) => set({ measure: v, fn: fnOptions(fields.find((f) => f.key === v), meta?.aggregations ?? {}).includes(c.fn) ? c.fn : "count" })}>
            {!needsNumber && <option value="">{t("boards.form.rowCount")}</option>}
            {(needsNumber ? numeric : fields).map((f) => <option key={f.key} value={f.key}>{f.name}</option>)}
          </Select>
          {["number", "bar", "pie"].includes(c.kind) && (
            <Select label={t("boards.form.fn")} value={c.fn} onChange={(v) => set({ fn: v })}>
              {fnOptions(measure, meta?.aggregations ?? {}).filter((fn) => c.kind !== "pie" || fn === "count" || fn === "sum").map((fn) => <option key={fn} value={fn}>{meta?.aggregations?.[fn] ?? fn}</option>)}
            </Select>
          )}
        </div>
      )}
      {c.filters?.length > 0 && <p className="muted small">{t("boards.form.fixed", { count: c.filters.length })}</p>}
    </fieldset>
  );
}

/** A board's form: components, the filter bar, who may open it, when it ends and how often it reads; the board is worked out beside it as you change it. */
export function BoardEditor({ id }) {
  const t = useT();
  const [saved] = useLoad(() => (id ? getBoard(id) : Promise.resolve(null)), [id]);
  if (id && saved.status === "error") return <main className="page"><p className="error">{saved.error}</p></main>;
  if (id && !saved.data) return <main className="page"><p className="muted">{t("boards.loading")}</p></main>;
  return <Editor id={id} board={saved.data} />;
}

function Editor({ id, board }) {
  const t = useT();
  const [draft, setDraft] = useState(() => (board ? draftOf(board) : emptyDraft()));
  const [types] = useLoad(() => getTypes(), []);
  const [people] = useLoad(() => getBoards().then((b) => b.people), []);
  const used = [...new Set(draft.components.filter((c) => c.kind !== "query" && c.type).map((c) => c.type))];
  const [metas] = useLoad(() => Promise.all(used.map((t) => getExploreMeta(t))).then((all) => Object.fromEntries(all.map((m) => [m.type.id, m]))), [used.join("|")]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const usable = (types.data ?? []);
  const problem = draftProblem(draft);
  const ready = draft.components.length && draft.components.every((c) => c.title.trim() && (c.kind !== "query" || c.text.trim())) && !isParamIssue(draftIssue(draft));
  const preview = useSettled(() => (ready ? previewBoard(specOf(draft)) : Promise.resolve(null)), JSON.stringify(specOf(draft)), 600);
  const set = (patch) => setDraft({ ...draft, ...patch });
  const allFields = [...new Map(Object.values(metas.data ?? {}).flatMap((m) => m.fields.filter((f) => !f.derived).map((f) => [f.key, f.name]))).entries()];
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const body = id ? await updateBoard({ ...payloadOf(draft), id, version: board.version }) : await createBoard(payloadOf(draft));
      window.location.hash = `#/boards/${body.id}`;
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("boards.title"), href: "#/boards" }, ...(id ? [{ label: board.name, href: `#/boards/${id}` }] : []), { label: id ? t("boards.form.edit") : t("boards.form.new") }]}
        title={id ? t("boards.form.edit") : t("boards.form.new")} />
      <div className="stack wide">
        <label className="field"><span className="caption">{t("boards.form.name")}</span>
          <input type="text" aria-label={t("boards.form.boardName")} value={draft.name} maxLength={40} onChange={(e) => set({ name: e.target.value })} />
        </label>
        <h2 className="section">{t("boards.form.components")}</h2>
        {draft.components.map((c, i) => (
          <ComponentForm key={c.id} c={c} metas={metas.data ?? {}} types={usable} onChange={(next) => set({ components: draft.components.map((x, j) => (j === i ? next : x)) })} onRemove={() => set({ components: draft.components.filter((_, j) => j !== i) })} />
        ))}
        <div className="inline">
          <button className="secondary" disabled={!usable.length || draft.components.length >= 12}
            onClick={() => set({ components: [...draft.components, emptyComponent(draft.components.at(-1)?.type ?? usable[0].id, Math.max(0, ...draft.components.map((c) => Number(c.id.slice(1)) || 0)) + 1)] })}>{t("boards.form.addComponent")}</button>
          {!usable.length && types.status !== "loading" && <span className="muted small">{t("boards.form.noTypes")}</span>}
        </div>
        <h2 className="section">{t("boards.form.filters")}</h2>
        {draft.filters.map((f, i) => (
          <div className="inline wide" key={i}>
            <Select label={t("boards.form.filterField")} value={f.field} onChange={(v) => set({ filters: draft.filters.map((x, j) => (j === i ? { field: v, label: allFields.find(([k]) => k === v)?.[1] ?? v } : x)) })}>
              <option value="">{t("boards.form.pickField")}</option>
              {allFields.map(([k, name]) => <option key={k} value={k}>{name}</option>)}
            </Select>
            <Select label={t("objects.filter.compare")} value={f.op ?? "eq"} onChange={(op) => set({ filters: draft.filters.map((x, j) => j === i ? { ...x, op } : x) })}>
              <option value="eq">{t("objects.op.eq")}</option>
              <option value="name_is">{t("objects.op.name_is")}</option>
            </Select>
            <input type="text" aria-label={t("boards.form.filterLabel")} value={f.label} onChange={(e) => set({ filters: draft.filters.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} />
            <button className="plain" onClick={() => set({ filters: draft.filters.filter((_, j) => j !== i) })}>{t("boards.form.remove")}</button>
          </div>
        ))}
        <div className="inline"><button className="secondary" disabled={draft.filters.length >= 4 || !allFields.length} onClick={() => set({ filters: [...draft.filters, { field: "", label: "" }] })}>{t("boards.form.addFilter")}</button></div>
        <h2 className="section">{t("boards.form.params")}</h2>
        <p className="muted small">{t("boards.form.paramsNote")}</p>
        {(draft.params ?? []).map((p, i) => (
          <div className="inline wide" key={i}>
            <input type="text" aria-label={t("boards.form.paramName")} placeholder={t("boards.form.paramNamePlaceholder")} value={p.name} onChange={(e) => set({ params: draft.params.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
            <input type="text" aria-label={t("boards.form.paramLabel")} placeholder={t("boards.form.paramLabelPlaceholder")} value={p.label} onChange={(e) => set({ params: draft.params.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} />
            <input type="text" aria-label={t("boards.form.paramDefault")} placeholder={t("boards.form.paramDefault")} value={p.default} onChange={(e) => set({ params: draft.params.map((x, j) => (j === i ? { ...x, default: e.target.value } : x)) })} />
            <button className="plain" onClick={() => set({ params: draft.params.filter((_, j) => j !== i) })}>{t("boards.form.remove")}</button>
          </div>
        ))}
        <div className="inline"><button className="secondary" disabled={(draft.params ?? []).length >= 4} onClick={() => set({ params: [...(draft.params ?? []), { name: "", label: "", default: "" }] })}>{t("boards.form.addParam")}</button></div>
        <h2 className="section">{t("boards.form.publish")}</h2>
        <fieldset className="ways">
          {scopeOptions().map(([k, label]) => (
            <label key={k}><input type="radio" name="scope" checked={draft.scope === k} onChange={() => set({ scope: k })} /> {label}</label>
          ))}
        </fieldset>
        {draft.scope === "named" && (
          <fieldset className="keys">
            <legend>{t("boards.form.people")}</legend>
            {(people.data ?? []).map((p) => (
              <label key={p.id}>
                <input type="checkbox" checked={draft.visible_to.includes(p.id)} onChange={(e) => set({ visible_to: e.target.checked ? [...draft.visible_to, p.id] : draft.visible_to.filter((i) => i !== p.id) })} /> {p.name}
              </label>
            ))}
          </fieldset>
        )}
        <label className="field"><span className="caption">{t("boards.form.expires")}</span>
          <input type="date" aria-label={t("boards.form.expiresAria")} value={draft.expires_at} onChange={(e) => set({ expires_at: e.target.value })} />
        </label>
        <label className="field"><span className="caption">{t("boards.form.refresh")}</span>
          <Select label={t("boards.form.refresh")} value={String(draft.refresh_seconds)} onChange={(v) => set({ refresh_seconds: Number(v) })}>
            {refreshOptions().map(([s, label]) => <option key={s} value={s}>{label}</option>)}
          </Select>
        </label>
        <p className="muted small">{t("boards.form.shareNote")}</p>
        <div className="inline">
          <button className="primary" disabled={busy || Boolean(problem)} onClick={save}>{id ? t("boards.form.save") : t("boards.form.create")}</button>
          {problem && <span className="muted small">{problem}</span>}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </div>
      {preview.data && (
        <>
          <h2 className="section">{t("boards.form.preview")}</h2>
          <BoardCards data={preview.data} />
        </>
      )}
      {preview.status === "error" && <p className="error">{preview.error}</p>}
    </main>
  );
}
