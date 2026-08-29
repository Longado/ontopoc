import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowRight,
  Box,
  GitBranch,
  Maximize2,
  MessageSquareText,
  RotateCcw,
  ScrollText,
  Send,
  X,
} from "lucide-react";

import { answerArtifactQuestion, keepOntologySelection } from "./ontologyWorkspaceModel.js";

const localCopy = {
  zh: {
    viewLabel: "OntologySpec 视图",
    graph: "Graph",
    details: "Details",
    graphStatus: "ONTOLOGY SPEC / READ ONLY",
    graphSummary: "3 个实体类型 · 3 个关系类型 · 1 条 candidate rule",
    fit: "适配画布",
    reset: "重置",
    inspector: "证据检查器",
    inspectHint: "选择节点或有向边查看稳定身份、来源和证据定位。",
    stableId: "STABLE ID",
    semantic: "SEMANTIC KEY / PREDICATE",
    origin: "ORIGIN_KIND / REF",
    governance: "CANDIDATE STATUS",
    evidence: "CANONICAL JSON POINTER",
    source: "SOURCE EVIDENCE",
    sourceNone: "无外部 source；这是 provided scenario bridge/input。",
    caveat: "CAVEAT",
    locator: "LOCATOR",
    properties: "节点属性",
    conditions: "规则条件",
    ask: "询问这个 artifact",
    chatTitle: "确定性 artifact 查询",
    chatBoundary: "非实时模型调用",
    chatIntro: "只回答当前 pack/spec 中可确定性定位的内容，并附哈希与证据指针。",
    closeChat: "关闭问答",
    suggestionsLabel: "可以这样问",
    suggestions: ["有哪些实体和关系？", "candidate rule 是什么？", "有哪些内容需要复核？"],
    placeholder: "输入关于当前 artifact 的问题",
    send: "发送",
    enter: "Enter 发送 · Shift + Enter 换行",
    reason: "REFUSAL REASON",
    evidenceRefs: "EVIDENCE",
    packHash: "PACK HASH",
    specHash: "SPEC HASH",
    runtimeMissing: "缺少运行实例，不能推断订单或供应商状态。",
  },
  en: {
    viewLabel: "OntologySpec views",
    graph: "Graph",
    details: "Details",
    graphStatus: "ONTOLOGY SPEC / READ ONLY",
    graphSummary: "3 entity types · 3 relation types · 1 candidate rule",
    fit: "FIT",
    reset: "RESET",
    inspector: "EVIDENCE INSPECTOR",
    inspectHint: "Select a node or directed edge to inspect stable identity, provenance, and evidence location.",
    stableId: "STABLE ID",
    semantic: "SEMANTIC KEY / PREDICATE",
    origin: "ORIGIN_KIND / REF",
    governance: "CANDIDATE STATUS",
    evidence: "CANONICAL JSON POINTER",
    source: "SOURCE EVIDENCE",
    sourceNone: "No external source; this is a provided scenario bridge/input.",
    caveat: "CAVEAT",
    locator: "LOCATOR",
    properties: "NODE PROPERTIES",
    conditions: "RULE CONDITIONS",
    ask: "ASK THIS ARTIFACT",
    chatTitle: "DETERMINISTIC ARTIFACT QUERY",
    chatBoundary: "NOT A LIVE MODEL CALL",
    chatIntro: "Answers only what can be located deterministically in the current pack/spec, with hashes and evidence pointers.",
    closeChat: "CLOSE QUERY",
    suggestionsLabel: "TRY A QUESTION",
    suggestions: ["Which entities and relations exist?", "What is the candidate rule?", "What requires review?"],
    placeholder: "Ask about the current artifact",
    send: "SEND",
    enter: "Enter to send · Shift + Enter for a new line",
    reason: "REFUSAL REASON",
    evidenceRefs: "EVIDENCE",
    packHash: "PACK HASH",
    specHash: "SPEC HASH",
    runtimeMissing: "Runtime instances are absent; order or supplier state cannot be inferred.",
  },
};

function handleOffset(index, count) {
  return `${((index + 1) / (count + 1)) * 100}%`;
}

