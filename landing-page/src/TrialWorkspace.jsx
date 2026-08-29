import { useState } from "react";
import { AlertCircle, ArrowRight, Bot, CheckCircle2, CircleDashed, RefreshCw, ShieldCheck } from "lucide-react";

import { confirmAgentModelingSession, createRecordedAgentModelingSession } from "./agentModelingSession.js";
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
    agentTitle: "Agent 已生成可审阅的本体候选草案",
    agentIntro: "已知模板识别与候选编译来自已录制产物；确认只在本次浏览器会话内有效。",
    agentSteps: ["接收合成文档", "识别已知模板", "编译候选模型", "等待人工确认"],
    candidateSet: "闭合候选集",
    candidateKinds: ["实体类型", "关系类型", "候选规则"],
    confirm: "确认候选并进入本体图",
    sessionOnly: "SESSION ONLY / NOT SAVED",
    confirmed: "本次会话已确认 / 未保存",
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
    agentTitle: "The Agent produced an inspectable ontology draft",
    agentIntro: "Known-template recognition and candidate compilation use a recorded artifact. Confirmation lasts for this browser session only.",
    agentSteps: ["Receive synthetic document", "Recognize known template", "Compile candidates", "Await human confirmation"],
    candidateSet: "CLOSED CANDIDATE SET",
    candidateKinds: ["ENTITY TYPES", "RELATION TYPES", "CANDIDATE RULES"],
    confirm: "CONFIRM CANDIDATES AND OPEN GRAPH",
    sessionOnly: "SESSION ONLY / NOT SAVED",
    confirmed: "CONFIRMED FOR THIS SESSION / NOT SAVED",
  },
};

export function TrialWorkspace({ language }) {
  const [status, setStatus] = useState("idle");
  const [workspace, setWorkspace] = useState(null);
  const [agentSession, setAgentSession] = useState(null);
  const [confirmationReceipt, setConfirmationReceipt] = useState(null);
  const [error, setError] = useState("");
  const [activeStage, setActiveStage] = useState(0);
  const t = copy[language];

  const runAgentDemo = async () => {
    setStatus("loading");
    setError("");
    try {
      const response = await fetch("/artifacts/supply-chain-recognition.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const artifact = await response.json();
      const adapted = adaptTrialArtifact(artifact);
      const session = createRecordedAgentModelingSession(artifact, adapted);
      setWorkspace(adapted);
      setAgentSession(session);
      setConfirmationReceipt(null);
      setActiveStage(0);
      setStatus("agent_review");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      setStatus("error");
    }
  };

  if (status === "idle") {
    return <DocumentModeler language={language} runAgentDemo={runAgentDemo} />;
  }

  if (status === "loading") {
    return <div className="workspace-state" role="status"><RefreshCw className="workspace-spinner" size={26} /><strong>{t.loading}</strong><span>{t.fixed}</span></div>;
  }

  if (status === "error") {
    return <div className="workspace-state workspace-error" role="alert"><AlertCircle size={30} /><strong>{t.error}</strong><span>{error}</span><button type="button" onClick={runAgentDemo}>{t.retry}</button></div>;
  }

  if (status === "agent_review") {
    const confirmCandidates = () => {
      const receipt = confirmAgentModelingSession(agentSession, {
        specHash: agentSession.specHash,
        candidateIds: agentSession.candidates.stableIds,
      });
      setConfirmationReceipt(receipt);
      setStatus("succeeded");
    };
    return <AgentReviewPanel session={agentSession} workspace={workspace} t={t} onConfirm={confirmCandidates} />;
  }

  const stage = workspace.stages[activeStage];
  const panels = [RecognitionPanel, DecisionPackPanel, OntologySpecPanel, ValidationPanel];
  const ActivePanel = panels[activeStage];

  return <div className="artifact-workspace"><div className="workspace-stage-tabs" role="tablist" aria-label="Demo compiler stages">{workspace.stages.map((item, index) => <button id={`workspace-tab-${index}`} key={item.id} type="button" role="tab" aria-selected={activeStage === index} aria-controls={`workspace-panel-${index}`} tabIndex={activeStage === index ? 0 : -1} className={activeStage === index ? "is-active" : ""} onClick={() => setActiveStage(index)} onKeyDown={(event) => { if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return; event.preventDefault(); const next = moveTrialStage(index, event.key, workspace.stages.length); setActiveStage(next); event.currentTarget.parentElement?.querySelector(`#workspace-tab-${next}`)?.focus(); }}><span>0{index + 1}</span><strong>{item.label}</strong><small>{item.status}</small></button>)}</div><section className="workspace-stage-panel" id={`workspace-panel-${activeStage}`} role="tabpanel" aria-labelledby={`workspace-tab-${activeStage}`}><div className="workspace-stage-heading"><div><span>{t.fixed}</span><h2>{stage.label}</h2></div><div className="workspace-heading-status"><span className="agent-session-confirmed"><ShieldCheck size={13} />{t.confirmed}</span><Status value={stage.status} /></div></div><ActivePanel data={stage.data} t={t} language={language} confirmationReceipt={confirmationReceipt} /></section></div>;
}

function AgentReviewPanel({ session, workspace, t, onConfirm }) {
  const ontology = workspace.stages[2].data.ontologyWorkspace;
  const candidateGroups = [
    ontology.entityNodes.map(({ data }) => data.label),
    ontology.relationEdges.map(({ data }) => data.predicate),
    ontology.ruleNodes.map(({ data }) => data.semanticKey),
  ];
  const counts = session.candidates.counts;

  return <section className="agent-review" aria-labelledby="agent-review-title">
    <header className="agent-review-header"><div><span>RECORDED KNOWN-TEMPLATE AGENT</span><h2 id="agent-review-title">{t.agentTitle}</h2><p>{t.agentIntro}</p></div><Bot size={36} strokeWidth={1.4} /></header>
    <div className="agent-review-layout">
      <div className="agent-review-main">
        <div className="agent-stage-list">{session.stages.map((stage, index) => <div key={stage.id} className={stage.status === "pending" ? "is-pending" : "is-complete"}>{stage.status === "pending" ? <CircleDashed size={18} /> : <CheckCircle2 size={18} />}<span>0{index + 1}</span><strong>{t.agentSteps[index]}</strong><small>{stage.status}</small></div>)}</div>
        <div className="agent-candidate-groups">{candidateGroups.map((items, index) => <section key={t.candidateKinds[index]}><header><span>{t.candidateKinds[index]}</span><strong>{items.length}</strong></header>{items.map((item) => <code key={item}>{item}</code>)}</section>)}</div>
      </div>
      <aside className="agent-review-aside">
        <span>{t.candidateSet}</span>
        <div className="agent-counts"><strong>{counts.entities}</strong><small>{t.candidateKinds[0]}</small><strong>{counts.relations}</strong><small>{t.candidateKinds[1]}</small><strong>{counts.rules}</strong><small>{t.candidateKinds[2]}</small></div>
        <Hash label="ONTOLOGY SPEC HASH" value={session.specHash} />
        <div className="agent-boundaries"><span>{t.sessionOnly}</span>{Object.entries(session.boundaries).map(([key, value]) => <div key={key}><code>{key}</code><strong>{String(value)}</strong></div>)}</div>
        <button type="button" className="agent-confirm" onClick={onConfirm}><ShieldCheck size={17} />{t.confirm}<ArrowRight size={17} /></button>
      </aside>
    </div>
  </section>;
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
