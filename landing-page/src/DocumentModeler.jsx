import { useMemo, useState } from "react";
import { Background, BackgroundVariant, MarkerType, ReactFlow } from "@xyflow/react";
import { ArrowRight, Braces, Check, GitBranch, Network, ScrollText } from "lucide-react";

import {
  buildPhase1DecisionPack,
  DOCUMENT_MODELING_PRESETS,
  resolveDocumentModelingRequest,
} from "./documentModelingDemoModel.js";

const copy = {
  zh: {
    title: "从质量事件开始追溯",
    intro: "固定案例演示：材料只读。查看同一质量快照的对象范围，再核对核心关系。",
    scenario: "01 / 选择质量事件或演示场景",
    document: "02 / 固定质量事件材料（只读）",
    generate: "查看追溯证据链",
    evidence: "选中证据",
    empty: "选择质量事件后，查看跨来源记录、追溯链和当前数据缺口。",
    unsupported: "当前文本不受支持",
    unsupportedBody: "文档已被编辑或不属于所选预设。请恢复原预设文本后重新生成。",
    boundary: "能力边界",
    compiledReady: "COMPILED ARTIFACT ROUTE AVAILABLE",
    entity: "对象候选",
    relation: "关系候选",
    decision: "待支持的业务决策",
    owner: "决策负责人",
    trigger: "触发条件",
    event: "质量事件",
    eventStatus: "当前状态",
    detectedAt: "发现时间",
    investigation: "当前追溯问题",
    sourceRecords: "跨来源记录",
    available: "已取得",
    missing: "缺失",
    sourceRecord: "来源记录",
    controlScope: "建议临时控制范围",
    controlScopeBoundary: "SYNTHETIC DEMO · 未执行任何控制",
    confirmedImpact: "同批次关联",
    possibleImpact: "可能影响",
    excludedImpact: "已排除",
    notEvaluableImpact: "无法评估",
    basis: "判断依据",
    includeControl: "纳入临时控制",
    excludeControl: "排除",
    needsEvidence: "待补证",
    reviewProgress: "范围确认进度",
    scopePending: "尚有对象待确认",
    scopeComplete: "本次范围已完成",
    scopeSessionBoundary: "会话内选择 · 未执行业务控制",
    objectTypes: {
      inventory: "库存",
      work_in_process: "在制",
      pending_shipment: "待发运",
      in_transit: "在途",
      customer_side: "客户侧",
    },
    investigationResults: "调查范围建议",
    priority: "优先调查",
    weakened: "正常对照削弱",
    evidenceRefs: "支持证据",
    counterevidence: "反证",
    dataGaps: "数据缺口",
    investigationLoading: "正在读取调查结果…",
    investigationLoadError: "调查结果不可用，请检查演示数据。",
    rootCauseBoundary: "仅用于确定调查顺序，不确认根因",
    keepCandidate: "保留候选",
    excludeCandidate: "排除候选",
    restoreCandidate: "恢复候选",
    selectedCount: "已保留",
    reviewNote: "FDE 修正说明",
    reviewPlaceholder: "说明需要补证、排除或保留的原因",
    confirmPack: "确认候选 DecisionPack",
    candidatePack: "候选 DecisionPack",
    packReady: "已生成，仅当前会话有效",
    packSchema: "decision_pack.phase1_candidate.v1",
    sessionOnly: "SESSION ONLY · 不创建业务动作",
  },
  en: {
    title: "Start from a quality event",
    intro: "Read-only fixed case. Inspect scope objects from the same quality snapshot, then review the core relationships.",
    scenario: "01 / SELECT QUALITY EVENT OR DEMO SCENARIO",
    document: "02 / FIXED CASE MATERIAL (READ ONLY)",
    generate: "VIEW TRACE EVIDENCE",
    evidence: "SELECTED EVIDENCE",
    empty: "Select a quality event to inspect cross-source records, its trace, and current data gaps.",
    unsupported: "UNSUPPORTED DOCUMENT TEXT",
    unsupportedBody: "The document was edited or does not match the selected preset. Restore the preset text and generate again.",
    boundary: "CAPABILITY BOUNDARY",
    compiledReady: "COMPILED ARTIFACT ROUTE AVAILABLE",
    entity: "OBJECT CANDIDATE",
    relation: "RELATION CANDIDATE",
    decision: "BUSINESS DECISION",
    owner: "DECISION OWNER",
    trigger: "TRIGGER",
    event: "QUALITY EVENT",
    eventStatus: "CURRENT STATUS",
    detectedAt: "DETECTED AT",
    investigation: "CURRENT TRACE QUESTION",
    sourceRecords: "CROSS-SOURCE RECORDS",
    available: "AVAILABLE",
    missing: "MISSING",
    sourceRecord: "SOURCE RECORD",
    controlScope: "SUGGESTED TEMPORARY CONTROL SCOPE",
    controlScopeBoundary: "SYNTHETIC DEMO · NO CONTROL EXECUTED",
    confirmedImpact: "SAME-BATCH ASSOCIATION",
    possibleImpact: "POSSIBLE IMPACT",
    excludedImpact: "EXCLUDED",
    notEvaluableImpact: "NOT EVALUABLE",
    basis: "BASIS",
    includeControl: "INCLUDE IN CONTROL",
    excludeControl: "EXCLUDE",
    needsEvidence: "NEEDS EVIDENCE",
    reviewProgress: "SCOPE REVIEW PROGRESS",
    scopePending: "OBJECTS AWAITING REVIEW",
    scopeComplete: "SCOPE REVIEW COMPLETE",
    scopeSessionBoundary: "SESSION-ONLY CHOICE · NO BUSINESS CONTROL EXECUTED",
    objectTypes: {
      inventory: "INVENTORY",
      work_in_process: "WORK IN PROCESS",
      pending_shipment: "PENDING SHIPMENT",
      in_transit: "IN TRANSIT",
      customer_side: "CUSTOMER SIDE",
    },
    investigationResults: "INVESTIGATION SCOPE",
    priority: "PRIORITY",
    weakened: "WEAKENED BY NORMAL CONTROL",
    evidenceRefs: "SUPPORTING EVIDENCE",
    counterevidence: "COUNTEREVIDENCE",
    dataGaps: "DATA GAPS",
    investigationLoading: "Loading investigation result…",
    investigationLoadError: "Investigation result is unavailable. Check the demo data.",
    rootCauseBoundary: "Prioritizes investigation only; does not confirm root cause",
    keepCandidate: "KEEP CANDIDATE",
    excludeCandidate: "EXCLUDE CANDIDATE",
    restoreCandidate: "RESTORE CANDIDATE",
    selectedCount: "KEPT",
    reviewNote: "FDE REVIEW NOTE",
    reviewPlaceholder: "Explain what needs evidence, exclusion, or retention",
    confirmPack: "CONFIRM CANDIDATE DECISIONPACK",
    candidatePack: "CANDIDATE DECISIONPACK",
    packReady: "CREATED FOR THIS SESSION ONLY",
    packSchema: "decision_pack.phase1_candidate.v1",
    sessionOnly: "SESSION ONLY · NO BUSINESS ACTION CREATED",
  },
};