function EntityNode({ data }) {
  return (
    <div className={`ontology-node ontology-entity-node ${data.selected ? "is-selected" : ""}`}>
      {data.inputHandles.map((id, index) => (
        <Handle
          key={id}
          id={id}
          type="target"
          position={Position.Left}
          isConnectable={false}
          className="ontology-handle"
          style={{ top: handleOffset(index, data.inputHandles.length) }}
        />
      ))}
      <div className="ontology-node-icon"><Box size={18} strokeWidth={1.7} /></div>
      <div className="ontology-node-copy"><small>{data.roleKey}</small><strong>{data.label}</strong><span>{data.semanticKey}</span></div>
      {data.outputHandles.map((id, index) => (
        <Handle
          key={id}
          id={id}
          type="source"
          position={Position.Right}
          isConnectable={false}
          className="ontology-handle"
          style={{ top: handleOffset(index, data.outputHandles.length) }}
        />
      ))}
    </div>
  );
}

function RuleNode({ data }) {
  return (
    <div className={`ontology-node ontology-rule-node ${data.selected ? "is-selected" : ""}`}>
      {data.inputHandles.map((id) => (
        <Handle
          key={id}
          id={id}
          type="target"
          position={Position.Left}
          isConnectable={false}
          className="ontology-handle"
        />
      ))}
      <div className="ontology-node-icon"><ScrollText size={18} strokeWidth={1.7} /></div>
      <div className="ontology-node-copy"><small>{data.label}</small><strong>{data.ruleKind}</strong><span>{data.semanticKey}</span></div>
    </div>
  );
}

const nodeTypes = {
  ontologyEntity: EntityNode,
  ontologyRule: RuleNode,
};

function GraphCanvas({ workspace, selected, onSelect, copy }) {
  const { fitView, setViewport } = useReactFlow();
  const nodes = useMemo(
    () => workspace.nodes.map((node) => ({
      ...node,
      selected: selected.kind === "node" && selected.id === node.id,
      data: {
        ...node.data,
        selected: selected.kind === "node" && selected.id === node.id,
      },
    })),
    [selected, workspace.nodes],
  );
  const edges = useMemo(
    () => workspace.edges.map((edge) => ({
      ...edge,
      selected: selected.kind === "edge" && selected.id === edge.id,
      style: {
        ...edge.style,
        strokeWidth: selected.kind === "edge" && selected.id === edge.id ? 2.8 : edge.style.strokeWidth,
      },
    })),
    [selected, workspace.edges],
  );

  const reset = () => {
    onSelect({ kind: "node", id: workspace.entityNodes[0].id });
    setViewport({ x: 18, y: 18, zoom: 0.82 }, { duration: 180 });
  };

  return (
    <div className="ontology-canvas-shell">
      <div className="ontology-graph-status">
        <div><span>{copy.graphStatus}</span><small>{copy.graphSummary}</small></div>
        <div>
          <button type="button" onClick={() => fitView({ padding: 0.15, duration: 180 })}><Maximize2 size={13} />{copy.fit}</button>
          <button type="button" onClick={reset}><RotateCcw size={13} />{copy.reset}</button>
        </div>
      </div>
      <div className="ontology-graph-canvas" data-testid="ontology-spec-graph">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesReconnectable={false}
          elementsSelectable
          deleteKeyCode={null}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.34}
          maxZoom={1.65}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => onSelect({ kind: "node", id: node.id })}
          onEdgeClick={(_, edge) => onSelect({ kind: "edge", id: edge.id })}
          onSelectionChange={(selection) => {
            const node = selection.nodes.at(-1);
            const edge = selection.edges.at(-1);
            if (node) onSelect({ kind: "node", id: node.id });
            else if (edge) onSelect({ kind: "edge", id: edge.id });
          }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#c7c4ba" />
        </ReactFlow>
      </div>
    </div>
  );
}

function EvidenceField({ label, children }) {
  return <div className="ontology-evidence-field"><span>{label}</span><strong>{children}</strong></div>;
}

