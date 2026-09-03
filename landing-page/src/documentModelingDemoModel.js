export const DOCUMENT_MODELING_PRESETS = [
  {
    id: "quality-temporary-control",
    title: { zh: "质量临时控制", en: "Quality temporary control" },
    evidenceScope: "synthetic_demo",
    mode: "scenario_preview",
    productMode: "phase1_decision_modeling",
    event: {
      id: "QI-DEMO-017",
      signal: "终检发现泄漏率异常",
      status: "待调查",
      detectedAt: "2026-08-04 09:10",
    },
    investigationQuestion: "该异常与哪些批次、在制品和待发运件有关，哪条关键链路仍然缺失？",
    decision: "哪些在制品和待发运件进入临时控制或复检队列？",
    decisionOwner: "质量负责人",
    trigger: "终检发现泄漏率异常且原因尚未确认",
    documentText: "synthetic_demo\n终检发现质量事件 QI-DEMO-017：批次 B-17 的组件出现泄漏率异常，原因尚未确认。质量负责人需要判断在制品 WIP-B17 与待发运件 SHIP-B17 是否进入临时控制或复检队列。WIP-B17 使用批次 B-17；SHIP-B17 由 WIP-B17 形成，项目映射尚缺失。",
    sourceRecords: [
      {
        id: "qms:quality-event-017",
        sourceSystem: "QMS_SYNTHETIC",
        status: "available",
        label: "终检异常记录",
        observedAt: "2026-08-04 09:10",
        detail: "记录质量事件、异常指标与关联组件批次。",
      },
      {
        id: "mes:material-use-017",
        sourceSystem: "MES_SYNTHETIC",
        status: "available",
        label: "实际投料记录",
        observedAt: "2026-08-04 08:42",
        detail: "记录在制品 WIP-B17 实际使用批次 B-17。",
      },
      {
        id: "wms:shipment-formation-017",
        sourceSystem: "WMS_SYNTHETIC",
        status: "available",
        label: "待发运形成记录",
        observedAt: "2026-08-04 10:05",
        detail: "记录待发运件 SHIP-B17 由 WIP-B17 形成。",
      },
      {
        id: "plm:project-product-map-017",
        sourceSystem: "PLM_SYNTHETIC",
        status: "missing",
        label: "项目与产品映射",
        observedAt: null,
        detail: "尚未取得项目映射，当前不能继续判断对应项目范围。",
      },
    ],
    entityTypes: [
      { id: "quality-event", label: "质量事件 QI-DEMO-017", evidenceText: "质量事件 QI-DEMO-017", evidenceRef: "qms:quality-event-017" },
      { id: "material-batch", label: "批次 B-17", evidenceText: "批次 B-17", evidenceRef: "qms:quality-event-017" },
      { id: "work-in-progress", label: "在制品 WIP-B17", evidenceText: "在制品 WIP-B17", evidenceRef: "mes:material-use-017" },
      { id: "pending-shipment", label: "待发运件 SHIP-B17", evidenceText: "待发运件 SHIP-B17", evidenceRef: "wms:shipment-formation-017" },
    ],
    relationTypes: [
      { id: "event-involves-batch", label: "INVOLVES", source: "quality-event", target: "material-batch", evidenceText: "质量事件 QI-DEMO-017：批次 B-17 的组件出现泄漏率异常", evidenceRef: "qms:quality-event-017" },
      { id: "wip-uses-batch", label: "USES_BATCH", source: "work-in-progress", target: "material-batch", evidenceText: "WIP-B17 使用批次 B-17", evidenceRef: "mes:material-use-017" },
      { id: "wip-forms-shipment", label: "FORMS_SHIPMENT", source: "work-in-progress", target: "pending-shipment", evidenceText: "SHIP-B17 由 WIP-B17 形成", evidenceRef: "wms:shipment-formation-017" },
    ],
    boundary: "候选只在当前浏览器会话中供 FDE 选择和修正；不会发布、创建外部任务或写回业务系统。",
  },
  {
    id: "supply-chain-order-intervention",
    title: { zh: "供应链订单干预", en: "Supply-chain order intervention" },
    evidenceScope: "synthetic_demo",
    mode: "compiled_artifact",
    documentText: "synthetic_demo：供应链计划经理负责判断哪些订单进入优先干预队列；当订单预计交期、物料齐套或供应商承诺发生异常时，检查客户订单、物料与供应商关系。本材料为固定演示输入，不含客户事实，不触发发布、Action 或 ERP 写回。",
    entityTypes: [
      { id: "customer-order", label: "客户订单", evidenceText: "检查客户订单、物料与供应商关系" },
      { id: "material", label: "物料", evidenceText: "检查客户订单、物料与供应商关系" },
      { id: "supplier", label: "供应商", evidenceText: "供应商承诺发生异常" },
    ],
    relationTypes: [
      { id: "order-requires-material", label: "REQUIRES", source: "customer-order", target: "material", evidenceText: "客户订单与物料关系" },
      { id: "supplier-qualified-material", label: "QUALIFIED_TO_SUPPLY", source: "supplier", target: "material", evidenceText: "供应商与物料资格关系" },
      { id: "supplier-supplied-material", label: "HAS_SUPPLIED", source: "supplier", target: "material", evidenceText: "供应商与物料供货关系" },
    ],
    boundary: "固定合成文本匹配已知模板后，加载仓库内已提交的编译产物并等待会话内人工确认。",
  },
  {
    id: "supplier-qualification-change",
    title: { zh: "供应商资格变更", en: "Supplier qualification change" },
    evidenceScope: "synthetic_demo",
    mode: "scenario_preview",
    documentText: "synthetic_demo\n供应商 SUP-DEMO-B 的资格状态拟从“条件准入”调整为“暂停新增订单”。变更记录引用评审项 REV-DEMO-8，并要求采购负责人确认受影响的物料类别与生效范围。",
    entityTypes: [
      { id: "supplier", label: "Supplier", evidenceText: "供应商 SUP-DEMO-B" },
      { id: "qualification", label: "Qualification status", evidenceText: "条件准入调整为暂停新增订单" },
      { id: "review", label: "Review item", evidenceText: "评审项 REV-DEMO-8" },
      { id: "material-category", label: "Material category", evidenceText: "需要确认受影响的物料类别" },
    ],
    relationTypes: [
      { id: "supplier-has-qualification", label: "HAS_STATUS", source: "supplier", target: "qualification", evidenceText: "供应商资格状态拟变更" },
      { id: "review-supports-qualification", label: "SUPPORTS", source: "review", target: "qualification", evidenceText: "变更记录引用评审项" },
      { id: "qualification-affects-category", label: "AFFECTS", source: "qualification", target: "material-category", evidenceText: "需确认受影响类别与范围" },
    ],
    boundary: "仅展示固定合成文本中的候选实体与关系；未运行识别、编译或业务资格变更。",
  },
  {
    id: "dairy-rd-fallback",
    title: { zh: "乳品研发回退", en: "Dairy R&D fallback" },
    evidenceScope: "synthetic_demo",
    mode: "scenario_preview",
    documentText: "synthetic_demo\n研发样品 SAMPLE-DEMO-B 的消费者测试未达到预设门槛。研发负责人需要依据测试记录 TEST-DEMO-12，决定保留当前样品、补充验证，或回退到配方候选 FORMULA-DEMO-A。",
    entityTypes: [
      { id: "sample", label: "R&D sample", evidenceText: "研发样品 SAMPLE-DEMO-B" },
      { id: "consumer-test", label: "Consumer test", evidenceText: "测试记录 TEST-DEMO-12" },
      { id: "formula", label: "Formula candidate", evidenceText: "配方候选 FORMULA-DEMO-A" },
      { id: "fallback-decision", label: "Fallback decision", evidenceText: "保留、补充验证或回退" },
    ],
    relationTypes: [
      { id: "sample-evaluated-by-test", label: "EVALUATED_BY", source: "sample", target: "consumer-test", evidenceText: "样品消费者测试未达到门槛" },
      { id: "sample-derived-from-formula", label: "DERIVED_FROM", source: "sample", target: "formula", evidenceText: "样品可回退到配方候选" },
      { id: "decision-governs-sample", label: "GOVERNS", source: "fallback-decision", target: "sample", evidenceText: "研发负责人决定样品后续路径" },
    ],
    boundary: "仅展示固定合成文本中的候选实体与关系；未运行研发判断、配方变更或后续任务。",
  },
];

