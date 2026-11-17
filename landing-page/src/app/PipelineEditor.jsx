import React, { useEffect, useState } from "react";
import { getDatasets, getPipelineOptions, getPipelineRun, pipelineSummary, previewNode, runPipeline, savePipeline } from "./api.js";
import { AiDraftPanel, RunDialog } from "./AiDraftPanel.jsx";
import { PipelineBar } from "./PipelineBar.jsx";
import { PipelineGraph } from "./PipelineGraph.jsx";
import { PipelinePanel } from "./PipelinePanel.jsx";
import { KIND_LABEL, addStep, allIssues, applyDraft, durationText, friendlyError, kindLine, newStep, numberText, orphans, runBlockReason, runResults, sameSpec, stepTitle, withBranchNodes } from "./pipelineModel.js";
import { hrefFor } from "./routeModel.js";
import { StepEditor } from "./StepEditors.jsx";
import { useSettled } from "./useSettled.js";
import { Icon } from "./ui/Icon.jsx";
import { usePopover } from "./ui/MoreMenu.jsx";

const ADDABLE = ["input", "join", "transform", "llm", "union", "split", "output"];
const LEAVE_ASK = "有改动还没保存，离开会丢掉这些改动。要离开吗？";

/** While there are unsaved changes: closing or reloading the tab asks, and so does following a link to another page of the app. (The browser's back button cannot be stopped from here.) */
function useLeaveGuard(dirty) {
  useEffect(() => {
    if (!dirty) return undefined;
    const onUnload = (e) => {
      e.preventDefault();
      e.returnValue = "";
    };
    const onClick = (e) => {
      const link = e.target instanceof Element ? e.target.closest("a[href]") : null;
      const to = link?.getAttribute("href");
      if (to?.startsWith("#") && to !== window.location.hash && !window.confirm(LEAVE_ASK)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", onUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);
}

/** "加一步": the kinds of step, in a menu over the graph. */
function AddStep({ onAdd }) {
  const [open, setOpen, ref] = usePopover();
  return (
    <span className="menu-wrap" ref={ref}>
      <button className="secondary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="plus" size={14} /> 加一步</button>
      {open && (
        <div className="menu" role="menu">
          {ADDABLE.map((k) => <button key={k} role="menuitem" className="menu-item" onClick={() => { setOpen(false); onAdd(k); }}>{KIND_LABEL[k]}</button>)}
        </div>
      )}
    </span>
  );
}

/** The editing page: steps on the left, the graph in the middle, the selected step's editor on the right, rows / columns / statistics / log below. Nothing is saved until 保存. */
export function PipelineEditor({ detail, reload }) {
  const name = detail.name;
  const [draft, setDraft] = useState(detail.spec);
  const [selected, setSelected] = useState(detail.spec.steps[detail.spec.steps.length - 1]?.id ?? null);
  const [tab, setTab] = useState("rows");
  const [upto, setUpto] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [options, setOptions] = useState(null);
  const [asking, setAsking] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [stepsOpen, setStepsOpen] = useState(false);   // the list repeats the graph, so the graph gets the width until the person asks for the list
  const [size, setSize] = useState("normal");
  const [attempted, setAttempted] = useState(false);   // a step that is not set up is grey 待配置 until the person saves or runs
  const [ran, setRan] = useState(null);   // the run that just finished, as its record
  useEffect(() => {
    setDraft(detail.spec);
  }, [detail.version]);
  useEffect(() => {
    getDatasets().then(setDatasets, () => {});
    getPipelineOptions().then(setOptions, () => {});
  }, []);
  const dirty = !sameSpec(draft, detail.spec);
  useLeaveGuard(dirty);
  useEffect(() => {
    if (dirty) setRan(null);   // the numbers on the cards belong to the definition that ran
  }, [dirty]);
  const issues = allIssues(draft.steps);
  const todoCount = Object.values(issues).reduce((n, list) => n + list.length, 0);
  const step = draft.steps.find((s) => s.id === selected) ?? null;
  const summary = useSettled(() => pipelineSummary(name, draft), JSON.stringify(draft));
  const nodes = withBranchNodes(Object.fromEntries((summary.data?.nodes ?? []).map((n) => [n.id, n])), draft.steps);   // a step that reads a branch sees its columns
  const preview = useSettled(() => (step && tab !== "log" ? previewNode(name, draft, step.id, upto) : Promise.resolve(null)), JSON.stringify([draft, selected, upto, tab === "log"]));
  const hasOutput = draft.steps.some((s) => s.type === "output");
  const hasAi = draft.steps.some((s) => s.type === "llm");

  const save = async () => {
    setAttempted(true);
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
    setAttempted(true);
    setRunning(true);
    setError("");
    try {
      const made = await runPipeline(name);
      setRan(await getPipelineRun(name, made.id));   // stay on the graph: the run's rows are drawn on its cards
      reload();
    } catch (e) {
      setError(e.message);
    }
    setRunning(false);
  };
  const exportSpec = () => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" }));
    link.download = `${name}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };
  const add = (kind) => {
    const made = newStep(draft.steps, kind, selected, datasets.map((d) => d.name), options?.model ?? "");
    setDraft(addStep(draft, made));
    setSelected(made.id);
    setUpto(null);
  };
  const select = (id) => {
    setSelected(id);
    setUpto(null);
  };
  const lost = new Set(orphans(draft.steps));
  const reason = runBlockReason({ dirty, hasOutput, todo: todoCount, running });
  const results = runResults(ran);
  const titleOfStep = (id) => { const x = draft.steps.find((t) => t.id === id); return x ? stepTitle(x, draft.steps) : id; };
  const firstTodo = Object.entries(issues).flatMap(([id, list]) => list.map((l) => (l.includes("：") ? l : `${titleOfStep(id)}：${l}`)))[0];
  const problem = summary.status === "ready" && summary.data.error ? summary.data.error : summary.status === "error" ? summary.error : "";
  const quiet = Boolean(problem) && todoCount > 0 && !attempted;   // the engine objects to something the person has not set up yet: grey, not red
  return (
    <div className="pl">
      <PipelineBar detail={detail} view="edit"
        actions={(
          <>
            <span className={`saved${dirty ? " unsaved" : ""}`}>{dirty ? "有改动还没保存" : `已保存，第 ${detail.definition_version} 版`}</span>
            <button className="secondary" onClick={() => setAsking(true)} disabled={!options?.model_ready} title={options && !options.model_ready ? "本机服务没有模型凭据" : "用一句话让 AI 写几个步骤"}>AI</button>
            <button className="secondary" onClick={save} disabled={!dirty || saving}>{saving ? "保存中" : "保存"}</button>
            <span className="run-wrap" title={reason || "运行这条管道，结果写进输出的数据集"}>
              <button className="primary" onClick={() => (hasAi ? setConfirmRun(true) : run())} disabled={Boolean(reason)}><Icon name="play" size={14} /> {running ? "运行中" : "运行"}</button>
            </span>
          </>
        )}
        more={[{ label: "导出定义（JSON）", onClick: exportSpec }, ...(dirty ? [{ label: "放弃没保存的改动", danger: true, confirmText: "没保存的改动会丢掉，确定吗？", onClick: () => { setDraft(detail.spec); setAttempted(false); } }] : [])]} />
      {error && <p className="error pl-error">{friendlyError(error, draft.steps)} {error.includes("被改了") && <button className="plain" onClick={reload}>重新载入</button>}</p>}
      {problem && (quiet
        ? <p className="todo-note pl-error">待配置：{firstTodo}。配好后会自动检查。</p>
        : <p className="error pl-error">{friendlyError(problem, draft.steps)}{summary.status === "ready" ? "。它后面的步骤要等它改好才能算。" : ""}</p>)}
      {ran && (
        <p className={`run-bar${ran.status === "failed" ? " failed" : ""}`} role="status">
          <Icon name={ran.status === "failed" ? "alert" : "check-circle"} size={16} />
          <strong>第 {ran.id} 次运行{ran.status === "failed" ? "没成功" : "成功"}</strong>
          <span>用时 {durationText(ran.duration_ms)}</span>
          {ran.outputs.map((o) => <span key={o.dataset}>写出 <a href={hrefFor({ page: "dataset", name: o.dataset, tab: "fields" })}>{o.dataset}</a> 第 {o.version} 版，{numberText(o.rows)} 行</span>)}
          <a href={hrefFor({ page: "pipeline", name, view: "run", run: ran.id })}>查看运行记录</a>
          <button className="plain" onClick={() => setRan(null)} aria-label="关闭这条提示">关闭</button>
        </p>
      )}
      <div className={`pl-grid${stepsOpen ? "" : " no-steps"} size-${size}`}>
        <aside className="pl-steps" aria-label="步骤">
          <ol>
            {draft.steps.map((s) => (
              <li key={s.id}>
                <button className={`step-item${selected === s.id ? " on" : ""}`} onClick={() => select(s.id)} aria-current={selected === s.id ? "true" : undefined}>
                  <span className="step-kind">{kindLine(s)}{lost.has(s.id) && "，不会运行"}{issues[s.id] && <span className="card-todo">待配置</span>}</span>
                  <span className="step-title">{stepTitle(s, draft.steps)}</span>
                </button>
              </li>
            ))}
          </ol>
        </aside>
        <section className="pl-graph" aria-label="管道图">
          <div className="pl-tools">
            <button className="secondary" aria-pressed={stepsOpen} onClick={() => setStepsOpen(!stepsOpen)}>{stepsOpen ? "收起步骤清单" : "步骤清单"}</button>
            <AddStep onAdd={add} />
            {todoCount > 0 && <span className="muted small">{todoCount} 处待配置</span>}
          </div>
          <PipelineGraph steps={draft.steps} nodes={nodes} selected={selected} onSelect={select} issues={issues} results={results} />
        </section>
        <section className="pl-editor" aria-label="编辑这一步">
          {step && issues[step.id] && <p className="todo-note">待配置：{issues[step.id].join("；")}</p>}
          <StepEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} datasets={datasets} name={name} catalog={options?.operators ?? []} options={options} dirty={dirty} onPreviewTo={(i) => { setUpto(i); setTab("rows"); }} onRemoved={() => setSelected(null)} />
        </section>
        <section className="pl-bottom" aria-label="这一步的内容">
          <PipelinePanel tab={tab} setTab={setTab} preview={preview} upto={upto} onClearUpto={() => setUpto(null)} name={name} step={step} steps={draft.steps} node={step ? nodes[step.id] : null} todo={step ? issues[step.id] ?? [] : []} size={size} setSize={setSize} />
        </section>
      </div>
      {asking && (
        <AiDraftPanel name={name} spec={draft} selected={selected} onClose={() => setAsking(false)}
          onApply={(steps) => { setDraft(applyDraft(draft, steps)); setSelected(steps[0].id); setUpto(null); }} />
      )}
      {confirmRun && <RunDialog name={name} spec={draft} onClose={() => setConfirmRun(false)} onGo={run} />}
    </div>
  );
}
