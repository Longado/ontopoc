export const DOCUMENT_MODELING_PRESETS = [
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
