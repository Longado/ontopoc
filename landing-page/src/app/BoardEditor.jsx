import React, { useState } from "react";
import { BoardCards } from "./BoardsPage.jsx";
import { GroupColumns, GroupShape } from "./ChartView.jsx";
import { createBoard, getBoard, getBoards, getExploreMeta, getTypes, previewBoard, updateBoard } from "./api.js";
import { COMPONENT_KINDS, REFRESH_OPTIONS, SCOPE_LABEL, draftOf, draftProblem, emptyComponent, emptyDraft, payloadOf, specOf } from "./boardModel.js";
import { fnOptions } from "./explorerModel.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { useSettled } from "./useSettled.js";

function ComponentForm({ c, metas, types, onChange, onRemove }) {
  const meta = metas[c.type];
  const fields = meta?.fields ?? [];
  const numeric = fields.filter((f) => f.numeric);
  const needsNumber = c.kind === "histogram" || c.kind === "table";
  const measure = fields.find((f) => f.key === c.measure);
  const set = (patch) => onChange({ ...c, ...patch });
  return (
    <fieldset className="component">
      <div className="inline wide">
        <input type="text" aria-label="组件标题" placeholder="标题，例如 有效订单数" value={c.title} onChange={(e) => set({ title: e.target.value })} />
        <button className="plain" onClick={onRemove}>去掉</button>
      </div>
      <div className="op-row inline wide">
        <Select label="对象类型" value={c.type} onChange={(v) => set({ type: v, view: "", group: "", measure: "", fn: "count" })}>
          {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
        <Select label="视图" value={c.view} onChange={(v) => set({ view: v })}>
          <option value="">全部行</option>
          {(meta?.views ?? []).map((v) => <option key={v.id} value={v.id}>{v.name}{v.state === "confirmed" ? "" : "（未确认）"}</option>)}
        </Select>
        <Select label="种类" value={c.kind} onChange={(v) => set({ kind: v, group: ["histogram", "number", "rows"].includes(v) ? "" : c.group, measure: v === "histogram" || v === "table" ? (numeric[0]?.key ?? "") : c.measure })}>
          {COMPONENT_KINDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
      </div>
      {["bar", "pie", "table"].includes(c.kind) && (
        <div className="op-row inline wide">
          <Select label="分组" value={c.group} onChange={(v) => set({ group: v })}>
            <option value="">{c.kind === "table" ? "不分组" : "按哪一列分组"}</option>
            <GroupColumns fields={fields} reach={meta?.reach} />
          </Select>
          {c.group && <GroupShape top={c.top} order={c.order} onChange={set} />}
        </div>
      )}
      {c.kind !== "rows" && (
        <div className="op-row inline wide">
          <Select label="量哪一列" value={c.measure} onChange={(v) => set({ measure: v, fn: fnOptions(fields.find((f) => f.key === v), meta?.aggregations ?? {}).includes(c.fn) ? c.fn : "count" })}>
            {!needsNumber && <option value="">行数</option>}
            {(needsNumber ? numeric : fields).map((f) => <option key={f.key} value={f.key}>{f.name}</option>)}
          </Select>
          {["number", "bar", "pie"].includes(c.kind) && (
            <Select label="统计方式" value={c.fn} onChange={(v) => set({ fn: v })}>
              {fnOptions(measure, meta?.aggregations ?? {}).filter((fn) => c.kind !== "pie" || fn === "count" || fn === "sum").map((fn) => <option key={fn} value={fn}>{meta?.aggregations?.[fn] ?? fn}</option>)}
            </Select>
          )}
        </div>
      )}
      {c.filters?.length > 0 && <p className="muted small">带着 {c.filters.length} 个固定条件（保存时留下的）</p>}
    </fieldset>
  );
}

/** A board's form: components, the filter bar, who may open it, when it ends and how often it reads; the board is worked out beside it as you change it. */
export function BoardEditor({ id }) {
  const [saved] = useLoad(() => (id ? getBoard(id) : Promise.resolve(null)), [id]);
  if (id && saved.status === "error") return <main className="page"><p className="error">{saved.error}</p></main>;
  if (id && !saved.data) return <main className="page"><p className="muted">加载中</p></main>;
  return <Editor id={id} board={saved.data} />;
}

function Editor({ id, board }) {
  const [draft, setDraft] = useState(() => (board ? draftOf(board) : emptyDraft()));
  const [types] = useLoad(() => getTypes(), []);
  const [people] = useLoad(() => getBoards().then((b) => b.people), []);
  const used = [...new Set(draft.components.map((c) => c.type))];
  const [metas] = useLoad(() => Promise.all(used.map((t) => getExploreMeta(t))).then((all) => Object.fromEntries(all.map((m) => [m.type.id, m]))), [used.join("|")]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const usable = (types.data ?? []);
  const problem = draftProblem(draft);
  const preview = useSettled(() => (draft.components.length && draft.components.every((c) => c.title.trim()) ? previewBoard(specOf(draft)) : Promise.resolve(null)), JSON.stringify(specOf(draft)), 600);
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
      <a className="back" href={id ? `#/boards/${id}` : "#/boards"}>
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {id ? board.name : "看板"}
      </a>
      <h1 tabIndex={-1}>{id ? "修改看板" : "新建看板"}</h1>
      <div className="stack wide">
        <label className="field"><span className="caption">名称</span>
          <input type="text" aria-label="看板名称" value={draft.name} maxLength={40} onChange={(e) => set({ name: e.target.value })} />
        </label>
        <h2 className="section">组件</h2>
        {draft.components.map((c, i) => (
          <ComponentForm key={c.id} c={c} metas={metas.data ?? {}} types={usable} onChange={(next) => set({ components: draft.components.map((x, j) => (j === i ? next : x)) })} onRemove={() => set({ components: draft.components.filter((_, j) => j !== i) })} />
        ))}
        <div className="inline">
          <button className="secondary" disabled={!usable.length || draft.components.length >= 12}
            onClick={() => set({ components: [...draft.components, emptyComponent(draft.components.at(-1)?.type ?? usable[0].id, Math.max(0, ...draft.components.map((c) => Number(c.id.slice(1)) || 0)) + 1)] })}>加组件</button>
          {!usable.length && types.status !== "loading" && <span className="muted small">还没有对象类型</span>}
        </div>
        <h2 className="section">筛选条</h2>
        {draft.filters.map((f, i) => (
          <div className="inline wide" key={i}>
            <Select label="筛选的字段" value={f.field} onChange={(v) => set({ filters: draft.filters.map((x, j) => (j === i ? { field: v, label: allFields.find(([k]) => k === v)?.[1] ?? v } : x)) })}>
              <option value="">选字段</option>
              {allFields.map(([k, name]) => <option key={k} value={k}>{name}</option>)}
            </Select>
            <input type="text" aria-label="筛选项名称" value={f.label} onChange={(e) => set({ filters: draft.filters.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} />
            <button className="plain" onClick={() => set({ filters: draft.filters.filter((_, j) => j !== i) })}>去掉</button>
          </div>
        ))}
        <div className="inline"><button className="secondary" disabled={draft.filters.length >= 4 || !allFields.length} onClick={() => set({ filters: [...draft.filters, { field: "", label: "" }] })}>加筛选项</button></div>
        <h2 className="section">发布</h2>
        <fieldset className="ways">
          {Object.entries(SCOPE_LABEL).map(([k, label]) => (
            <label key={k}><input type="radio" name="scope" checked={draft.scope === k} onChange={() => set({ scope: k })} /> {label}</label>
          ))}
        </fieldset>
        {draft.scope === "named" && (
          <fieldset className="keys">
            <legend>可以打开的人</legend>
            {(people.data ?? []).map((p) => (
              <label key={p.id}>
                <input type="checkbox" checked={draft.visible_to.includes(p.id)} onChange={(e) => set({ visible_to: e.target.checked ? [...draft.visible_to, p.id] : draft.visible_to.filter((i) => i !== p.id) })} /> {p.name}
              </label>
            ))}
          </fieldset>
        )}
        <label className="field"><span className="caption">到期日（不写就不过期）</span>
          <input type="date" aria-label="到期日" value={draft.expires_at} onChange={(e) => set({ expires_at: e.target.value })} />
        </label>
        <label className="field"><span className="caption">刷新间隔</span>
          <Select label="刷新间隔" value={String(draft.refresh_seconds)} onChange={(v) => set({ refresh_seconds: Number(v) })}>
            {REFRESH_OPTIONS.map(([s, label]) => <option key={s} value={s}>{label}</option>)}
          </Select>
        </label>
        <p className="muted small">分享链接打开时仍要先登录，并且要在发布范围里；没有匿名访问。</p>
        <div className="inline">
          <button className="primary" disabled={busy || Boolean(problem)} onClick={save}>{id ? "保存修改" : "创建看板"}</button>
          {problem && <span className="muted small">{problem}</span>}
        </div>
        {error && <p className="error" role="alert">{error}</p>}
      </div>
      {preview.data && (
        <>
          <h2 className="section">现在的样子</h2>
          <BoardCards data={preview.data} />
        </>
      )}
      {preview.status === "error" && <p className="error">{preview.error}</p>}
    </main>
  );
}
