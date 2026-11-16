import React, { useEffect, useRef, useState } from "react";
import { llmClearCache, llmLabel, llmReview, llmState, llmTrial, previewNode } from "./api.js";
import {
  LLM_OUTPUT, LLM_TEMPLATE, TRIAL_MODE, estimateText, fieldCells, friendlyError, insertField, llmRunText, numberText, offListLines, readableSteps, reviewText, stepTitle, updateStep,
} from "./pipelineModel.js";
import { Select } from "./Select.jsx";
import { useSettled } from "./useSettled.js";

const TABS = [["config", "配置"], ["trial", "试跑"], ["review", "样本审核"], ["output", "输出"]];
const earlier = (draft, step) => draft.steps.slice(0, draft.steps.findIndex((s) => s.id === step.id));
const answerText = (values) => (values == null ? "" : values.map((v) => (v == null ? "空" : String(v))).join(" / "));

/** A list of short texts the person edits: the categories of a classification, the answers to choose from. */
function TextList({ legend, items, onChange, add }) {
  return (
    <fieldset className="keys">
      <legend>{legend}</legend>
      {items.map((item, i) => (
        <div className="inline op-row" key={i}>
          <input type="text" aria-label={`${legend} ${i + 1}`} value={item} onChange={(e) => onChange(items.map((x, k) => (k === i ? e.target.value : x)))} />
          <button className="plain" disabled={items.length <= 2} onClick={() => onChange(items.filter((_, k) => k !== i))}>删除</button>
        </div>
      ))}
      <button className="plain" onClick={() => onChange([...items, ""])}>{add}</button>
    </fieldset>
  );
}

function ColumnSelect({ names, value, onChange, label }) {
  return (
    <Select label={label} value={value ?? ""} onChange={onChange}>
      <option value="">选一列</option>
      {names.map((n) => <option key={n} value={n}>{n}</option>)}
    </Select>
  );
}