export function resolveDocumentModelingRequest(scenarioId, documentText) {
  const preset = DOCUMENT_MODELING_PRESETS.find(({ id }) => id === scenarioId);
  if (!preset || typeof documentText !== "string" || documentText.trim() !== preset.documentText.trim()) {
    return { status: "unsupported", mode: "unsupported" };
  }

  return { status: "resolved", mode: preset.mode, preset };
}

export function buildPhase1DecisionPack(preset, review) {
  if (!preset || preset.productMode !== "phase1_decision_modeling") {
    throw new Error("Phase 1 decision-modeling preset is required");
  }
  if (!review || !Array.isArray(review.selectedEntityIds) || !Array.isArray(review.selectedRelationIds)) {
    throw new Error("FDE candidate selections are required");
  }

  const entityIds = new Set(preset.entityTypes.map(({ id }) => id));
  const relationIds = new Set(preset.relationTypes.map(({ id }) => id));
  const selectedEntityIds = new Set(review.selectedEntityIds);
  const selectedRelationIds = new Set(review.selectedRelationIds);
  if (selectedEntityIds.size !== review.selectedEntityIds.length || selectedRelationIds.size !== review.selectedRelationIds.length) {
    throw new Error("FDE candidate selections must be unique");
  }
  if ([...selectedEntityIds].some((id) => !entityIds.has(id))) {
    throw new Error("unknown selected entity");
  }
  if ([...selectedRelationIds].some((id) => !relationIds.has(id))) {
    throw new Error("unknown selected relation");
  }

  const objects = preset.entityTypes
    .filter(({ id }) => selectedEntityIds.has(id))
    .map(({ id, label, evidenceText }) => ({
      object_id: id,
      label,
      evidence_span: evidenceText,
    }));
  if (objects.length < 2) throw new Error("at least two selected objects are required");

  const relations = preset.relationTypes
    .filter(({ id }) => selectedRelationIds.has(id))
    .map(({ id, label, source, target, evidenceText }) => {
      if (!selectedEntityIds.has(source) || !selectedEntityIds.has(target)) {
        throw new Error("selected relation endpoints must remain selected");
      }
      return {
        relation_id: id,
        predicate: label,
        source_object_id: source,
        target_object_id: target,
        evidence_span: evidenceText,
      };
    });

  for (const candidate of [...objects, ...relations]) {
    if (!preset.documentText.includes(candidate.evidence_span)) {
      throw new Error("candidate evidence must be an exact source substring");
    }
  }

  return {
    schema: "decision_pack.phase1_candidate.v1",
    status: "candidate",
    evidence_scope: preset.evidenceScope,
    scenario_id: preset.id,
    decision: {
      question: preset.decision,
      owner: preset.decisionOwner,
      trigger: preset.trigger,
    },
    objects,
    relations,
    fde_review: {
      note: typeof review.reviewNote === "string" ? review.reviewNote.trim() : "",
      selected_object_ids: objects.map(({ object_id }) => object_id),
      selected_relation_ids: relations.map(({ relation_id }) => relation_id),
    },
    delivery_boundary: {
      session_only: true,
      published: false,
      external_action_created: false,
    },
  };
}
