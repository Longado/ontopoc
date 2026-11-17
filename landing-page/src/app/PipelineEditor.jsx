import React, { useEffect, useState } from "react";
import { getDatasets, getPipelineOptions, getPipelineRun, pipelineSummary, previewNode, runPipeline, savePipeline } from "./api.js";
import { AiDraftPanel, RunDialog } from "./AiDraftPanel.jsx";
import { t } from "./i18n/index.js";
import { PipelineBar } from "./PipelineBar.jsx";
import { PipelineGraph } from "./PipelineGraph.jsx";
import { KindChip, PIcon } from "./PipelineIcons.jsx";
import { PipelinePanel } from "./PipelinePanel.jsx";
import { KIND_LABEL, addStep, allIssues, applyDraft, cardFlags, durationText, friendlyError, kindLine, newStep, orphans, removeStep, rowsText, runBlockReason, runResults, sameSpec, stepTitle, withBranchNodes } from "./pipelineModel.js";
import { CHANGED_BY_OTHER } from "./pipelineServerText.js";
import { hrefFor } from "./routeModel.js";
import { StepEditor } from "./StepEditors.jsx";
import { useSettled } from "./useSettled.js";
import { usePopover } from "./ui/MoreMenu.jsx";

const ADDABLE_GROUPS = [["input", ["input"]], ["transform", ["join", "transform", "union", "split"]], ["ai", ["llm"]], ["output", ["output"]]];
const TOAST_MS = 5000;

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
      if (to?.startsWith("#") && to !== window.location.hash && !window.confirm(t("pipeline.editor.leaveAsk"))) {
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

/** While the editor is open the app's navigation folds to its icons (CSS: body.pl-editing), so that the canvas gets the width. */
function useFullBleed() {
  useEffect(() => {
    document.body.classList.add("pl-editing");
    return () => document.body.classList.remove("pl-editing");
  }, []);
}

/** "Add step": the kinds of step, grouped, in a menu over the canvas. */
function AddStep({ onAdd }) {
  const [open, setOpen, ref] = usePopover();
  return (
    <span className="menu-wrap" ref={ref}>
      <button type="button" className="pl-tool primary-soft" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}><PIcon name="plus" /> {t("pipeline.editor.addStep")}</button>
      {open && (
        <div className="menu pl-add-menu" role="menu">
          {ADDABLE_GROUPS.map(([group, kinds]) => (
            <div key={group} className="pl-add-group">
              <p className="menu-label">{t(`pipeline.editor.group.${group}`)}</p>
              {kinds.map((k) => (
                <button key={k} type="button" role="menuitem" className="menu-item" onClick={() => { setOpen(false); onAdd(k); }}><KindChip step={{ type: k }} /> {KIND_LABEL[k]}</button>
              ))}
            </div>
          ))}
        </div>
      )}
    </span>
  );
}

/** The result of a run, as a toast at the bottom of the page: one sentence, a link to the record, a close button. A success goes away by itself; a failure stays until closed. */
function RunToast({ name, run, onClose }) {
  const failed = run.status === "failed";
  useEffect(() => {
    if (failed) return undefined;
    const timer = setTimeout(onClose, TOAST_MS);
    return () => clearTimeout(timer);
  }, [run.id, failed]);
  return (
    <div className={`pl-toast${failed ? " failed" : ""}`} role={failed ? "alert" : "status"}>
      <PIcon name={failed ? "alert" : "success"} size={18} />
      <div className="pl-toast-body">
        <strong>{t(failed ? "pipeline.editor.toast.failed" : "pipeline.editor.toast.ok", { id: run.id })}</strong>
        <span>{t("pipeline.editor.toast.took", { time: durationText(run.duration_ms) })}</span>
        {run.outputs.map((o) => <span key={o.dataset}>{t("pipeline.editor.toast.wrote", { rows: rowsText(o.rows), version: o.version })} <a href={hrefFor({ page: "dataset", name: o.dataset, tab: "fields" })}>{o.dataset}</a></span>)}
      </div>
      <a className="pl-toast-link" href={hrefFor({ page: "pipeline", name, view: "run", run: run.id })}>{t("pipeline.editor.toast.view")}</a>
      <button type="button" className="icon-btn" onClick={onClose} aria-label={t("pipeline.editor.toast.close")}><PIcon name="close" /></button>
    </div>
  );
}

