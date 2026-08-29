import { useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";

import { DocumentModeler } from "./DocumentModeler.jsx";
import { OntologyWorkspace } from "./OntologyWorkspace.jsx";
import { adaptTrialArtifact, moveTrialStage } from "./trialWorkspaceModel.js";

const copy = {
  zh: {
    eyebrow: "RECORDED / DETERMINISTIC DEMO",
    title: "把一段合成业务材料编译成可检查的本体草案。",
    intro: "运行已录制的确定性产物，查看 Recognition、DecisionPack、OntologySpec 与尚未执行的 Validation 边界。",
    run: "运行演示",
    loading: "正在加载完整编译产物…",
    error: "演示产物加载失败",
    retry: "重新加载",
    fixed: "固定演示产物 / 非实时调用",
    source: "合成源文本",
    profile: "匹配场景",
    owner: "决策负责人",
    trigger: "触发条件",
    provider: "Provider / Model",
    decision: "业务判断",
    hash: "后端内容哈希",
    packHash: "绑定的 DecisionPack 哈希",
    bindings: "输入绑定",
    sources: "来源目录",
    outcomes: "知识匹配结果",
    governance: "治理状态",
    compilation: "complete 仅表示编译完成",
    closure: "引用闭包",
    checked: "已检查引用",
    counts: ["实体", "关系", "属性", "规则"],
    issues: "需业务复核的编译项",
    validationTitle: "Validation contract 已定义，evaluator 未执行。",
    noReceipt: "无 Validation receipt",
    boundary: "交付边界",
    contractOnly: "CONTRACT ONLY / NOT IMPLEMENTED",
  },
  en: {
    eyebrow: "RECORDED / DETERMINISTIC DEMO",
    title: "Compile synthetic business material into an inspectable ontology draft.",
    intro: "Load one recorded deterministic artifact and inspect Recognition, DecisionPack, OntologySpec, and the unexecuted Validation boundary.",
    run: "RUN DEMO",
    loading: "Loading the complete compiler artifact…",
    error: "The demo artifact could not be loaded",
    retry: "RELOAD",
    fixed: "RECORDED ARTIFACT / NO LIVE MODEL CALL",
    source: "SYNTHETIC SOURCE TEXT",
    profile: "MATCHED PROFILE",
    owner: "DECISION OWNER",
    trigger: "TRIGGER",
    provider: "PROVIDER / MODEL",
    decision: "BUSINESS DECISION",
    hash: "BACKEND CONTENT HASH",
    packHash: "BOUND DECISIONPACK HASH",
    bindings: "INPUT BINDINGS",
    sources: "SOURCE CATALOG",
    outcomes: "KNOWLEDGE OUTCOMES",
    governance: "GOVERNANCE",
    compilation: "complete means compilation completed only",
    closure: "REFERENCE CLOSURE",
    checked: "CHECKED REFERENCES",
    counts: ["ENTITIES", "RELATIONS", "PROPERTIES", "RULES"],
    issues: "COMPILATION ITEMS REQUIRING REVIEW",
    validationTitle: "The Validation contract is defined; its evaluator did not run.",
    noReceipt: "NO VALIDATION RECEIPT",
    boundary: "DELIVERY BOUNDARY",
    contractOnly: "CONTRACT ONLY / NOT IMPLEMENTED",
  },
};

export function TrialWorkspace({ language }) {
  const [status, setStatus] = useState("idle");
  const [workspace, setWorkspace] = useState(null);
  const [error, setError] = useState("");
  const [activeStage, setActiveStage] = useState(0);
  const t = copy[language];

  const runDemo = async () => {
    setStatus("loading");
    setError("");
    try {
      const response = await fetch("/artifacts/supply-chain-recognition.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const adapted = adaptTrialArtifact(await response.json());
      setWorkspace(adapted);
      setActiveStage(0);
      setStatus("succeeded");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus("error");
    }
  };

  if (status === "idle") {
    return <DocumentModeler language={language} runDemo={runDemo} />;
  }

  if (status === "loading") {
    return <div className="workspace-state" role="status"><RefreshCw className="workspace-spinner" size={26} /><strong>{t.loading}</strong><span>{t.fixed}</span></div>;
  }

  if (status === "error") {
    return <div className="workspace-state workspace-error" role="alert"><AlertCircle size={30} /><strong>{t.error}</strong><span>{error}</span><button type="button" onClick={runDemo}>{t.retry}</button></div>;
  }

  const stage = workspace.stages[activeStage];
  const panels = [RecognitionPanel, DecisionPackPanel, OntologySpecPanel, ValidationPanel];
  const ActivePanel = panels[activeStage];

  return <div className="artifact-workspace"><div className="workspace-stage-tabs" role="tablist" aria-label="Demo compiler stages">{workspace.stages.map((item, index) => <button id={`workspace-tab-${index}`} key={item.id} type="button" role="tab" aria-selected={activeStage === index} aria-controls={`workspace-panel-${index}`} tabIndex={activeStage === index ? 0 : -1} className={activeStage === index ? "is-active" : ""} onClick={() => setActiveStage(index)} onKeyDown={(event) => { if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return; event.preventDefault(); const next = moveTrialStage(index, event.key, workspace.stages.length); setActiveStage(next); event.currentTarget.parentElement?.querySelector(`#workspace-tab-${next}`)?.focus(); }}><span>0{index + 1}</span><strong>{item.label}</strong><small>{item.status}</small></button>)}</div><section className="workspace-stage-panel" id={`workspace-panel-${activeStage}`} role="tabpanel" aria-labelledby={`workspace-tab-${activeStage}`}><div className="workspace-stage-heading"><div><span>{t.fixed}</span><h2>{stage.label}</h2></div><Status value={stage.status} /></div><ActivePanel data={stage.data} t={t} language={language} /></section></div>;
}

function Status({ value }) {
  const Icon = value === "not_implemented" ? AlertCircle : CheckCircle2;
  return <span className={`workspace-status status-${value.replaceAll("_", "-")}`}><Icon size={13} />{value}</span>;
}

function Meta({ label, children, mono = false }) {
  return <div className={`workspace-meta ${mono ? "is-mono" : ""}`}><span>{label}</span><strong>{children}</strong></div>;
}

function Hash({ label, value }) {
  return <div className="workspace-hash"><span>{label}</span><code>{value}</code></div>;
}

function RecognitionPanel({ data, t }) {
  return <div className="workspace-detail-layout"><div className="workspace-detail-main"><div className="workspace-source"><span>{t.source}</span><p>{data.sourceText}</p></div></div><aside className="workspace-detail-aside"><Meta label={t.profile} mono>{data.profileKey}</Meta><Meta label={t.owner}>{data.owner}</Meta><Meta label={t.trigger}>{data.trigger}</Meta><Meta label={t.provider} mono>{data.provider}<br />{data.model}</Meta></aside></div>;
}

function DecisionPackPanel({ data, t }) {
  return <div className="workspace-detail-layout"><div className="workspace-detail-main"><Meta label={t.decision}>{data.businessDecision}</Meta><div className="workspace-main-lists"><ListBlock title={t.bindings} rows={data.inputBindings.map((item) => [item.role_key, item.label])} /><ListBlock title={t.outcomes} rows={data.outcomes.map((item) => [item.match_status, item.unit_id])} /></div></div><aside className="workspace-detail-aside"><Hash label={t.hash} value={data.contentHash} /><Meta label={t.governance} mono>{data.governanceStatuses.join(" / ")}</Meta><ListBlock title={t.sources} rows={data.sources.map((item) => [item.source_kind, item.title])} /></aside></div>;
}

function ListBlock({ title, rows }) {
  return <div className="workspace-list"><span>{title}</span>{rows.map(([meta, value]) => <div key={`${meta}-${value}`}><small>{meta}</small><strong>{value}</strong></div>)}</div>;
}

function OntologySpecPanel({ data, t, language }) {
  return <OntologyWorkspace data={data} t={t} language={language} />;
}

function ValidationPanel({ data, t }) {
  return <div className="workspace-validation"><div className="validation-empty"><span>{t.contractOnly}</span><h3>{t.validationTitle}</h3><p>{t.noReceipt} · receipt = null</p></div><div className="validation-boundaries"><span>{t.boundary}</span>{Object.entries(data.boundaries).map(([key, value]) => <div key={key}><code>{key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)}</code><strong>{String(value)}</strong></div>)}<div><code>evaluator_executed</code><strong>{String(data.evaluatorExecuted)}</strong></div></div></div>;
}
