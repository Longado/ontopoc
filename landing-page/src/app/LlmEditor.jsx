import React, { useEffect, useRef, useState } from "react";
import { llmClearCache, llmLabel, llmReview, llmState, llmTrial, previewNode } from "./api.js";
import {
  LLM_OUTPUT, LLM_TEMPLATE, TRIAL_MODE, estimateText, fieldCells, friendlyError, insertField, llmRunText, numberText, offListLines, readableSteps, reviewText, stepTitle, updateStep,
} from "./pipelineModel.js";
import { t } from "./i18n/index.js";
import { Select } from "./Select.jsx";
import { useSettled } from "./useSettled.js";

const tabs = () => [["config", t("steps.llm.tab.config")], ["trial", t("steps.llm.tab.trial")], ["review", t("steps.llm.tab.review")], ["output", t("steps.llm.tab.output")]];
const earlier = (draft, step) => draft.steps.slice(0, draft.steps.findIndex((s) => s.id === step.id));
const answerText = (values) => (values == null ? "" : values.map((v) => (v == null ? t("steps.llm.null") : String(v))).join(" / "));

/** A list of short texts the person edits: the categories of a classification, the answers to choose from. */
function TextList({ legend, items, onChange, add }) {
  return (
    <fieldset className="keys">
      <legend>{legend}</legend>
      {items.map((item, i) => (
        <div className="inline op-row" key={i}>
          <input type="text" aria-label={`${legend} ${i + 1}`} value={item} onChange={(e) => onChange(items.map((x, k) => (k === i ? e.target.value : x)))} />
          <button className="plain" disabled={items.length <= 2} onClick={() => onChange(items.filter((_, k) => k !== i))}>{t("steps.llm.delete")}</button>
        </div>
      ))}
      <button className="plain" onClick={() => onChange([...items, ""])}>{add}</button>
    </fieldset>
  );
}