/** The editing page: the graph fills the page, the steps can open as a list on the left, the selected step's editor sits on the right, and rows / columns / statistics / log in a drawer below.
 * Nothing is saved until Save. */
export function PipelineEditor({ detail, reload }) {
  useFullBleed();
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
  const [attempted, setAttempted] = useState(false);   // a step that is not set up is grey "Unconfigured" until the person saves or runs
  const [ran, setRan] = useState(null);   // the run that just finished, as its record: the numbers on the cards
  const [toast, setToast] = useState(null);   // the same run, as the message at the bottom
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
      const record = await getPipelineRun(name, made.id);   // stay on the graph: the run's rows are drawn on its cards
      setRan(record);
      setToast(record);
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
  const titleOfStep = (id) => { const x = draft.steps.find((s) => s.id === id); return x ? stepTitle(x, draft.steps) : id; };
  const firstTodo = Object.entries(issues).flatMap(([id, list]) => list.map((l) => (/[:\uff1a]/.test(l) || /^[(\uff08]/.test(titleOfStep(id)) ? l : t("pipeline.editor.todoLine", { title: titleOfStep(id), issue: l }))))[0];
  const problem = summary.status === "ready" && summary.data.error ? summary.data.error : summary.status === "error" ? summary.error : "";
  const quiet = Boolean(problem) && todoCount > 0 && !attempted;   // the engine objects to something the person has not set up yet: grey, not red
  const flags = step ? cardFlags(nodes[step.id]).filter((f) => f.level !== "note") : [];
  const readers = step ? removeStep(draft, step.id).blocked : [];
  return (
    <div className="pl pl-edit">
      <PipelineBar detail={detail} view="edit"
        meta={<span className={`pl-saved${dirty ? " unsaved" : ""}`}><i aria-hidden="true" />{dirty ? t("pipeline.editor.unsaved") : t("pipeline.editor.saved", { version: detail.definition_version })}</span>}
        actions={(
          <>
            <button type="button" className="secondary pl-btn" onClick={() => setAsking(true)} disabled={!options?.model_ready} title={options && !options.model_ready ? t("pipeline.editor.aiNoModel") : t("pipeline.editor.aiHint")}><PIcon name="sparkle" /> {t("pipeline.editor.ai")}</button>
            <button type="button" className="secondary pl-btn" onClick={save} disabled={!dirty || saving}>{saving ? t("pipeline.editor.saving") : t("pipeline.editor.save")}</button>
            <span className="run-wrap" title={reason || t("pipeline.editor.runHint")}>
              <button type="button" className="primary pl-btn" onClick={() => (hasAi ? setConfirmRun(true) : run())} disabled={Boolean(reason)}><PIcon name="play" size={14} /> {running ? t("pipeline.editor.running") : t("pipeline.editor.run")}</button>
            </span>
          </>
        )}
        more={[{ label: t("pipeline.editor.export"), onClick: exportSpec }, ...(dirty ? [{ label: t("pipeline.editor.discard"), danger: true, confirmText: t("pipeline.editor.discardAsk"), onClick: () => { setDraft(detail.spec); setAttempted(false); } }] : [])]} />
      <div className={`pl-work${stepsOpen ? " with-steps" : ""}${step ? " with-config" : ""} size-${size}`}>
        <aside className="pl-steps" aria-label={t("pipeline.editor.stepsAria")}>
          <div className="pl-side-head"><h2>{t("pipeline.editor.steps")}</h2><span className="pl-count">{draft.steps.length}</span></div>
          <ol>
            {draft.steps.map((s) => (
              <li key={s.id}>
                <button type="button" className={`step-item${selected === s.id ? " on" : ""}`} onClick={() => select(s.id)} aria-current={selected === s.id ? "true" : undefined}>
                  <KindChip step={s} />
                  <span className="step-text">
                    <span className="step-title">{stepTitle(s, draft.steps)}</span>
                    <span className="step-kind">{kindLine(s)}{lost.has(s.id) && ` · ${t("pipeline.graph.wontRun")}`}</span>
                  </span>
                  {issues[s.id] && <span className="pl-badge neutral">{t("pipeline.graph.unconfigured")}</span>}
                </button>
              </li>
            ))}
          </ol>
        </aside>
        <div className="pl-center">
          <section className="pl-graph" aria-label={t("pipeline.editor.graphAria")}>
            <div className="pl-tools">
              <button type="button" className="pl-tool" aria-pressed={stepsOpen} onClick={() => setStepsOpen(!stepsOpen)}><PIcon name="steps" /> {t("pipeline.editor.steps")}</button>
              <AddStep onAdd={add} />
              {todoCount > 0 && <span className="pl-tool-note">{t("pipeline.editor.todoCount", { count: todoCount })}</span>}
              {!step && draft.steps.length > 0 && <span className="pl-tool-note">{t("pipeline.panel.pick")}</span>}
            </div>
            <div className="pl-notices">
              {error && <p className="pl-note bad" role="alert"><PIcon name="alert" size={14} /><span>{friendlyError(error, draft.steps)} {error.includes(CHANGED_BY_OTHER) && <button type="button" className="plain" onClick={reload}>{t("pipeline.editor.reload")}</button>}</span></p>}
              {problem && (quiet
                ? <p className="pl-note neutral"><PIcon name="info" size={14} /><span><strong>{t("pipeline.graph.unconfigured")}.</strong> {t("pipeline.editor.quiet", { first: firstTodo })}</span></p>
                : <p className="pl-note bad" role="alert"><PIcon name="alert" size={14} /><span>{friendlyError(problem, draft.steps)}{summary.status === "ready" ? ` ${t("pipeline.editor.laterBlocked")}` : ""}</span></p>)}
            </div>
            <PipelineGraph steps={draft.steps} nodes={nodes} selected={selected} onSelect={select} issues={issues} results={results} />
          </section>
          {step && (
            <section className="pl-bottom" aria-label={t("pipeline.editor.bottomAria")}>
              <PipelinePanel tab={tab} setTab={setTab} preview={preview} upto={upto} onClearUpto={() => setUpto(null)} name={name} step={step} steps={draft.steps} node={nodes[step.id]} todo={issues[step.id] ?? []} size={size} setSize={setSize} />
            </section>
          )}
        </div>
        {step && (
          <aside className="pl-config" aria-label={t("pipeline.editor.configAria")}>
            <header className="pl-config-head">
              <KindChip step={step} size={28} />
              <div className="pl-config-title">
                <h2 title={stepTitle(step, draft.steps)}>{stepTitle(step, draft.steps)}</h2>
                <p>{step.type === "join" ? kindLine(step) : KIND_LABEL[step.type]}</p>
              </div>
              <button type="button" className="icon-btn" onClick={() => setSelected(null)} aria-label={t("pipeline.editor.closePanel")} title={t("pipeline.editor.closePanel")}><PIcon name="close" /></button>
            </header>
            <div className="pl-config-body">
              {issues[step.id] && <p className="pl-note neutral"><PIcon name="info" size={14} /><span><strong>{t("pipeline.graph.unconfigured")}.</strong> {issues[step.id].join("; ")}</span></p>}
              {flags.map((f) => <p key={f.text} className={`pl-note ${f.level === "bad" ? "bad" : "warn"}`}><PIcon name="alert" size={14} /><span>{f.text}</span></p>)}
              <StepEditor step={step} draft={draft} setDraft={setDraft} nodes={nodes} datasets={datasets} name={name} catalog={options?.operators ?? []} options={options} dirty={dirty} onPreviewTo={(i) => { setUpto(i); setTab("rows"); }} />
            </div>
            <footer className="pl-config-foot">
              <span className={`pl-foot-note${dirty ? " unsaved" : ""}`}><i aria-hidden="true" />{dirty ? t("pipeline.editor.footUnsaved") : t("pipeline.editor.footSaved")}</span>
              <button type="button" className="secondary danger-text" disabled={readers.length > 0} title={readers.length ? t("steps.edit.readers.blocked", { names: readers.join(", ") }) : ""} onClick={() => { setDraft(removeStep(draft, step.id).spec); setSelected(null); }}><PIcon name="trash" /> {t("steps.edit.removeStep")}</button>
            </footer>
          </aside>
        )}
      </div>
      {toast && <RunToast name={name} run={toast} onClose={() => setToast(null)} />}
      {asking && (
        <AiDraftPanel name={name} spec={draft} selected={selected} onClose={() => setAsking(false)}
          onApply={(steps) => { setDraft(applyDraft(draft, steps)); setSelected(steps[0].id); setUpto(null); }} />
      )}
      {confirmRun && <RunDialog name={name} spec={draft} onClose={() => setConfirmRun(false)} onGo={run} />}
    </div>
  );
}