function EvidenceInspector({ item, copy, onOpenChat, chatTriggerRef }) {
  const data = item.data;
  const sources = data.sources ?? [];
  return (
    <div className="ontology-inspector">
      <header>
        <div><span>{copy.inspector}</span><p>{copy.inspectHint}</p></div>
        <GitBranch size={18} />
      </header>
      <div className="ontology-inspector-scroll">
        <EvidenceField label={copy.stableId}><code>{item.id}</code></EvidenceField>
        <EvidenceField label={copy.semantic}><code>{data.predicate ?? data.semanticKey}</code></EvidenceField>
        {data.triple && <EvidenceField label="TRIPLE"><code>{data.triple}</code></EvidenceField>}
        <EvidenceField label={copy.origin}><code>{data.originKind}<br />{data.originRefId}</code></EvidenceField>
        <EvidenceField label={copy.governance}><code>{data.governanceStatus}</code></EvidenceField>
        <EvidenceField label={copy.evidence}><code>{data.pointer}</code></EvidenceField>
        {data.properties?.length > 0 && (
          <div className="ontology-evidence-list">
            <span>{copy.properties}</span>
            {data.properties.map((property) => (
              <div key={property.id}><code>{property.semanticKey}</code><small>{property.valueType} · {property.governanceStatus}</small></div>
            ))}
          </div>
        )}
        {data.conditions?.length > 0 && (
          <div className="ontology-evidence-list">
            <span>{copy.conditions}</span>
            {data.conditions.map((condition) => (
              <div key={condition.propertyTypeId}><code>{condition.semanticKey}</code><small>{condition.operator} [{condition.allowedValues.join(", ")}]</small></div>
            ))}
          </div>
        )}
        <div className="ontology-source-block">
          <span>{copy.source}</span>
          <p>{data.sourceCaveat || copy.sourceNone}</p>
          {sources.map((source) => (
            <div key={source.id}>
              <strong>{source.title}</strong>
              <small>{copy.caveat}</small><p>{source.caveat}</p>
              <small>{copy.locator}</small><code>{source.locator}</code>
            </div>
          ))}
        </div>
      </div>
      <button ref={chatTriggerRef} className="ontology-chat-trigger" type="button" onClick={onOpenChat}>
        <MessageSquareText size={16} />{copy.ask}<ArrowRight size={15} />
      </button>
    </div>
  );
}

function ChatDrawer({ workspace, language, copy, onClose, drawerRef }) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const ask = (nextQuestion = question) => {
    const value = nextQuestion.trim();
    if (!value) return;
    const result = answerArtifactQuestion(value, workspace, language);
    setHistory((items) => [...items, { question: value, result }]);
    setQuestion("");
  };

  return (
    <aside ref={drawerRef} className="ontology-chat-drawer" role="dialog" aria-modal="true" aria-labelledby="ontology-chat-title">
      <header>
        <div><span>{copy.chatBoundary}</span><h3 id="ontology-chat-title">{copy.chatTitle}</h3></div>
        <button type="button" onClick={onClose} aria-label={copy.closeChat}><X size={16} /></button>
      </header>
      <p className="ontology-chat-intro">{copy.chatIntro}</p>
      <div className="ontology-chat-history" aria-live="polite">
        {history.length === 0 && (
          <div className="ontology-chat-suggestions"><span>{copy.suggestionsLabel}</span>{copy.suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => ask(suggestion)}>{suggestion}</button>)}</div>
        )}
        {history.map((exchange, index) => (
          <div className="ontology-chat-exchange" key={`${exchange.question}-${index}`}>
            <div className="ontology-chat-question">{exchange.question}</div>
            <div className={`ontology-chat-answer ${exchange.result.answerable ? "" : "is-refusal"}`}>
              <p>{exchange.result.answer}</p>
              {!exchange.result.answerable && <small><b>{copy.reason}</b> · {exchange.result.reason}{exchange.result.reason === "missing_runtime_facts" ? ` · ${copy.runtimeMissing}` : ""}</small>}
              <div className="ontology-chat-hashes"><code>{copy.packHash}<br />{exchange.result.packHash}</code><code>{copy.specHash}<br />{exchange.result.specHash}</code></div>
              {exchange.result.evidence.length > 0 && <div className="ontology-chat-evidence"><span>{copy.evidenceRefs}</span>{exchange.result.evidence.map((evidence) => <code key={`${evidence.pointer}-${evidence.stableId}`}>{evidence.pointer}<br />{evidence.stableId}{evidence.triple ? ` · ${evidence.triple}` : ""}</code>)}</div>}
            </div>
          </div>
        ))}
      </div>
      <form className="ontology-chat-form" onSubmit={(event) => { event.preventDefault(); ask(); }}>
        <textarea
          ref={inputRef}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              ask();
            }
          }}
          rows={2}
          placeholder={copy.placeholder}
        />
        <button type="submit" disabled={!question.trim()} aria-label={copy.send}><Send size={15} /></button>
        <small>{copy.enter}</small>
      </form>
    </aside>
  );
}

