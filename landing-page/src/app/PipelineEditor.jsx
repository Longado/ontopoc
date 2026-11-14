import React, { useEffect, useState } from "react";
import { getDatasets, getPipelineOptions, pipelineSummary, previewNode, runPipeline, savePipeline } from "./api.js";
import { PipelineBar } from "./PipelineBar.jsx";
import { PipelineGraph } from "./PipelineGraph.jsx";
import { PipelinePanel } from "./PipelinePanel.jsx";
import { KIND_LABEL, addStep, kindLine, newStep, orphans, sameSpec, stepTitle } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { StepEditor } from "./StepEditors.jsx";

const ADDABLE = ["input", "join", "transform", "output"];

/** Runs `load` a moment after `key` stops changing; what it returns is {status, data, error}. The last good data stays while the next is worked out. */
function useSettled(load, key, wait = 350) {
  const [state, setState] = useState({ status: "loading" });
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      setState((s) => ({ ...s, status: "loading", error: "" }));
      load().then((data) => live && setState({ status: "ready", data }), (e) => live && setState((s) => ({ status: "error", data: s.data, error: e.message })));
    }, wait);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [key]);
  return state;
}

/** The editing page: steps on the left, the graph in the middle, the selected step's editor on the right, rows / columns / statistics / log below. Nothing is saved until 保存. */
export function PipelineEditor({ detail, reload }) {
  const name = detail.name;
  const [draft, setDraft] = useState(detail.spec);
  const [selected, setSelected] = useState(detail.spec.steps[detail.spec.steps.length - 1]?.id ?? null);
  const [tab, setTab] = useState("rows");
  const [upto, setUpto] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setDraft(detail.spec);
  }, [detail.version]);
  useEffect(() => {
    getDatasets().then(setDatasets, () => {});
    getPipelineOptions().then((o) => setCatalog(o.operators), () => {});
  }, []);
  const dirty = !sameSpec(draft, detail.spec);
  const step = draft.steps.find((s) => s.id === selected) ?? null;
  const summary = useSettled(() => pipelineSummary(name, draft), JSON.stringify(draft));
  const nodes = Object.fromEntries((summary.data?.nodes ?? []).map((n) => [n.id, n]));
  const preview = useSettled(() => (step && tab !== "log" ? previewNode(name, draft, step.id, upto) : Promise.resolve(null)), JSON.stringify([draft, selected, upto, tab === "log"]));
  const hasOutput = draft.steps.some((s) => s.type === "output");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await savePipeline(name, detail.version, draft);
      reload();
    } catch (e) {
      setError(e.message);
    }
    setSaving(false);
  };
  const run = async () => {
    setRunning(true);
    setError("");
    try {
      const made = await runPipeline(name);
      window.location.hash = hrefFor({ page: "pipeline", name, view: "run", run: made.id });
    } catch (e) {
      setError(e.message);
      setRunning(false);
    }
  };
  const add = (kind) => {
    const made = newStep(draft.steps, kind, selected, datasets.map((d) => d.name));
    setDraft(addStep(draft, made));
    setSelected(made.id);
    setUpto(null);
  };
  const select = (id) => {
    setSelected(id);
    setUpto(null);
  };
  const lost = new Set(orphans(draft.steps));
  return (
    <div className="pl">
      <PipelineBar detail={detail} view="edit">
        <span className={`saved${dirty ? " unsaved" : ""}`}>{dirty ? "有改动还没保存" : `已保存，第 ${detail.definition_version} 版`}</span>
        <button className="secondary" onClick={save} disabled={!dirty || saving}>{saving ? "保存中" : "保存"}</button>
        <button className="primary" onClick={run} disabled={dirty || running || !hasOutput} title={dirty ? "先保存" : !hasOutput ? "要有一个输出才能运行" : ""}>{running ? "运行中" : "运行"}</button>
      </PipelineBar>
      {error && <p className="error pl-error">{error} {error.includes("被改了") && <button className="plain" onClick={reload}>重新载入</button>}</p>}
      {summary.status === "error" && <p className="error pl-error">{summary.error}</p>}
      {summary.status === "ready" && summary.data.error && <p className="error pl-error">{summary.data.error}（图里只算到这一步之前）</p>}
      <div className="pl-grid">
        <aside className="pl-steps" aria-label="步骤">
          <ol>
            {draft.steps.map((s) => (
              <li key={s.id}>
                <button className={`step-item${selected === s.id ? " on" : ""}`} onClick={() => select(s.id)} aria-current={selected === s.id ? "true" : undefined}>
                  <span className="step-kind">{kindLine(s)}{lost.has(s.id) && "，不会运行"}</span>
                  <span className="step-title">{stepTitle(s, draft.steps)}</span>
                </button>
              </li>
            ))}
          </ol>
          <div className="step-add">
            <p className="caption">加一步</p>
            {ADDABLE.map((k) => <button key={k} className="plain" onClick={() => add(k)}>{KIND_LABEL[k]}</button>)}
          </div>
        </aside>
        <section className="pl-graph" aria-label="管道图">
          <PipelineGraph steps={draft.steps} nodes={nodes} selected={selected} onSelect={select} />
        </section>
        <section className="pl-editor" aria-label="编辑这一步">
          <StepEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} datasets={datasets} name={name} catalog={catalog} onPreviewTo={(i) => { setUpto(i); setTab("rows"); }} onRemoved={() => setSelected(null)} />
        </section>
        <section className="pl-bottom" aria-label="这一步的内容">
          <PipelinePanel tab={tab} setTab={setTab} preview={preview} upto={upto} onClearUpto={() => setUpto(null)} name={name} step={step} steps={draft.steps} node={step ? nodes[step.id] : null} />
        </section>
      </div>
    </div>
  );
}
