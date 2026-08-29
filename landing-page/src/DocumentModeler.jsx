import { useMemo, useState } from "react";
import { Background, BackgroundVariant, MarkerType, ReactFlow } from "@xyflow/react";
import { ArrowRight, Braces, GitBranch, Network, Play, ScrollText } from "lucide-react";

import { DOCUMENT_MODELING_PRESETS, resolveDocumentModelingRequest } from "./documentModelingDemoModel.js";

const copy = {
  zh: {
    title: "从文档到候选模型",
    intro: "选择一段固定合成材料，检查候选实体、关系、文本证据与能力边界。",
    scenario: "01 / 选择演示场景",
    document: "02 / 文档内容",
    generate: "生成候选模型",
    evidence: "选中证据",
    empty: "运行确定性解析器后，这里会显示候选图与文本证据。",
    unsupported: "当前文本不受支持",
    unsupportedBody: "文档已被编辑或不属于所选预设。请恢复原预设文本后重新生成。",
    boundary: "能力边界",
    compiledReady: "COMPILED ARTIFACT ROUTE AVAILABLE",
    startCompiled: "Start compiled demo / 启动已编译演示",
    entity: "ENTITY TYPE",
    relation: "RELATION TYPE",
  },
  en: {
    title: "Document to candidate model",
    intro: "Choose fixed synthetic material and inspect candidate entities, relations, text evidence, and the capability boundary.",
    scenario: "01 / SELECT DEMO SCENARIO",
    document: "02 / DOCUMENT TEXT",
    generate: "GENERATE CANDIDATE MODEL",
    evidence: "SELECTED EVIDENCE",
    empty: "Run the deterministic parser to see the candidate graph and text evidence.",
    unsupported: "UNSUPPORTED DOCUMENT TEXT",
    unsupportedBody: "The document was edited or does not match the selected preset. Restore the preset text and generate again.",
    boundary: "CAPABILITY BOUNDARY",
    compiledReady: "COMPILED ARTIFACT ROUTE AVAILABLE",
    startCompiled: "Start compiled demo",
    entity: "ENTITY TYPE",
    relation: "RELATION TYPE",
  },
};

const positions = [
  { x: 24, y: 34 },
  { x: 268, y: 24 },
  { x: 268, y: 154 },
  { x: 510, y: 88 },
];

function projectCandidateGraph(preset) {
  return {
    nodes: preset.entityTypes.map((entity, index) => ({
      id: entity.id,
      position: positions[index],
      data: { label: entity.label },
    })),
    edges: preset.relationTypes.map((relation) => ({
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

export function DocumentModeler({ language, runDemo }) {
  const t = copy[language] ?? copy.en;
  const [scenarioId, setScenarioId] = useState(DOCUMENT_MODELING_PRESETS[0].id);
  const [documentText, setDocumentText] = useState(DOCUMENT_MODELING_PRESETS[0].documentText);
  const [result, setResult] = useState(null);
  const [selectedEvidence, setSelectedEvidence] = useState(null);

  const graph = useMemo(
    () => result?.status === "resolved" ? projectCandidateGraph(result.preset) : { nodes: [], edges: [] },
    [result],
  );

  const selectScenario = (preset) => {
    setScenarioId(preset.id);
    setDocumentText(preset.documentText);
    setResult(null);
    setSelectedEvidence(null);
  };

  const generate = () => {
    const nextResult = resolveDocumentModelingRequest(scenarioId, documentText);
    setResult(nextResult);
    setSelectedEvidence(nextResult.status === "resolved" ? { kind: "entity", id: nextResult.preset.entityTypes[0].id } : null);
  };

  const preset = result?.status === "resolved" ? result.preset : null;
  const evidenceItems = preset ? [
    ...preset.entityTypes.map((item) => ({ ...item, kind: "entity" })),
    ...preset.relationTypes.map((item) => ({ ...item, kind: "relation" })),
  ] : [];
  const evidence = selectedEvidence
    ? evidenceItems.find(({ id, kind }) => id === selectedEvidence.id && kind === selectedEvidence.kind)
    : null;

  return (
    <div className="document-modeler">
      <section className="document-modeler-controls" aria-labelledby="document-modeler-title">
        <header>
          <span>DETERMINISTIC DEMO PARSER / NO LIVE MODEL</span>
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
            value={documentText}
            onChange={(event) => {
              setDocumentText(event.target.value);
              setResult(null);
              setSelectedEvidence(null);
            }}
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
                {evidenceItems.map((item) => (
                  <button
                    key={`${item.kind}-${item.id}`}
                    type="button"
                    className={`document-evidence-item ${selectedEvidence?.kind === item.kind && selectedEvidence.id === item.id ? "is-active" : ""}`}
                    aria-pressed={selectedEvidence?.kind === item.kind && selectedEvidence.id === item.id}
                    onClick={() => setSelectedEvidence({ kind: item.kind, id: item.id })}
                  >
                    {item.kind === "entity" ? <Network size={13} /> : <GitBranch size={13} />}
                    <span><small>{item.kind === "entity" ? t.entity : t.relation}</small><strong>{item.label}</strong></span>
                  </button>
                ))}
              </div>
              <aside className="document-evidence-inspector">
                <span>{t.evidence}</span>
                <strong>{evidence?.label}</strong>
                <p>{evidence?.evidenceText}</p>
                {evidence?.kind === "relation" && <code>{evidence.source} → {evidence.target}</code>}
                <div><small>{t.boundary}</small><p>{preset.boundary}</p></div>
                {preset.mode === "compiled_artifact" && (
                  <button type="button" onClick={runDemo}><Play size={15} fill="currentColor" />{t.startCompiled}</button>
                )}
              </aside>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