function DetailsView({ data, t }) {
  const countValues = Object.values(data.counts);
  return (
    <div className="workspace-detail-layout">
      <div className="workspace-detail-main">
        <div className="workspace-boundary-note"><GitBranch size={18} /><div><strong>{t.compilation}</strong><span>{t.closure}: closed · {t.checked}: {data.referenceClosure.checkedReferenceCount}</span></div></div>
        <div className="workspace-counts">{countValues.map((value, index) => <div key={t.counts[index]}><strong>{value}</strong><span>{t.counts[index]}</span></div>)}</div>
        <div className="workspace-issues"><span>{t.issues} · {data.reviewIssues.length}</span>{data.reviewIssues.map((issue) => <div key={issue.issue_id}><code>{issue.payload_schema}</code><p>{issue.message}</p><small>{issue.severity}</small></div>)}</div>
      </div>
      <aside className="workspace-detail-aside">
        <div className="workspace-hash"><span>{t.hash}</span><code>{data.contentHash}</code></div>
        <div className="workspace-hash"><span>{t.packHash}</span><code>{data.packContentHash}</code></div>
        <EvidenceField label="evidence_scope"><code>{data.evidenceScope}</code></EvidenceField>
        <EvidenceField label="stage"><code>{data.stage}</code></EvidenceField>
        <EvidenceField label={t.governance}><code>{data.governanceStatus}</code></EvidenceField>
      </aside>
    </div>
  );
}

export function OntologyWorkspace({ data, t, language }) {
  const copy = localCopy[language];
  const workspace = data.ontologyWorkspace;
  const [view, setView] = useState("graph");
  const [selected, setSelected] = useState({ kind: "node", id: workspace.entityNodes[0].id });
  const [chatOpen, setChatOpen] = useState(false);
  const chatTriggerRef = useRef(null);
  const drawerRef = useRef(null);
  const chatWasOpenRef = useRef(false);
  const selectItem = useCallback((next) => {
    setSelected((current) => keepOntologySelection(current, next));
  }, []);

  const selectedItem = selected.kind === "node"
    ? workspace.nodes.find(({ id }) => id === selected.id)
    : workspace.edges.find(({ id }) => id === selected.id);

  useEffect(() => {
    if (!chatOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setChatOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(drawerRef.current?.querySelectorAll("button:not([disabled]), textarea") ?? [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [chatOpen]);

  useEffect(() => {
    if (chatOpen) {
      chatWasOpenRef.current = true;
      return;
    }
    if (chatWasOpenRef.current) {
      chatWasOpenRef.current = false;
      chatTriggerRef.current?.focus();
    }
  }, [chatOpen]);

  const switchView = (next, event) => {
    setView(next);
    event?.currentTarget.parentElement?.querySelector(`#ontology-view-${next}`)?.focus();
  };

  return (
    <div className="ontology-workspace">
      <div className="ontology-view-tabs" role="tablist" aria-label={copy.viewLabel}>
        {["graph", "details"].map((item, index, views) => (
          <button
            key={item}
            id={`ontology-view-${item}`}
            type="button"
            role="tab"
            aria-selected={view === item}
            aria-controls={`ontology-panel-${item}`}
            tabIndex={view === item ? 0 : -1}
            className={view === item ? "is-active" : ""}
            onClick={() => setView(item)}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
              event.preventDefault();
              const direction = event.key === "ArrowRight" ? 1 : -1;
              switchView(views[(index + direction + views.length) % views.length], event);
            }}
          >
            {item === "graph" ? copy.graph : copy.details}
          </button>
        ))}
      </div>
      {view === "graph" ? (
        <div id="ontology-panel-graph" role="tabpanel" aria-labelledby="ontology-view-graph" className="ontology-graph-layout">
          <ReactFlowProvider>
            <GraphCanvas workspace={workspace} selected={selected} onSelect={selectItem} copy={copy} />
          </ReactFlowProvider>
          <div className="ontology-inspector-shell">
            <EvidenceInspector item={selectedItem} copy={copy} onOpenChat={() => setChatOpen(true)} chatTriggerRef={chatTriggerRef} />
            {chatOpen && <ChatDrawer workspace={workspace} language={language} copy={copy} onClose={() => setChatOpen(false)} drawerRef={drawerRef} />}
          </div>
        </div>
      ) : (
        <div id="ontology-panel-details" role="tabpanel" aria-labelledby="ontology-view-details">
          <DetailsView data={data} t={t} />
        </div>
      )}
    </div>
  );
}
