import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
} from "@xyflow/react";
import {
  AlertTriangle,
  Boxes,
  Factory,
  GitCompareArrows,
  RotateCcw,
  Truck,
  UserCheck,
} from "lucide-react";
import "@xyflow/react/dist/style.css";

import {
  impactTraceEdges,
  impactTraceNodes,
  getImpactTraceFrame,
} from "./impactTraceModel.js";

const nodeIcons = {
  change: AlertTriangle,
  supplier: Factory,
  material: Boxes,
  order: Truck,
  "invalid-decision": GitCompareArrows,
  "human-gate": UserCheck,
};

function TraceNode({ id, data }) {
  const Icon = nodeIcons[id];
  const showTarget = id !== "change";
  const showSource = id !== "human-gate";

  return <>
    {showTarget && <Handle className="trace-handle" type="target" position={data.compact ? Position.Top : Position.Left} isConnectable={false} />}
    <button
      type="button"
      className={`trace-node trace-node-${data.kind} ${data.active ? "is-active" : ""} ${data.selected ? "is-selected" : ""}`}
      aria-pressed={data.selected}
      onClick={() => data.onSelect(id)}
    >
      <span className="trace-node-icon"><Icon size={15} strokeWidth={2.2} /></span>
      <span className="trace-node-copy"><small>{data.eyebrow}</small><strong>{data.title}</strong><em>{data.meta}</em></span>
    </button>
    {showSource && <Handle className="trace-handle" type="source" position={data.compact ? Position.Bottom : Position.Right} isConnectable={false} />}
  </>;
}

const nodeTypes = { trace: TraceNode };

export function ImpactTrace({ active, copy }) {
  const [step, setStep] = useState(0);
  const [runKey, setRunKey] = useState(0);
  const [selectedId, setSelectedId] = useState("change");
  const [compact, setCompact] = useState(() => window.innerWidth <= 1120);
  const frame = getImpactTraceFrame(step);

  useEffect(() => {
    const onResize = () => setCompact(window.innerWidth <= 1120);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
      setStep(impactTraceEdges.length);
      setSelectedId("human-gate");
      return undefined;
    }

    let nextStep = 0;
    setStep(0);
    setSelectedId("change");
    const timer = window.setInterval(() => {
      nextStep += 1;
      setStep(nextStep);
      setSelectedId(impactTraceEdges[nextStep - 1].target);
      if (nextStep === impactTraceEdges.length) window.clearInterval(timer);
    }, 620);
    return () => window.clearInterval(timer);
  }, [active, runKey]);

  const nodes = useMemo(() => impactTraceNodes.map((node, index) => {
    const nodeCopy = copy.nodes[node.id];
    const compactPositions = [
      { x: 90, y: 0 }, { x: 0, y: 135 }, { x: 180, y: 135 },
      { x: 90, y: 270 }, { x: 90, y: 405 }, { x: 90, y: 540 },
    ];
    return {
      ...node,
      position: compact ? compactPositions[index] : node.position,
      type: "trace",
      draggable: false,
      selectable: false,
      data: {
        ...nodeCopy,
        kind: node.kind,
        active: frame.activeNodeIds.includes(node.id),
        selected: selectedId === node.id,
        compact,
        onSelect: setSelectedId,
      },
    };
  }), [compact, copy.nodes, frame.activeNodeIds, selectedId]);

  const edges = useMemo(() => impactTraceEdges.map((edge) => {
    const isActive = frame.activeEdgeIds.includes(edge.id);
    return {
      ...edge,
      type: compact ? "straight" : "smoothstep",
      animated: isActive && frame.status !== "awaiting_approval",
      markerEnd: { type: MarkerType.ArrowClosed, color: isActive ? "#1757dc" : "#aaa9a2", width: 15, height: 15 },
      style: { stroke: isActive ? "#1757dc" : "#aaa9a2", strokeWidth: isActive ? 2.4 : 1.2 },
      className: isActive ? "is-active" : "",
    };
  }), [compact, frame.activeEdgeIds, frame.status]);

  const selected = copy.nodes[selectedId];
  const isComplete = frame.status === "awaiting_approval";

  return <div className="impact-trace">
    <header className="impact-trace-header">
      <div><span>{copy.kicker}</span><strong>{isComplete ? copy.awaiting : copy.tracing}</strong></div>
      <div className="trace-step"><span>{String(step).padStart(2, "0")}</span><i /> <span>{String(impactTraceEdges.length).padStart(2, "0")}</span></div>
      <button type="button" onClick={() => setRunKey((value) => value + 1)} aria-label={copy.replayLabel}><RotateCcw size={15} />{copy.replay}</button>
    </header>
    <div className="impact-trace-body">
      <div className="impact-flow" aria-label={copy.ariaLabel}>
        <ReactFlow
          key={compact ? "compact" : "wide"}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          fitView
          fitViewOptions={{ padding: 0.11, minZoom: 0.48, maxZoom: 1 }}
          minZoom={0.48}
          maxZoom={1.2}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          panOnDrag={false}
          panOnScroll={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
        >
          <Background color="#d1cec3" gap={28} size={1} />
        </ReactFlow>
      </div>
      <aside className={`trace-inspector trace-inspector-${selected.kind}`} aria-live="polite">
        <span>{selected.eyebrow}</span>
        <h4>{selected.title}</h4>
        <p>{selected.detail}</p>
        <div><span>{copy.currentState}</span><strong>{selected.meta}</strong></div>
        {selectedId === "human-gate" && <small><UserCheck size={14} />{copy.stopNote}</small>}
      </aside>
    </div>
  </div>;
}