const positions = [
  { x: 24, y: 34 },
  { x: 268, y: 24 },
  { x: 268, y: 154 },
  { x: 510, y: 88 },
];

function projectCandidateGraph(preset, includedCandidates) {
  const includedEntityIds = new Set(
    preset.entityTypes
      .filter(({ id }) => includedCandidates.has(candidateKey("entity", id)))
      .map(({ id }) => id),
  );
  return {
    nodes: preset.entityTypes
      .filter(({ id }) => includedEntityIds.has(id))
      .map((entity, index) => ({
        id: entity.id,
        position: positions[index],
        data: { label: entity.label },
      })),
    edges: preset.relationTypes
      .filter(({ id, source, target }) => (
        includedCandidates.has(candidateKey("relation", id))
        && includedEntityIds.has(source)
        && includedEntityIds.has(target)
      ))
      .map((relation) => ({
        id: relation.id,
        source: relation.source,
        target: relation.target,
        label: relation.label,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#1757dc" },
        style: { stroke: "#1757dc", strokeWidth: 1.6 },
        labelStyle: { fill: "#0a0b0d", fontSize: 8, fontWeight: 800 },
        labelBgStyle: { fill: "#f8f7f1", fillOpacity: 0.96 },
      })),
  };
}

function candidateKey(kind, id) {
  return `${kind}:${id}`;
}

