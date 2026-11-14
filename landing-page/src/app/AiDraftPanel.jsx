import React, { useEffect, useRef, useState } from "react";
import { aiDraft, llmState } from "./api.js";
import { QuestionList, SeesNote } from "./AiBox.jsx";
import { estimateText, failureLines, friendlyError, kindLine, llmRunText, numberText, rememberPrompt, rowsText, stepTitle } from "./pipelineModel.js";

const storeKey = (name) => `pipeline-ai-prompts:${name}`;
const readPrompts = (name) => {
  try {
    return JSON.parse(window.localStorage.getItem(storeKey(name)) ?? "[]");
  } catch {
    return [];
  }
};

/** The AI button's panel: the nodes to work on (chosen first: they bound what the model may read), a sentence, and the draft that comes back, with the questions it must ask and our check. 应用 puts ordinary steps into the draft; nothing exists before that. */
export function AiDraftPanel({ name, spec, selected, onApply, onClose }) {
  const ref = useRef(null);
  const [chosen, setChosen] = useState(selected && spec.steps.find((s) => s.id === selected)?.type !== "output" ? [selected] : []);
  const [text, setText] = useState("");
  const [recent, setRecent] = useState(() => readPrompts(name));
  const [state, setState] = useState({ status: "idle" });
  const [answers, setAnswers] = useState({});
  useEffect(() => { ref.current.showModal(); }, []);
  const ask = async (more = {}) => {
    setState((s) => ({ ...s, status: "loading" }));
    try {
      setState({ status: "ready", data: await aiDraft(name, spec, chosen, text, more) });
    } catch (e) {
      setState({ status: "error", error: e.message });
    }
  };
  const generate = () => {
    const next = rememberPrompt(recent, { text, selected: chosen });
    setRecent(next);
    window.localStorage.setItem(storeKey(name), JSON.stringify(next));
    setAnswers({});
    ask();
  };
  const answer = (id, values) => {
    const next = { ...answers, [id]: values };
    setAnswers(next);
    ask({ raw: state.data.raw, answers: next });
  };
  const d = state.data;
  const loading = state.status === "loading";
  const open = d ? d.questions.filter((q) => !(answers[q.id] ?? []).length).length : 0;
  const pickable = spec.steps.filter((s) => s.type !== "output");
  return (
    <dialog ref={ref} className="upload wide-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      <div className="dialog-body">
        <h2>AI 编排</h2>
        <fieldset className="keys">
          <legend>用哪些节点（AI 只能读选中的）</legend>
          {pickable.map((s) => (
            <label key={s.id}><input type="checkbox" checked={chosen.includes(s.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, s.id] : chosen.filter((c) => c !== s.id))} />{kindLine(s)}：{stepTitle(s, spec.steps)}</label>
          ))}
        </fieldset>
        <label className="field"><span className="caption">想做什么</span>
          <textarea rows={3} value={text} placeholder="例如：按客户汇总订单金额，剔除已取消订单" onChange={(e) => setText(e.target.value)} />
        </label>
        {recent.length > 0 && (
          <div className="field"><span className="caption">以前写过的</span>
            <ul className="plain-list">{recent.map((r) => <li key={r.text}><button className="plain" onClick={() => { setText(r.text); setChosen(r.selected.filter((id) => spec.steps.some((s) => s.id === id))); }}>{r.text}</button></li>)}</ul>
          </div>
        )}
        <div className="inline"><button className="secondary" disabled={!chosen.length || !text.trim() || loading} onClick={generate}>{loading ? "AI 在写" : "生成草稿"}</button>{!chosen.length && <span className="muted small">先选节点</span>}</div>
        {state.status === "error" && <p className="error">{friendlyError(state.error, spec.steps)}</p>}
        {d && (
          <div className="ai-draft">
            <p className="caption">{d.label}{d.basis && `：${d.basis}`}</p>
            <ol className="draft-steps">
              {d.steps.map((s) => (
                <li key={s.id}>
                  <p><strong>{s.summary}</strong> <span className="muted small">{kindLine(s.step)}</span></p>
                  {s.rows_in && <p className="muted small">{s.rows_in.map(numberText).join(" + ")} 行 → {rowsText(s.rows_out)}{s.to_call != null && `；${numberText(s.to_call)} 次模型调用才能出全部答案`}</p>}
                  {(s.operators ?? []).map((o, i) => <p key={i} className="muted small">{o.text}</p>)}
                  {failureLines({ failures: s.failures }).map((l) => <p key={l} className="warn small">{l}</p>)}
                </li>
              ))}
            </ol>
            {d.cites.map((c) => <p key={c.text} className="small">{c.text}</p>)}
            <QuestionList questions={d.questions} answers={answers} onAnswer={answer} busy={loading} />
            {d.check.ok ? <p className="ok small">我们这边检查过了：{d.check.dry_run}</p> : <p className="bad small">{friendlyError(d.check.error, spec.steps)}</p>}
            {open > 0 && d.check.ok && <p className="warn small">还有 {open} 个问题没回答：这些条件现在没有写进去，应用后这一步会多留下行。</p>}
            <SeesNote sees={d.sees} />
          </div>
        )}
      </div>
      <div className="actions">
        <span></span>
        <button className="plain" onClick={onClose}>放弃</button>
        <button className="primary" disabled={!d?.check.ok || !d.steps.length || loading} onClick={() => { onApply(d.steps); onClose(); }}>应用</button>
      </div>
    </dialog>
  );
}

/** Before a run that asks the model: for each AI step what the run would call, what is kept, what is skipped, and the estimate; the run starts only when the person says so. */
export function RunDialog({ name, spec, onGo, onClose }) {
  const ref = useRef(null);
  const llmSteps = spec.steps.filter((s) => s.type === "llm");
  const [states, setStates] = useState({});
  const [error, setError] = useState("");
  useEffect(() => {
    ref.current.showModal();
    Promise.all(llmSteps.map((s) => llmState(name, spec, s.id).then((d) => [s.id, d]))).then((all) => setStates(Object.fromEntries(all)), (e) => setError(e.message));
  }, []);
  const ready = llmSteps.every((s) => states[s.id]);
  return (
    <dialog ref={ref} className="upload" onCancel={(e) => { e.preventDefault(); onClose(); }}>
      <div className="dialog-body">
        <h2>运行前，AI 步骤要调用模型</h2>
        {error && <p className="error">{friendlyError(error, spec.steps)}</p>}
        {!ready && !error && <p className="muted">在数现在的数据</p>}
        {llmSteps.map((s) => {
          const d = states[s.id];
          return d && (
            <div key={s.id} className="run-llm">
              <p><strong>{stepTitle(s, spec.steps)}</strong> <span className="muted small">{d.model_now ?? d.model_node}</span></p>
              <p className="small">全部 {numberText(d.report.rows)} 行：{numberText(d.report.answered)} 行已有记下的答案，{numberText(d.report.skipped)} 行跳过（提示用到的列都是空的），{numberText(d.report.pending)} 行要问模型</p>
              <p className="small">{estimateText(d.estimate)}</p>
              {d.recompute && <p className="warn small">提示、模型或答案的形式改过，以前记下的 {numberText(d.cache.stale)} 条答案不再用：{d.recompute.why.join("；")}</p>}
              <p className="muted small">已有：{llmRunText({ ...d.report, pending: 0 })}</p>
            </div>
          );
        })}
      </div>
      <div className="actions">
        <span></span>
        <button className="plain" onClick={onClose}>取消</button>
        <button className="primary" disabled={!ready} onClick={() => { onClose(); onGo(); }}>开始运行</button>
      </div>
    </dialog>
  );
}
