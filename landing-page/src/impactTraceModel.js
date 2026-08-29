export const impactTraceNodes = [
  { id: "change", kind: "change", position: { x: 0, y: 128 } },
  { id: "supplier", kind: "object", position: { x: 210, y: 36 } },
  { id: "material", kind: "object", position: { x: 210, y: 220 } },
  { id: "order", kind: "object", position: { x: 440, y: 128 } },
  { id: "invalid-decision", kind: "decision", position: { x: 680, y: 128 } },
  { id: "human-gate", kind: "gate", position: { x: 930, y: 128 } },
];

export const impactTraceEdges = [
  { id: "change-supplier", source: "change", target: "supplier" },
  { id: "change-material", source: "change", target: "material" },
  { id: "supplier-order", source: "supplier", target: "order" },
  { id: "material-order", source: "material", target: "order" },
  { id: "order-invalid", source: "order", target: "invalid-decision" },
  { id: "invalid-gate", source: "invalid-decision", target: "human-gate" },
];

export function getImpactTraceFrame(requestedStep) {
  const step = Math.max(0, Math.min(impactTraceEdges.length, requestedStep));
  const activeEdges = impactTraceEdges.slice(0, step);
  const activeNodeIds = [
    "change",
    ...new Set(activeEdges.map((edge) => edge.target)),
  ];

  return {
    step,
    activeEdgeIds: activeEdges.map((edge) => edge.id),
    activeNodeIds,
    status: step === impactTraceEdges.length ? "awaiting_approval" : "tracing",
  };
}