function ColumnSelect({ names, value, onChange, label }) {
  return (
    <Select label={label} value={value ?? ""} onChange={onChange}>
      <option value="">{t("steps.llm.pickCol")}</option>
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
      <div className="field"><span className="caption">{t("steps.llm.c.how")}</span>
        <Select label={t("steps.llm.c.how")} value={template} onChange={(tpl) => set({ template: tpl, ...(tpl === "classify" && !step.categories ? { categories: [t("steps.llm.c.otherCat")] } : {}), ...(tpl === "summary" && !step.size ? { size: 30, unit: t("steps.llm.raw.char") } : {}), ...(tpl === "extract" && !step.fields ? { fields: [{ name: "", type: "text" }] } : {}) })}>
          {Object.entries(LLM_TEMPLATE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>
      <div className="field"><span className="caption">{t("steps.llm.c.reads")}</span>
        <Select label={t("steps.llm.c.reads")} value={step.from ?? ""} onChange={(from) => set({ from })}>
          {readableSteps(earlier(draft, step)).map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
        </Select>
      </div>
      <label className="field"><span className="caption">{template === "extract" ? t("steps.llm.c.nameExtract") : t("steps.llm.c.nameNew")}</span>
        <input type="text" value={step.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
      </label>
      {template === "classify" && (
        <>
          <label className="field"><span className="caption">{t("steps.llm.c.context")}</span><input type="text" value={step.context ?? ""} onChange={(e) => set({ context: e.target.value })} /></label>
          <div className="field"><span className="caption">{t("steps.llm.c.classifyCol")}</span><ColumnSelect label={t("steps.llm.c.classifyCol")} names={names} value={step.column} onChange={(column) => set({ column })} /></div>
          <TextList legend={t("steps.llm.c.categories")} items={step.categories ?? []} onChange={(categories) => set({ categories })} add={t("steps.llm.c.addCategory")} />
          <p className="hint">{t("steps.llm.c.catHint")}</p>
          <label className="check"><input type="checkbox" checked={!!step.multiple} onChange={(e) => set({ multiple: e.target.checked })} />{t("steps.llm.c.multiple")}</label>
        </>
      )}
      {template === "summary" && (
        <>
          <div className="field"><span className="caption">{t("steps.llm.c.summaryCol")}</span><ColumnSelect label={t("steps.llm.c.summaryCol")} names={names} value={step.column} onChange={(column) => set({ column })} /></div>
          <div className="inline">
            <span>{t("steps.llm.c.atMost")}</span>
            <input type="text" inputMode="numeric" aria-label={t("steps.llm.c.length")} value={step.size ?? ""} onChange={(e) => set({ size: e.target.value === "" ? "" : Number(e.target.value) || 0 })} />
            <Select label={t("steps.llm.c.unit")} value={step.unit ?? t("steps.llm.raw.char")} onChange={(unit) => set({ unit })}><option value={t("steps.llm.raw.char")}>{t("steps.llm.c.unitChar")}</option><option value={t("steps.llm.raw.sentence")}>{t("steps.llm.c.unitSentence")}</option></Select>
          </div>
        </>
      )}
      {template === "extract" && (
        <>
          <div className="field"><span className="caption">{t("steps.llm.c.extractCol")}</span><ColumnSelect label={t("steps.llm.c.extractCol")} names={names} value={step.column} onChange={(column) => set({ column })} /></div>
          <fieldset className="keys">
            <legend>{t("steps.llm.c.fields")}</legend>
            {(step.fields ?? []).map((f, i) => (
              <div className="inline op-row" key={i}>
                <input type="text" aria-label={t("steps.llm.c.fieldName", { n: i + 1 })} value={f.name} onChange={(e) => set({ fields: step.fields.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)) })} />
                <Select label={t("steps.llm.c.type")} value={f.type} onChange={(type) => set({ fields: step.fields.map((x, k) => (k === i ? { ...x, type } : x)) })}><option value="text">{t("steps.llm.c.text")}</option><option value="number">{t("steps.llm.c.number")}</option></Select>
                <button className="plain" disabled={step.fields.length === 1} onClick={() => set({ fields: step.fields.filter((_, k) => k !== i) })}>{t("steps.llm.delete")}</button>
              </div>
            ))}
            <button className="plain" onClick={() => set({ fields: [...(step.fields ?? []), { name: "", type: "text" }] })}>{t("steps.llm.c.addField")}</button>
          </fieldset>
        </>
      )}
      {template === "empty" && (
        <>
          <label className="field"><span className="caption">{t("steps.llm.c.prompt")}</span>
            <textarea ref={ref} rows={5} value={step.prompt ?? ""} spellCheck={false} onChange={(e) => set({ prompt: e.target.value })} />
          </label>
          <div className="chips" aria-label={t("steps.llm.c.chips")}>
            {names.map((n) => <button key={n} className="plain" onClick={() => insert(n)}>{n}</button>)}
          </div>
          <div className="field"><span className="caption">{t("steps.llm.c.answerIs")}</span>
            <Select label={t("steps.llm.c.answerType")} value={step.output ?? "text"} onChange={(output) => set({ output, ...(output === "choice" && !step.choices ? { choices: [t("steps.llm.c.yes"), t("steps.llm.c.no")] } : {}) })}>
              {Object.entries(LLM_OUTPUT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </div>
          {step.output === "choice" && <TextList legend={t("steps.llm.c.choices")} items={step.choices ?? []} onChange={(choices) => set({ choices })} add={t("steps.llm.c.addChoice")} />}
        </>
      )}
      {template !== "empty" && state?.prompt && <div className="field"><span className="caption">{t("steps.llm.c.sent")}</span><pre className="prompt-box">{state.prompt}</pre></div>}
      <p className="muted small">{t("steps.llm.c.model", { model: options?.model ?? step.model })} {options && !options.model_ready && t("steps.llm.c.noKey")}</p>
    </div>
  );
}

/** One row of the 试跑 result: the fields, the answer, and the exact prompt, the raw answer and the parsed value behind it. */
function TrialRow({ row, fields, columns }) {
  const [open, setOpen] = useState(false);
  const bad = row.status !== "ok" && row.status !== "skipped";
  return (
    <>
      <tr className={bad ? "changed" : ""}>
        {fieldCells(fields, row.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
        <td><strong>{answerText(row.values) || <span className="faint">{t("steps.llm.null")}</span>}</strong></td>
        <td className={bad ? "warn" : "muted"}>{row.message ?? (row.cached ? t("steps.llm.t.cached") : "")}</td>
        <td>{row.prompt && <button className="plain" aria-expanded={open} aria-label={t("steps.llm.t.seePrompt")} onClick={() => setOpen(!open)}>{open ? t("steps.llm.t.collapse") : "</>"}</button>}</td>
      </tr>
      {open && (
        <tr><td colSpan={fields.length + 3}>
          <div className="trial-detail">
            <p className="caption">{t("steps.llm.t.system")}</p><pre className="prompt-box">{row.prompt.system}</pre>
            <p className="caption">{t("steps.llm.t.user")}</p><pre className="prompt-box">{row.prompt.user}</pre>
            <p className="caption">{t("steps.llm.t.raw")}</p><pre className="prompt-box">{row.raw ?? t("steps.llm.t.noAnswer")}</pre>
            <p className="caption">{t("steps.llm.t.written", { columns: columns.slice(0, -1).join(", ") })}</p><pre className="prompt-box">{answerText(row.values) || t("steps.llm.null")}</pre>
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
      {mode === "sample" && <label className="field"><span className="caption">{t("steps.llm.r.sampleN")}</span><input type="text" inputMode="numeric" value={n} onChange={(e) => setN(e.target.value)} /></label>}
      {mode === "values" && fields.map((f) => <label className="field" key={f}><span className="caption">{f}</span><textarea rows={2} value={values[f] ?? ""} onChange={(e) => setValues({ ...values, [f]: e.target.value })} /></label>)}
      {mode === "rows" && (
        <div className="table-wrap panel-table tall-small">
          {input?.error && <p className="error">{friendlyError(input.error, draft.steps)}</p>}
          {!input && <p className="muted">{t("steps.llm.loading")}</p>}
          {input?.rows && (
            <table>
              <thead><tr><th></th>{fields.map((f) => <th key={f}>{f}</th>)}</tr></thead>
              <tbody>{input.rows.map((r, i) => (
                <tr key={i}>
                  <td><input type="checkbox" aria-label={t("steps.llm.r.pickRow", { n: i + 1 })} checked={picked.includes(i)} onChange={(e) => setPicked(e.target.checked ? [...picked, i] : picked.filter((p) => p !== i))} /></td>
                  {fieldIndex.map((k, j) => <td key={j} className="cell">{k < 0 || r[k] == null ? t("steps.llm.null") : String(r[k])}</td>)}
                </tr>
              ))}</tbody>
            </table>
          )}
          <p className="muted small">{t("steps.llm.r.first100")}</p>
        </div>
      )}
      <div className="inline"><button className="secondary" disabled={!ready || run.status === "loading"} onClick={go}>{run.status === "loading" ? t("steps.llm.r.going") : t("steps.llm.r.go")}</button><span className="muted small">{t("steps.llm.r.calls")}</span></div>
      {run.status === "error" && <p className="error">{friendlyError(run.error, draft.steps)}</p>}
      {run.data && (
        <div>
          <p className="muted small">{run.data.basis === t("steps.llm.r.basis") ? t("steps.llm.r.sample") : ""}{t("steps.llm.r.summary", { count: run.data.trials.length })}</p>
          <div className="table-wrap panel-table">
            <table>
              <thead><tr>{run.data.fields.map((f) => <th key={f}>{f}</th>)}<th>{t("steps.llm.r.answer")}</th><th>{t("steps.llm.r.note")}</th><th></th></tr></thead>
              <tbody>{run.data.trials.map((tr, i) => <TrialRow key={i} row={tr} fields={run.data.fields} columns={run.data.columns} />)}</tbody>
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
    return <div className="expected">{state.fields.map((f) => <input key={f.name} type="text" aria-label={t("steps.llm.e.field", { name: f.name })} placeholder={f.name} value={value?.[f.name] ?? ""} onChange={(e) => onChange({ ...(value ?? {}), [f.name]: e.target.value })} />)}</div>;
  }
  if (state.kind === "choice") {
    return <Select label={t("steps.llm.e.answer")} value={value ?? ""} onChange={onChange}><option value="">{t("steps.llm.e.pick")}</option>{state.choices.map((c) => <option key={c} value={c}>{c}</option>)}</Select>;
  }
  return <input type="text" aria-label={t("steps.llm.e.answer")} placeholder={state.kind === "choices" ? t("steps.llm.e.several") : state.kind === "number" ? t("steps.llm.e.oneNumber") : t("steps.llm.e.answer")} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
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
  if (!review.reviewable) return <p className="muted">{t("steps.llm.v.none")}</p>;
  return (
    <div className="op-form">
      <p className={review.passed ? "ok" : ""}><strong>{reviewText(review)}</strong>{review.who && review.matched != null && <span className="muted small"> {t("steps.llm.v.checkedBy", { who: review.who })}</span>}</p>
      {dirty && <p className="warn small">{t("steps.llm.v.dirty")}</p>}
      <label className="field"><span className="caption">{t("steps.llm.v.min")}</span>
        <input type="text" inputMode="numeric" value={step.min_match ?? ""} onChange={(e) => setDraft(updateStep(draft, step.id, { min_match: e.target.value === "" ? undefined : Number(e.target.value) || 0 }))} />
      </label>
      <div className="inline wide">
        <button className="secondary" disabled={dirty || busy !== ""} onClick={draw}>{busy === "draw" ? t("steps.llm.v.drawing") : t("steps.llm.v.draw")}</button>
        <button className="secondary" disabled={dirty || busy !== "" || !review.labelled} onClick={rerun}>{busy === "review" ? t("steps.llm.v.reviewing") : t("steps.llm.v.review")}</button>
      </div>
      {error && <p className="error">{error}</p>}
      {rows && (
        <div>
          <p className="muted small">{t("steps.llm.v.rowsHint")}</p>
          <div className="table-wrap panel-table">
            <table>
              <thead><tr>{state.inputs.map((f) => <th key={f}>{f}</th>)}<th>{t("steps.llm.v.yourAnswer")}</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.row_hash}>
                  {fieldCells(state.inputs, r.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
                  <td><ExpectedInput state={state} value={expected[r.row_hash]} onChange={(v) => setExpected({ ...expected, [r.row_hash]: v })} /></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="inline"><button className="primary" disabled={busy !== "" || !rows.some((r) => expectedDone(state, expected[r.row_hash]))} onClick={save}>{t("steps.llm.v.save")}</button><button className="plain" onClick={() => setRows(null)}>{t("steps.llm.v.discard")}</button></div>
        </div>
      )}
      {result && (
        <div>
          <p className="caption">{t("steps.llm.v.result", { total: result.total, matched: result.matched })}</p>
          <div className="table-wrap panel-table">
            <table>
              <thead><tr>{state.inputs.map((f) => <th key={f}>{f}</th>)}<th>{t("steps.llm.v.expected")}</th><th>{t("steps.llm.v.aiAnswer")}</th></tr></thead>
              <tbody>{result.rows.map((r) => (
                <tr key={r.row_hash} className={r.matched ? "" : "changed"}>
                  {fieldCells(state.inputs, r.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
                  <td>{typeof r.expected === "object" ? Object.values(r.expected).join(" / ") : String(r.expected)}</td>
                  <td className={r.matched ? "ok" : "warn"}>{answerText(r.values) || r.message || t("steps.llm.null")}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      )}
      {state.labels.length > 0 && !rows && (
        <details>
          <summary>{t("steps.llm.v.labelled", { count: state.labels.length })}</summary>
          <div className="table-wrap panel-table">
            <table>
              <tbody>{state.labels.map((l) => (
                <tr key={l.row_hash}>
                  {fieldCells(state.inputs, l.fields).map((c, i) => <td key={i} className="cell">{c}</td>)}
                  <td>{typeof l.expected === "object" ? Object.values(l.expected).join(" / ") : String(l.expected)}</td>
                  <td><button className="plain" disabled={busy !== "" || dirty} onClick={() => remove(l.row_hash)}>{t("steps.llm.v.remove")}</button></td>
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
    if (!window.confirm(t("steps.llm.o.clear", { count: numberText(state.cache.current) }))) return;
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
        <p className="caption">{t("steps.llm.o.cols")}</p>
        <ul className="plain-list">{state.columns.map((c, i) => <li key={c}>{c} <span className="badge badge-ai">{t("steps.llm.o.badge")}</span>{i === state.columns.length - 1 && <span className="muted small"> {t("steps.llm.o.why")}</span>}</li>)}</ul>
      </div>
      <p className="muted small">{t("steps.llm.o.notice")}</p>
      <div>
        <p className="caption">{t("steps.llm.o.now", { count: numberText(r.rows) })}</p>
        <p>{llmRunText(r)}</p>
        {offListLines(r).map((l) => <p key={l} className="warn small">{l}</p>)}
      </div>
      {r.to_call > 0 && <p className="muted small">{t("steps.llm.o.estimate", { text: estimateText(state.estimate) })}</p>}
      {state.recompute && <p className="warn small">{t("steps.llm.o.recompute", { why: state.recompute.why.join("; ") })}</p>}
      <div className="inline"><button className="plain" disabled={!state.cache.current && !state.cache.stale} onClick={clear}>{t("steps.llm.o.clearBtn", { count: numberText(state.cache.current + state.cache.stale) })}</button></div>
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
      <div className="panel-tabs llm-tabs" role="tablist" aria-label={t("steps.llm.title")}>
        {tabs().map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>)}
      </div>
      {state.status === "error" && <p className="error">{friendlyError(state.error, draft.steps)}</p>}
      {data?.recompute && tab === "config" && <p className="warn small">{t("steps.llm.changed", { stale: data.cache.stale, calls: numberText(data.recompute.rows) })}</p>}
      {data && <p className="muted small">{llmRunText(data.report)}</p>}
      {tab === "config" && <ConfigTab step={step} draft={draft} setDraft={setDraft} names={names} options={options} state={data} />}
      {data && tab === "trial" && <TrialTab step={step} draft={draft} name={name} state={data} />}
      {data && tab === "review" && <ReviewTab step={step} draft={draft} setDraft={setDraft} name={name} state={data} dirty={dirty} reload={() => setRound(round + 1)} />}
      {data && tab === "output" && <OutputTab state={data} name={name} step={step} draft={draft} reload={() => setRound(round + 1)} />}
      {!data && tab !== "config" && state.status === "loading" && <p className="muted">{t("steps.llm.loading")}</p>}
    </div>
  );
}