export function DocumentModeler({ language, runAgentDemo }) {
  const t = copy[language] ?? copy.en;
  const [scenarioId, setScenarioId] = useState(DOCUMENT_MODELING_PRESETS[0].id);
  const [documentText, setDocumentText] = useState(DOCUMENT_MODELING_PRESETS[0].documentText);
  const [result, setResult] = useState(null);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [includedCandidates, setIncludedCandidates] = useState(new Set());
  const [reviewNote, setReviewNote] = useState("");
  const [decisionPack, setDecisionPack] = useState(null);
  const [investigation, setInvestigation] = useState(null);
  const [investigationStatus, setInvestigationStatus] = useState("idle");
  const [controlDecisions, setControlDecisions] = useState({});
  const [showMaterial, setShowMaterial] = useState(true);

  const graph = useMemo(
    () => result?.status === "resolved" ? projectCandidateGraph(result.preset, includedCandidates) : { nodes: [], edges: [] },
    [includedCandidates, result],
  );

  const selectScenario = (preset) => {
    setShowMaterial(true);
    setScenarioId(preset.id);
    setDocumentText(preset.documentText);
    setResult(null);
    setSelectedEvidence(null);
    setIncludedCandidates(new Set());
    setReviewNote("");
    setDecisionPack(null);
    setInvestigation(null);
    setInvestigationStatus("idle");
    setControlDecisions({});
  };

  const generate = async () => {
    const nextResult = resolveDocumentModelingRequest(scenarioId, documentText);
    if (nextResult.status === "resolved" && nextResult.mode === "compiled_artifact") {
      runAgentDemo();
      return;
    }
    setResult(nextResult);
    if (nextResult.status === "resolved") setShowMaterial(false);
    setControlDecisions({});
    if (nextResult.status === "resolved") {
      const nextPreset = nextResult.preset;
      setSelectedEvidence({ kind: "entity", id: nextPreset.entityTypes[0].id });
      setIncludedCandidates(new Set([
        ...nextPreset.entityTypes.map(({ id }) => candidateKey("entity", id)),
        ...nextPreset.relationTypes.map(({ id }) => candidateKey("relation", id)),
      ]));
      if (nextPreset.productMode === "phase1_decision_modeling") {
        setInvestigationStatus("loading");
        try {
          const response = await fetch("/artifacts/quality-investigation.json");
          if (!response.ok) throw new Error("investigation artifact unavailable");
          const nextInvestigation = await response.json();
          if (
            nextInvestigation.schema !== "investigation_scope.v1"
            || nextInvestigation.evidence_scope !== "synthetic_demo"
            || nextInvestigation.root_cause_confirmed !== false
            || nextInvestigation.quality_signal_id !== nextPreset.event.id
            || nextInvestigation.control_scope_objects?.some((object) => !nextPreset.documentText.includes(object.object_id))
            || !Array.isArray(nextInvestigation.control_scope_objects)
            || !Array.isArray(nextInvestigation.factors)
            || !Array.isArray(nextInvestigation.gaps)
          ) {
            throw new Error("investigation artifact contract mismatch");
          }
          setInvestigation(nextInvestigation);
          setInvestigationStatus("succeeded");
        } catch {
          setInvestigation(null);
          setInvestigationStatus("error");
        }
      } else {
        setInvestigation(null);
        setInvestigationStatus("idle");
      }
    } else {
      setSelectedEvidence(null);
      setIncludedCandidates(new Set());
      setInvestigation(null);
      setInvestigationStatus("idle");
    }
    setReviewNote("");
    setDecisionPack(null);
  };

  const preset = result?.status === "resolved" ? result.preset : null;
  const evidenceItems = preset ? [
    ...preset.entityTypes.map((item) => ({ ...item, kind: "entity" })),
    ...preset.relationTypes.map((item) => ({ ...item, kind: "relation" })),
  ] : [];
  const evidence = selectedEvidence
    ? evidenceItems.find(({ id, kind }) => id === selectedEvidence.id && kind === selectedEvidence.kind)
    : null;
  const isPhase1 = preset?.productMode === "phase1_decision_modeling";
  const evidenceRecord = isPhase1 && evidence?.evidenceRef
    ? preset.sourceRecords.find(({ id }) => id === evidence.evidenceRef)
    : null;
  const isEvidenceIncluded = evidence
    ? includedCandidates.has(candidateKey(evidence.kind, evidence.id))
    : false;
  const canRestoreEvidence = !evidence || evidence.kind !== "relation" || (
    includedCandidates.has(candidateKey("entity", evidence.source))
    && includedCandidates.has(candidateKey("entity", evidence.target))
  );
  const selectedObjectCount = preset
    ? preset.entityTypes.filter(({ id }) => includedCandidates.has(candidateKey("entity", id))).length
    : 0;
  const selectedRelationCount = preset
    ? preset.relationTypes.filter(({ id }) => includedCandidates.has(candidateKey("relation", id))).length
    : 0;
  const controlScopeObjects = investigation?.control_scope_objects ?? [];
  const reviewedControlCount = controlScopeObjects.filter(
    (object) => controlDecisions[object.object_id],
  ).length;
  const controlDecisionCounts = controlScopeObjects.reduce((counts, object) => {
    const decision = controlDecisions[object.object_id];
    if (decision) counts[decision] += 1;
    return counts;
  }, { include: 0, exclude: 0, needs_evidence: 0 });
  const controlScopeComplete = controlScopeObjects.length > 0
    && reviewedControlCount === controlScopeObjects.length;

  const toggleCandidate = () => {
    if (!evidence) return;
    setIncludedCandidates((current) => {
      const next = new Set(current);
      const key = candidateKey(evidence.kind, evidence.id);
      if (next.has(key)) {
        next.delete(key);
        if (evidence.kind === "entity") {
          for (const relation of preset.relationTypes) {
            if (relation.source === evidence.id || relation.target === evidence.id) {
              next.delete(candidateKey("relation", relation.id));
            }
          }
        }
      } else {
        if (evidence.kind === "relation" && !canRestoreEvidence) return current;
        next.add(key);
      }
      return next;
    });
    setDecisionPack(null);
  };

  const confirmDecisionPack = () => {
    const selectedEntityIds = preset.entityTypes
      .filter(({ id }) => includedCandidates.has(candidateKey("entity", id)))
      .map(({ id }) => id);
    const selectedRelationIds = preset.relationTypes
      .filter(({ id }) => includedCandidates.has(candidateKey("relation", id)))
      .map(({ id }) => id);
    setDecisionPack(buildPhase1DecisionPack(preset, {
      selectedEntityIds,
      selectedRelationIds,
      reviewNote,
    }));
  };

  return (
    <div className={`document-modeler ${!showMaterial ? "document-material-collapsed" : ""}`}>
      <button className="document-material-toggle" type="button" aria-expanded={showMaterial} onClick={() => setShowMaterial((value) => !value)}>{language === "zh" ? (showMaterial ? "收起案例材料" : "展开案例材料") : (showMaterial ? "Hide case material" : "Show case material")}</button>
      <section className="document-modeler-controls" aria-labelledby="document-modeler-title">
        <header>
          <span>QUALITY EVENT TRACE / PHASE 1</span>
          <h2 id="document-modeler-title">{t.title}</h2>
          <p>{t.intro}</p>
        </header>
        <div className="document-scenario-group">
          <span>{t.scenario}</span>
          <div className="document-scenario-list">
            {DOCUMENT_MODELING_PRESETS.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={scenarioId === item.id ? "is-active" : ""}
                aria-pressed={scenarioId === item.id}
                onClick={() => selectScenario(item)}
              >
                <small>0{index + 1} · synthetic_demo</small>
                <strong>{item.title[language] ?? item.title.en}</strong>
              </button>
            ))}
          </div>
        </div>
        <label className="document-text-control">
          <span>{t.document}</span>
          <textarea
            rows={8}
            readOnly
            value={documentText}

          />
        </label>
        <button className="document-generate" type="button" onClick={generate}>
          <Braces size={17} />{t.generate}<ArrowRight size={17} />
        </button>
      </section>

      <section className="document-modeler-output" aria-live="polite">
        {!result && (
          <div className="document-modeler-empty">
            <ScrollText size={30} strokeWidth={1.4} />
            <p>{t.empty}</p>
          </div>
        )}
        {result?.status === "unsupported" && (
          <div className="document-modeler-empty is-unsupported" role="status">
            <ScrollText size={30} strokeWidth={1.4} />
            <strong>{t.unsupported}</strong>
            <p>{t.unsupportedBody}</p>
          </div>
        )}
        {preset && (
          <>
            <header className="document-output-header">
              <div>
                <span>{preset.mode === "scenario_preview" ? "SCENARIO PREVIEW / NOT COMPILED" : t.compiledReady}</span>
                <strong>{preset.title[language] ?? preset.title.en}</strong>
              </div>
              <small>synthetic_demo</small>
            </header>
            {isPhase1 && (
              <>
                <section className="quality-event-summary" aria-label={t.event}>
                  <div>
                    <span>{t.event}</span>
                    <strong>{preset.event.id}</strong>
                    <p>{preset.event.signal}</p>
                  </div>
                  <dl>
                    <div><dt>{t.eventStatus}</dt><dd>{preset.event.status}</dd></div>
                    <div><dt>{t.detectedAt}</dt><dd>{preset.event.detectedAt}</dd></div>
                  </dl>
                  <div>
                    <span>{t.investigation}</span>
                    <p>{preset.investigationQuestion}</p>
                  </div>
                </section>
                <section className="source-record-list" aria-label={t.sourceRecords}>
                  <header><span>{t.sourceRecords}</span><small>synthetic_demo</small></header>
                  <div>
                    {preset.sourceRecords.map((record) => (
                      <article key={record.id} className={record.status === "missing" ? "is-missing" : "is-available"}>
                        <header><span>{record.sourceSystem}</span><strong>{record.status === "missing" ? t.missing : t.available}</strong></header>
                        <h3>{record.label}</h3>
                        <code>{record.id}</code>
                        <p>{record.detail}</p>
                        {record.observedAt && <small>{record.observedAt}</small>}
                      </article>
                    ))}
                  </div>
                </section>
                {investigationStatus === "loading" && (
                  <p className="investigation-scope-status">{t.investigationLoading}</p>
                )}
                {investigationStatus === "error" && (
                  <p className="investigation-scope-status is-error" role="status">{t.investigationLoadError}</p>
                )}
                {investigationStatus === "succeeded" && investigation && (
                  <section className="investigation-scope-summary" aria-label={t.investigationResults}>
                    <header>
                      <div><span>{t.investigationResults}</span><strong>{investigation.quality_signal_id}</strong></div>
                      <small>{t.rootCauseBoundary}</small>
                    </header>
                    <section className="control-scope-summary" aria-label={t.controlScope}>
                      <header><strong>{t.controlScope}</strong><small>{t.controlScopeBoundary}</small></header>
                      <div className="control-scope-groups">
                        {[
                          { status: "confirmed_impact", label: t.confirmedImpact },
                          { status: "possible_impact", label: t.possibleImpact },
                          { status: "excluded", label: t.excludedImpact },
                          { status: "not_evaluable", label: t.notEvaluableImpact },
                        ].map((group) => (
                          <section key={group.status} className={`is-${group.status}`}>
                            <header><span>{group.label}</span><strong>{investigation.control_scope_objects.filter((object) => object.status === group.status).length}</strong></header>
                            {investigation.control_scope_objects.filter((object) => object.status === group.status).map((object) => (
                              <article key={object.object_id}>
                                <span>{t.objectTypes[object.object_type] ?? object.object_type}</span>
                                <strong>{object.object_id}</strong>
                                <p>{object.reason}</p>
                                <small>{t.evidenceRefs}: {object.evidence_refs.join(" · ")}</small>
                                <div className="control-scope-actions">
                                  {[
                                    { id: "include", label: t.includeControl },
                                    { id: "exclude", label: t.excludeControl },
                                    { id: "needs_evidence", label: t.needsEvidence },
                                  ].map((action) => (
                                    <button
                                      key={action.id}
                                      type="button"
                                      className={controlDecisions[object.object_id] === action.id ? "is-active" : ""}
                                      aria-pressed={controlDecisions[object.object_id] === action.id}
                                      aria-label={`${object.object_id} · ${action.label}`}
                                      onClick={() => setControlDecisions((current) => ({ ...current, [object.object_id]: action.id }))}
                                    >
                                      {action.label}
                                    </button>
                                  ))}
                                </div>
                              </article>
                            ))}
                          </section>
                        ))}
                      </div>
                      <footer className="control-decision-summary">
                        <div><span>{t.reviewProgress}</span><strong>{reviewedControlCount} / {controlScopeObjects.length}</strong></div>
                        <div><span>{t.includeControl}</span><strong>{controlDecisionCounts.include}</strong></div>
                        <div><span>{t.excludeControl}</span><strong>{controlDecisionCounts.exclude}</strong></div>
                        <div><span>{t.needsEvidence}</span><strong>{controlDecisionCounts.needs_evidence}</strong></div>
                        <div><strong>{controlScopeComplete ? t.scopeComplete : t.scopePending}</strong><small>{t.scopeSessionBoundary}</small></div>
                      </footer>
                    </section>
                    <div className="investigation-factor-list">
                      {investigation.factors.map((factor) => (
                        <article key={`${factor.predicate}-${factor.factor_id}`} className={`is-${factor.status}`}>
                          <header><span>{factor.status === "priority" ? t.priority : t.weakened}</span><code>{factor.predicate}</code></header>
                          <strong>{factor.factor_id}</strong>
                          <div><small>{t.evidenceRefs}</small><p>{factor.evidence_refs.join(" · ")}</p></div>
                          {factor.counterevidence_refs.length > 0 && (
                            <div><small>{t.counterevidence}</small><p>{factor.counterevidence_refs.join(" · ")}</p></div>
                          )}
                        </article>
                      ))}
                    </div>
                    <div className="investigation-gap-list">
                      <span>{t.dataGaps}</span>
                      {investigation.gaps.map((gap) => (
                        <article key={gap.evidence_ref}>
                          <strong>{gap.source_system} · {gap.predicate}</strong>
                          <code>{gap.subject_id}</code>
                        </article>
                      ))}
                    </div>
                  </section>
                )}
                <div className="phase1-decision-card">
                  <div><span>{t.decision}</span><strong>{preset.decision}</strong></div>
                  <div><span>{t.owner}</span><strong>{preset.decisionOwner}</strong></div>
                  <div><span>{t.trigger}</span><strong>{preset.trigger}</strong></div>
                </div>
              </>
            )}
            <div className="document-graph" data-testid="document-candidate-graph">
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                nodesDraggable={false}
                nodesConnectable={false}
                edgesReconnectable={false}
                deleteKeyCode={null}
                fitView
                fitViewOptions={{ padding: 0.18 }}
                minZoom={0.45}
                maxZoom={1.4}
                proOptions={{ hideAttribution: true }}
                onNodeClick={(_, node) => setSelectedEvidence({ kind: "entity", id: node.id })}
                onEdgeClick={(_, edge) => setSelectedEvidence({ kind: "relation", id: edge.id })}
              >
                <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#c7c4ba" />
              </ReactFlow>
            </div>
            <div className="document-output-detail">
              <div className="document-evidence-list">
                <span>{t.evidence}</span>
                {evidenceItems.map((item) => {
                  const included = includedCandidates.has(candidateKey(item.kind, item.id));
                  return <button
                    key={`${item.kind}-${item.id}`}
                    type="button"
                    className={`document-evidence-item ${selectedEvidence?.kind === item.kind && selectedEvidence.id === item.id ? "is-active" : ""} ${isPhase1 && !included ? "is-excluded" : ""}`}
                    aria-pressed={selectedEvidence?.kind === item.kind && selectedEvidence.id === item.id}
                    onClick={() => setSelectedEvidence({ kind: item.kind, id: item.id })}
                  >
                    {item.kind === "entity" ? <Network size={13} /> : <GitBranch size={13} />}
                    <span><small>{item.kind === "entity" ? t.entity : t.relation}{isPhase1 ? ` · ${included ? t.keepCandidate : t.excludeCandidate}` : ""}</small><strong>{item.label}</strong></span>
                  </button>;
                })}
              </div>
              <aside className="document-evidence-inspector">
                <span>{t.evidence}</span>
                <strong>{evidence?.label}</strong>
                <p>{evidence?.evidenceText}</p>
                {evidence?.kind === "relation" && <code>{evidence.source} → {evidence.target}</code>}
                {evidenceRecord && (
                  <div className="document-source-record">
                    <small>{t.sourceRecord}</small>
                    <code>{evidenceRecord.sourceSystem} · {evidenceRecord.id}</code>
                    <p>{evidenceRecord.detail}</p>
                  </div>
                )}
                {isPhase1 && evidence && (
                  <button type="button" className="document-candidate-toggle" disabled={!isEvidenceIncluded && !canRestoreEvidence} onClick={toggleCandidate}>
                    {isEvidenceIncluded ? t.excludeCandidate : t.restoreCandidate}
                  </button>
                )}
                <div className="document-boundary"><small>{t.boundary}</small><p>{preset.boundary}</p></div>
              </aside>
            </div>
            {isPhase1 && (
              <section className="phase1-review" aria-label={t.candidatePack}>
                <header>
                  <div><span>{t.selectedCount}</span><strong>{selectedObjectCount} {t.entity} · {selectedRelationCount} {t.relation}</strong></div>
                  <small>{t.sessionOnly}</small>
                </header>
                <label>
                  <span>{t.reviewNote}</span>
                  <textarea rows={3} value={reviewNote} placeholder={t.reviewPlaceholder} onChange={(event) => { setReviewNote(event.target.value); setDecisionPack(null); }} />
                </label>
                <button type="button" className="phase1-confirm" disabled={selectedObjectCount < 2} onClick={confirmDecisionPack}>
                  <Check size={16} />{t.confirmPack}
                </button>
                {decisionPack && (
                  <div className="phase1-pack">
                    <header><div><span>{t.candidatePack}</span><strong>{t.packReady}</strong></div></header>
                    <code>{t.packSchema}</code>
                    <pre>{JSON.stringify(decisionPack, null, 2)}</pre>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </section>
    </div>
  );
}