function ConfigTab({ step, draft, setDraft, names, options, state }) {
  const ref = useRef(null);
  const set = (patch) => setDraft(updateStep(draft, step.id, patch));
  const template = step.template ?? "empty";
  const insert = (n) => {
    const el = ref.current;
    const at = insertField(step.prompt ?? "", el?.selectionStart, el?.selectionEnd, n);
    set({ prompt: at.text });
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at.caret, at.caret); });
  };
  return (
    <div className="op-form">
      <div className="field"><span className="caption">做法</span>
        <Select label="做法" value={template} onChange={(t) => set({ template: t, ...(t === "classify" && !step.categories ? { categories: ["其他"] } : {}), ...(t === "summary" && !step.size ? { size: 30, unit: "字" } : {}), ...(t === "extract" && !step.fields ? { fields: [{ name: "", type: "text" }] } : {}) })}>
          {Object.entries(LLM_TEMPLATE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>
      <div className="field"><span className="caption">读哪一步</span>
        <Select label="读哪一步" value={step.from ?? ""} onChange={(from) => set({ from })}>
          {readableSteps(earlier(draft, step)).map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
        </Select>
      </div>
      <label className="field"><span className="caption">{template === "extract" ? "说明列的名字（错误说明列叫“名字_错误”）" : "新列的名字（错误说明列叫“名字_错误”）"}</span>
        <input type="text" value={step.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
      </label>
      {template === "classify" && (
        <>
          <label className="field"><span className="caption">背景（这是什么数据，可以不写）</span><input type="text" value={step.context ?? ""} onChange={(e) => set({ context: e.target.value })} /></label>
          <div className="field"><span className="caption">要分类的列</span><ColumnSelect label="要分类的列" names={names} value={step.column} onChange={(column) => set({ column })} /></div>
          <TextList legend="类别" items={step.categories ?? []} onChange={(categories) => set({ categories })} add="加一个类别" />
          <p className="hint">最后一类写“其他”，AI 看不出的行才有地方放；不在这个列表里的回答会被数出来，不会写进去。</p>
          <label className="check"><input type="checkbox" checked={!!step.multiple} onChange={(e) => set({ multiple: e.target.checked })} />一行可以属于几个类别</label>
        </>
      )}
      {template === "summary" && (
        <>
          <div className="field"><span className="caption">要概括的列</span><ColumnSelect label="要概括的列" names={names} value={step.column} onChange={(column) => set({ column })} /></div>
          <div className="inline">
            <span>不超过</span>
            <input type="text" inputMode="numeric" aria-label="长度" value={step.size ?? ""} onChange={(e) => set({ size: e.target.value === "" ? "" : Number(e.target.value) || 0 })} />
            <Select label="单位" value={step.unit ?? "字"} onChange={(unit) => set({ unit })}><option value="字">字</option><option value="句">句</option></Select>
          </div>
        </>
      )}
      {template === "extract" && (
        <>
          <div className="field"><span className="caption">从哪一列抽取</span><ColumnSelect label="从哪一列抽取" names={names} value={step.column} onChange={(column) => set({ column })} /></div>
          <fieldset className="keys">
            <legend>抽取的字段，每个字段成为一列</legend>
            {(step.fields ?? []).map((f, i) => (
              <div className="inline op-row" key={i}>
                <input type="text" aria-label={`字段名 ${i + 1}`} value={f.name} onChange={(e) => set({ fields: step.fields.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)) })} />
                <Select label="类型" value={f.type} onChange={(type) => set({ fields: step.fields.map((x, k) => (k === i ? { ...x, type } : x)) })}><option value="text">文字</option><option value="number">数</option></Select>
                <button className="plain" disabled={step.fields.length === 1} onClick={() => set({ fields: step.fields.filter((_, k) => k !== i) })}>删除</button>
              </div>
            ))}
            <button className="plain" onClick={() => set({ fields: [...(step.fields ?? []), { name: "", type: "text" }] })}>加一个字段</button>
          </fieldset>
        </>
      )}
      {template === "empty" && (
        <>
          <label className="field"><span className="caption">提示：用 ${"{列名}"} 把这一行的内容放进去</span>
            <textarea ref={ref} rows={5} value={step.prompt ?? ""} spellCheck={false} onChange={(e) => set({ prompt: e.target.value })} />
          </label>
          <div className="chips" aria-label="点一下把列放进提示">
            {names.map((n) => <button key={n} className="plain" onClick={() => insert(n)}>{n}</button>)}
          </div>
          <div className="field"><span className="caption">答案是</span>
            <Select label="答案类型" value={step.output ?? "text"} onChange={(output) => set({ output, ...(output === "choice" && !step.choices ? { choices: ["是", "否"] } : {}) })}>
              {Object.entries(LLM_OUTPUT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </div>
          {step.output === "choice" && <TextList legend="可选的答案" items={step.choices ?? []} onChange={(choices) => set({ choices })} add="加一个答案" />}
        </>
      )}
      {template !== "empty" && state?.prompt && <div className="field"><span className="caption">发给模型的提示（这一行的内容放在 ${"{…}"} 处）</span><pre className="prompt-box">{state.prompt}</pre></div>}
      <p className="muted small">模型：{options?.model ?? step.model}，和问答用的是同一个，不能换。{options && !options.model_ready && "本机服务没有模型凭据：只能看以前记下的答案，不能试跑和运行。"}</p>
    </div>
  );
}

/** One row of the 试跑 result: the fields, the answer, and the exact prompt, the raw answer and the parsed value behind it. */
function TrialRow({ t, fields, columns }) {
  const [open, setOpen] = useState(false);
  const bad = t.status !== "ok" && t.status !== "skipped";
  return (
    <>
      <tr className={bad ? "changed" : ""}>
        {fieldCells(fields, t.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
        <td><strong>{answerText(t.values) || <span className="faint">空</span>}</strong></td>
        <td className={bad ? "warn" : "muted"}>{t.message ?? (t.cached ? "用的是记下的答案" : "")}</td>
        <td>{t.prompt && <button className="plain" aria-expanded={open} aria-label="看发出去的提示和模型的原话" onClick={() => setOpen(!open)}>{open ? "收起" : "</>"}</button>}</td>
      </tr>
      {open && (
        <tr><td colSpan={fields.length + 3}>
          <div className="trial-detail">
            <p className="caption">发出去的提示（系统）</p><pre className="prompt-box">{t.prompt.system}</pre>
            <p className="caption">发出去的内容</p><pre className="prompt-box">{t.prompt.user}</pre>
            <p className="caption">模型的原话</p><pre className="prompt-box">{t.raw ?? "（没有回答）"}</pre>
            <p className="caption">写进「{columns.slice(0, -1).join("、")}」的值</p><pre className="prompt-box">{answerText(t.values) || "空"}</pre>
          </div>
        </td></tr>
      )}
    </>
  );
}

function TrialTab({ step, draft, name, state }) {
  const [mode, setMode] = useState("sample");
  const [n, setN] = useState(20);
  const [picked, setPicked] = useState([]);
  const [values, setValues] = useState({});
  const [input, setInput] = useState(null);
  const [run, setRun] = useState({ status: "idle" });
  const fields = state?.inputs ?? [];
  useEffect(() => {
    if (mode === "rows" && !input) previewNode(name, draft, step.from).then(setInput, (e) => setInput({ error: e.message }));
  }, [mode]);
  const go = async () => {
    setRun({ status: "loading" });
    const body = mode === "sample" ? { mode, n: Number(n) || 20 } : mode === "rows" ? { mode, rows: picked } : { mode, values };
    try {
      setRun({ status: "ready", data: await llmTrial(name, draft, step.id, body) });
    } catch (e) {
      setRun({ status: "error", error: e.message });
    }
  };
  const columns = input?.columns?.map((c) => c.name) ?? [];
  const fieldIndex = fields.map((f) => columns.indexOf(f));
  const ready = mode === "sample" ? Number(n) > 0 : mode === "rows" ? picked.length > 0 : fields.some((f) => values[f]);
  return (
    <div className="op-form">
      <div className="ways">
        {Object.entries(TRIAL_MODE).map(([k, v]) => <label key={k}><input type="radio" name={`trial-${step.id}`} checked={mode === k} onChange={() => setMode(k)} />{v}</label>)}
      </div>
      {mode === "sample" && <label className="field"><span className="caption">抽几行（不同内容的行，随机）</span><input type="text" inputMode="numeric" value={n} onChange={(e) => setN(e.target.value)} /></label>}
      {mode === "values" && fields.map((f) => <label className="field" key={f}><span className="caption">{f}</span><textarea rows={2} value={values[f] ?? ""} onChange={(e) => setValues({ ...values, [f]: e.target.value })} /></label>)}
      {mode === "rows" && (
        <div className="table-wrap panel-table tall-small">
          {input?.error && <p className="error">{friendlyError(input.error, draft.steps)}</p>}
          {!input && <p className="muted">加载中</p>}
          {input?.rows && (
            <table>
              <thead><tr><th></th>{fields.map((f) => <th key={f}>{f}</th>)}</tr></thead>
              <tbody>{input.rows.map((r, i) => (
                <tr key={i}>
                  <td><input type="checkbox" aria-label={`选第 ${i + 1} 行`} checked={picked.includes(i)} onChange={(e) => setPicked(e.target.checked ? [...picked, i] : picked.filter((p) => p !== i))} /></td>
                  {fieldIndex.map((k, j) => <td key={j} className="cell">{k < 0 || r[k] == null ? "空" : String(r[k])}</td>)}
                </tr>
              ))}</tbody>
            </table>
          )}
          <p className="muted small">这是这一步前 100 行，勾几行用来试跑。</p>
        </div>
      )}
      <div className="inline"><button className="secondary" disabled={!ready || run.status === "loading"} onClick={go}>{run.status === "loading" ? "试跑中，模型在答" : "用这些行试跑"}</button><span className="muted small">会调用模型；答出来的会记下，正式运行时不再问。</span></div>
      {run.status === "error" && <p className="error">{friendlyError(run.error, draft.steps)}</p>}
      {run.data && (
        <div>
          <p className="muted small">{run.data.basis === "样本" ? "样本：" : ""}{run.data.trials.length} 行，不是这一步的全部行。点 {"</>"} 看发给模型的提示和它的原话。</p>
          <div className="table-wrap panel-table">
            <table>
              <thead><tr>{run.data.fields.map((f) => <th key={f}>{f}</th>)}<th>答案</th><th>说明</th><th></th></tr></thead>
              <tbody>{run.data.trials.map((t, i) => <TrialRow key={i} t={t} fields={run.data.fields} columns={run.data.columns} />)}</tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/** What a person writes for one row they label: a choice for a list of answers, a text for the rest, a field each for an extraction. */
function ExpectedInput({ state, value, onChange }) {
  if (state.kind === "extract") {
    return <div className="expected">{state.fields.map((f) => <input key={f.name} type="text" aria-label={`期望的${f.name}`} placeholder={f.name} value={value?.[f.name] ?? ""} onChange={(e) => onChange({ ...(value ?? {}), [f.name]: e.target.value })} />)}</div>;
  }
  if (state.kind === "choice") {
    return <Select label="期望的答案" value={value ?? ""} onChange={onChange}><option value="">选</option>{state.choices.map((c) => <option key={c} value={c}>{c}</option>)}</Select>;
  }
  return <input type="text" aria-label="期望的答案" placeholder={state.kind === "choices" ? "几个用“；”隔开" : state.kind === "number" ? "一个数" : "期望的答案"} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
}

const expectedDone = (state, v) => (state.kind === "extract" ? state.fields.some((f) => String(v?.[f.name] ?? "").trim()) : String(v ?? "").trim() !== "");

function ReviewTab({ step, draft, setDraft, name, state, dirty, reload }) {
  const [rows, setRows] = useState(null);
  const [expected, setExpected] = useState({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const review = state.review;
  const guard = async (what, go) => {
    setBusy(what);
    setError("");
    try {
      await go();
    } catch (e) {
      setError(friendlyError(e.message, draft.steps));
    }
    setBusy("");
  };
  const draw = () => guard("draw", async () => {
    const got = await llmTrial(name, draft, step.id, { mode: "draw", n: 20, exclude_labelled: true });
    setRows(got.trials);
    setExpected({});
  });
  const save = () => guard("save", async () => {
    const labels = rows.filter((r) => expectedDone(state, expected[r.row_hash])).map((r) => ({ fields: r.fields, expected: state.kind === "extract" ? expected[r.row_hash] : expected[r.row_hash] }));
    await llmLabel(name, draft, step.id, labels);
    setRows(null);
    reload();
  });
  const rerun = () => guard("review", async () => {
    setResult(await llmReview(name, draft, step.id));
    reload();
  });
  const remove = (hash) => guard("remove", async () => {
    await llmLabel(name, draft, step.id, [], [hash]);
    reload();
  });
  if (!review.reviewable) return <p className="muted">概括没有标准答案，不做样本审核。这一列仍然标着“AI 生成”。</p>;
  return (
    <div className="op-form">
      <p className={review.passed ? "ok" : ""}><strong>{reviewText(review)}</strong>{review.who && review.matched != null && <span className="muted small">　{review.who} 核对的</span>}</p>
      {dirty && <p className="warn small">管道有没保存的改动：先保存。标注属于保存过的这个节点。</p>}
      <label className="field"><span className="caption">样本里至少对上几行才算通过（你来定，系统不替你定）</span>
        <input type="text" inputMode="numeric" value={step.min_match ?? ""} onChange={(e) => setDraft(updateStep(draft, step.id, { min_match: e.target.value === "" ? undefined : Number(e.target.value) || 0 }))} />
      </label>
      <div className="inline wide">
        <button className="secondary" disabled={dirty || busy !== ""} onClick={draw}>{busy === "draw" ? "抽样中" : "抽 20 行来标注"}</button>
        <button className="secondary" disabled={dirty || busy !== "" || !review.labelled} onClick={rerun}>{busy === "review" ? "核对中，模型在答" : "按现在的提示核对一遍"}</button>
      </div>
      {error && <p className="error">{error}</p>}
      {rows && (
        <div>
          <p className="muted small">先写下你期望的答案，再核对；写了几行存几行。不同内容的行才抽，相同内容的行只算一行。</p>
          <div className="table-wrap panel-table">
            <table>
              <thead><tr>{state.inputs.map((f) => <th key={f}>{f}</th>)}<th>你期望的答案</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.row_hash}>
                  {fieldCells(state.inputs, r.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
                  <td><ExpectedInput state={state} value={expected[r.row_hash]} onChange={(v) => setExpected({ ...expected, [r.row_hash]: v })} /></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="inline"><button className="primary" disabled={busy !== "" || !rows.some((r) => expectedDone(state, expected[r.row_hash]))} onClick={save}>保存标注</button><button className="plain" onClick={() => setRows(null)}>放弃</button></div>
        </div>
      )}
      {result && (
        <div>
          <p className="caption">核对结果：{result.total} 行里 {result.matched} 行对上（样本，不是全部行）</p>
          <div className="table-wrap panel-table">
            <table>
              <thead><tr>{state.inputs.map((f) => <th key={f}>{f}</th>)}<th>期望</th><th>AI 答的</th></tr></thead>
              <tbody>{result.rows.map((r) => (
                <tr key={r.row_hash} className={r.matched ? "" : "changed"}>
                  {fieldCells(state.inputs, r.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
                  <td>{typeof r.expected === "object" ? Object.values(r.expected).join(" / ") : String(r.expected)}</td>
                  <td className={r.matched ? "ok" : "warn"}>{answerText(r.values) || r.message || "空"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
      {state.labels.length > 0 && !rows && (
        <details>
          <summary>已标注的 {state.labels.length} 行</summary>
          <div className="table-wrap panel-table">
            <table>
              <tbody>{state.labels.map((l) => (
                <tr key={l.row_hash}>
                  {fieldCells(state.inputs, l.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
                  <td>{typeof l.expected === "object" ? Object.values(l.expected).join(" / ") : String(l.expected)}</td>
                  <td><button className="plain" disabled={busy !== "" || dirty} onClick={() => remove(l.row_hash)}>去掉</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function OutputTab({ state, name, step, draft, reload }) {
  const [error, setError] = useState("");
  const clear = async () => {
    if (!window.confirm(`清空这个节点记下的 ${numberText(state.cache.current)} 条答案？下次运行每一行都要重新问模型。`)) return;
    try {
      await llmClearCache(name, draft, step.id);
      reload();
    } catch (e) {
      setError(e.message);
    }
  };
  const r = state.report;
  return (
    <div className="op-form">
      <div>
        <p className="caption">这个节点写出的列，都标着“AI 生成”</p>
        <ul className="plain-list">{state.columns.map((c, i) => <li key={c}>{c} <span className="badge badge-ai">AI 生成</span>{i === state.columns.length - 1 && <span className="muted small">　说明这一行为什么是空的</span>}</li>)}</ul>
      </div>
      <p className="muted small">样本审核通过、另一位确认这条管道之前，这些列可以筛选、分组，不能当主键，也不能成为已确认的代码含义。</p>
      <div>
        <p className="caption">按现在的数据，全部 {numberText(r.rows)} 行</p>
        <p>{llmRunText(r)}</p>
        {offListLines(r).map((l) => <p key={l} className="warn small">{l}</p>)}
      </div>
      {r.to_call > 0 && <p className="muted small">{estimateText(state.estimate)}。</p>}
      {state.recompute && <p className="warn small">下次运行会重算：{state.recompute.why.join("；")}。</p>}
      <div className="inline"><button className="plain" disabled={!state.cache.current && !state.cache.stale} onClick={clear}>清空记下的答案（{numberText(state.cache.current + state.cache.stale)} 条）</button></div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

/** The editor of an AI step: 配置 / 试跑 / 样本审核 / 输出. */
export function LlmEditor({ step, draft, setDraft, nodes, name, options, dirty }) {
  const [tab, setTab] = useState("config");
  const [round, setRound] = useState(0);
  const names = (nodes[step.from]?.column_types ?? []).map((c) => c.name);
  const state = useSettled(() => llmState(name, draft, step.id), JSON.stringify([draft, step.id, round]));
  const data = state.data;
  return (
    <div className="llm-editor">
      <div className="panel-tabs llm-tabs" role="tablist" aria-label="AI 步骤">
        {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      {state.status === "error" && <p className="error">{friendlyError(state.error, draft.steps)}</p>}
      {data?.recompute && tab === "config" && <p className="warn small">改了提示、模型或答案的形式：以前记下的 {data.cache.stale} 条答案不再用，运行时 {numberText(data.recompute.rows)} 次调用全部重算。</p>}
      {data && <p className="muted small">{llmRunText(data.report)}</p>}
      {tab === "config" && <ConfigTab step={step} draft={draft} setDraft={setDraft} names={names} options={options} state={data} />}
      {data && tab === "trial" && <TrialTab step={step} draft={draft} name={name} state={data} />}
      {data && tab === "review" && <ReviewTab step={step} draft={draft} setDraft={setDraft} name={name} state={data} dirty={dirty} reload={() => setRound(round + 1)} />}
      {data && tab === "output" && <OutputTab state={data} name={name} step={step} draft={draft} reload={() => setRound(round + 1)} />}
      {!data && tab !== "config" && state.status === "loading" && <p className="muted">加载中</p>}
    </div>
  );
}
