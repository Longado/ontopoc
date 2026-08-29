import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  BadgeCheck,
  Boxes,
  Check,
  ClipboardCheck,
  Database,
  Factory,
  FileCheck2,
  GitCompareArrows,
  Layers3,
  Link2,
  MoveHorizontal,
  PackageCheck,
  ScanSearch,
  ShieldCheck,
  Truck,
  UserCheck,
  Workflow,
  X,
} from "lucide-react";
import { ImpactTrace } from "./ImpactTrace.jsx";
import { TrialWorkspace } from "./TrialWorkspace.jsx";
import { moveStage, primaryNavTargets } from "./storylineModel.js";

const content = {
  zh: {
    ariaNav: "OntoPoc 主导航", home: "OntoPoc 首页", nav: { why: "问题", proof: "产品", how: "方法", model: "持续运行" }, trial: "体验场景",
    heroAlt: "供应链对象关系向订单判断传播的点阵", heroVision: "合成场景预览：规则变化后展示候选影响路径；不执行确认、生效或写回。",
    heroMeta: [["DETECT", "捕捉业务变化", "规则、数据、关系"], ["TRACE", "追到受影响订单", "供应商、物料、订单"], ["CONFIRM", "由业务确认生效", "补证、暂缓、确认"]], seeDelta: "查看影响路径",
    heroKicker: "ONTOLOGY-NATIVE SUPPLY CHAIN AI", whyEyebrow: "THE MISSING LAYER", whyTitle: ["知识库记住规则。", "OntoPoc 找出受影响的订单。"],
    whyLead: "ERP 记录交易，知识库沉淀规则；但规则一变，业务仍要重新检查哪些订单受影响、原处置是否还成立。OntoPoc 补上这层持续影响分析。",
    visionBody: "项目结束后留下可复用的对象关系、验证规则和确认记录，而不是一次性的分析报告。",
    proofEyebrow: "SUPPLY CHAIN SCENARIO", proofTitle: ["承诺期从 7 天变为 12 天，", "哪张订单要转入优先干预？"], proofLead: "合成场景预览展示供应商—物料—订单关系及订单 SC-2188 的候选处置路径；当前浏览器 demo 不执行重算、发布或 ERP 写回。",
    techPillars: [["RELATION GRAPH", "合成路径预览", "供应商 → 物料 → 订单"], ["CANDIDATE VIEW", "展示候选判断", "不执行 Validation 或运行时重算"], ["DELIVERY BOUNDARY", "仅展示确认边界", "不发布、不写回 ERP"]],
    modelEyebrow: "WHY IT COMPOUNDS", modelTitle: ["修正留得住，", "复核才会越来越快。"], modelLead: "持续复核闭环属于产品提案；当前已验证能力仅生成并检查 synthetic_demo 的 Recognition、DecisionPack 与 OntologySpec 编译 artifact，不保存确认记录。",
    modelSteps: [["01 / START", "从一个判断开始"], ["02 / CAPTURE", "留下修正依据"], ["03 / REUSE", "下次变化直接复核"]],
    deltaEyebrow: "CORE PRODUCT MOMENT", deltaTitle: ["先看业务结论，", "再看模型变化。"], deltaDescription: "选择一种业务变化，查看哪些供应链判断需要重新确认。以下为交互场景预览。", scenarioLabel: "选择业务变化", deltaAria: "DecisionDelta 交互场景预览",
    domain: "供应链 / 规则变化", decision: "业务判断", current: "原结论", candidate: "候选结论", reviewCta: "查看影响与依据", actions: { request: "补充证据", hold: "暂缓", approve: "确认新结论" },
    howEyebrow: "ONE LOOP / FOUR GATES", howTitle: ["从变化发生，", "到业务确认。"], howLead: "把一次现场判断，变成下一次业务变化仍能自动复核的决策记录。", flow: [["01", "CAPTURE", "记录业务变化", "记录变化来源、适用范围和业务负责人。"], ["02", "CONNECT", "形成决策链", "关联供应商、物料、订单、规则和证据。"], ["03", "VERIFY", "重算受影响判断", "标出需要复核的订单、候选结论和原因。"], ["04", "CONFIRM", "业务确认后生效", "负责人补充证据、暂缓，或确认新的处置结论。"]],
    trialEyebrow: "PRODUCT TRIAL", trialTitle: ["从一条规则变化进入，", "完成一次订单判断确认。"], trialLead: "选择供应链变化，检查受影响对象和候选结论，再由业务负责人决定是否生效。", openTrial: "打开供应链场景", preview: "场景演示", demoLabel: "示例数据", queue: "待确认事项", queueHint: "3 条规则变化待确认", inspect: "影响范围与依据", close: "关闭场景",
    buildEyebrow: "START WITH ONE REAL RULE", buildTitle: ["带来一条规则。", "先看它影响哪个订单。"], buildLead: "从供应商准入、交付承诺或订单优先级中选一个场景，跑通变化识别、关系追踪和业务确认。", buildPrimary: "打开供应链场景", buildSecondary: "回看影响路径",
  },
  en: {
    ariaNav: "OntoPoc primary navigation", home: "OntoPoc home", nav: { why: "PROBLEM", proof: "PRODUCT", how: "METHOD", model: "OPERATE" }, trial: "TRY A SCENARIO",
    heroAlt: "A halftone field showing impact moving through supply-chain relationships", heroVision: "Synthetic scenario preview: show a candidate impact path after a rule change; no confirmation, release, or writeback is executed.",
    heroMeta: [["DETECT", "Capture a business change", "Rules, data, relationships"], ["TRACE", "Reach the affected order", "Supplier, material, order"], ["CONFIRM", "Let the business decide", "Complete, hold, confirm"]], seeDelta: "SEE THE IMPACT PATH",
    heroKicker: "ONTOLOGY-NATIVE SUPPLY CHAIN AI", whyEyebrow: "THE MISSING LAYER", whyTitle: ["KNOWLEDGE BASES REMEMBER RULES.", "ONTOPOC FINDS THE ORDERS TO RECALCULATE."],
    whyLead: "ERP records transactions and knowledge bases preserve rules. When a rule changes, someone still has to find the affected orders and prior judgments. OntoPoc adds that continuous impact layer.",
    visionBody: "After the engagement, the enterprise keeps a decision asset that can still be verified, corrected, and released.",
    proofEyebrow: "SUPPLY CHAIN SCENARIO", proofTitle: ["PROMISE WINDOW: 7 TO 12 DAYS.", "WHICH ORDER NOW NEEDS INTERVENTION?"], proofLead: "The synthetic scenario preview shows the supplier–material–order relationships and a candidate path for order SC-2188. It does not execute recalculation, publication, or ERP writeback.",
    techPillars: [["RELATION GRAPH", "Synthetic path preview", "Supplier → Material → Order"], ["CANDIDATE VIEW", "Show a candidate judgment", "No Validation or runtime recalculation"], ["DELIVERY BOUNDARY", "Human gate shown only", "No publication or ERP writeback"]],
    modelEyebrow: "WHY IT COMPOUNDS", modelTitle: ["EVERY BUSINESS CORRECTION", "MAKES THE NEXT REVIEW FASTER."], modelLead: "The continuous-review loop is a product proposal. The verified capability is limited to generating and inspecting synthetic_demo Recognition, DecisionPack, and OntologySpec compiler artifacts; it does not persist confirmation records.",
    modelSteps: [["01 / START", "Begin with one judgment"], ["02 / CAPTURE", "Keep the correction evidence"], ["03 / REUSE", "Recheck the next change"]],
    deltaEyebrow: "CORE PRODUCT MOMENT", deltaTitle: ["SEE THE BUSINESS OUTCOME", "BEFORE THE MODEL DIFF."], deltaDescription: "Choose a business change and inspect which supply-chain judgments must be confirmed again. The interaction below is a product preview.", scenarioLabel: "Choose a business change", deltaAria: "DecisionDelta interactive product preview",
    domain: "SUPPLY CHAIN / RULE CHANGE", decision: "BUSINESS JUDGMENT", current: "PRIOR OUTCOME", candidate: "CANDIDATE OUTCOME", reviewCta: "REVIEW IMPACT & EVIDENCE", actions: { request: "REQUEST EVIDENCE", hold: "HOLD", approve: "CONFIRM OUTCOME" },
    howEyebrow: "ONE LOOP / FOUR GATES", howTitle: ["FROM A BUSINESS CHANGE", "TO BUSINESS CONFIRMATION."], howLead: "Turn one field judgment into a decision record that can be rechecked when the next change arrives.", flow: [["01", "CAPTURE", "Record the business change", "Keep its source, scope, and business owner together."], ["02", "CONNECT", "Form the decision chain", "Link suppliers, materials, orders, rules, and evidence."], ["03", "VERIFY", "Recalculate affected judgments", "Flag orders, candidate outcomes, and reasons that need review."], ["04", "CONFIRM", "Take effect after confirmation", "The owner completes evidence, holds, or confirms the new outcome."]],
    trialEyebrow: "PRODUCT TRIAL", trialTitle: ["ENTER THROUGH ONE RULE CHANGE.", "CONFIRM ONE ORDER OUTCOME."], trialLead: "Select a supply-chain change, inspect affected objects and the candidate outcome, then let the business owner decide whether it takes effect.", openTrial: "OPEN SUPPLY CHAIN SCENARIO", preview: "SCENARIO DEMO", demoLabel: "DEMO DATA", queue: "ITEMS TO CONFIRM", queueHint: "3 rule changes waiting", inspect: "IMPACT & EVIDENCE", close: "Close scenario",
    buildEyebrow: "START WITH ONE REAL RULE", buildTitle: ["BRING ONE REAL RULE.", "SEE WHICH ORDER IT CHANGES."], buildLead: "Choose supplier qualification, delivery promise, or order priority and walk through change detection, relationship tracing, and business confirmation.", buildPrimary: "OPEN SUPPLY CHAIN SCENARIO", buildSecondary: "REPLAY THE IMPACT PATH",
  },
};

const scenarios = [
  { id: "qualification", changeId: "CR-SC-2026-0829-01", version: "v1.3.0 → v1.3.1",
    zh: { tab: "供应商准入", change: "新增碳排与质量证明要求", title: "供应商准入要求发生变化", summary: "两家既有供应商缺少新要求的证明材料，相关订单的原处置结论需要重新确认。", deltas: [["订单 SC-1042", "不入队", "暂缓处理"], ["合格供应商", "3 家", "1 家"], ["替代物料", "可用", "需复核"]], evidence: ["29 / 32 项验证通过", "4 个对象受影响", "采购负责人待确认"] },
    en: { tab: "Supplier qualification", change: "New carbon and quality evidence", title: "Supplier evidence requirement updated", summary: "Two incumbent suppliers lack the new evidence, so related orders cannot keep their previous queue decision.", deltas: [["Order SC-1042", "Not queued", "Insufficient data"], ["Qualified suppliers", "3", "1"], ["Alternative material", "Available", "Review needed"]], evidence: ["29 / 32 checks pass", "4 objects affected", "Procurement owner"] } },
  { id: "commitment", changeId: "CR-SC-2026-0829-02", version: "v0.9.0 → v0.9.1",
    zh: { tab: "交付承诺", change: "关键物料承诺期延长", title: "供应商交付承诺发生变化", summary: "承诺期从 7 天延长到 12 天，订单 SC-2188 的原处置结论需要重新确认。", deltas: [["订单 SC-2188", "不入队", "进入优先干预"], ["承诺期", "7 天", "12 天"], ["关键物料", "3 项", "5 项"]], evidence: ["32 / 32 项验证通过", "5 个对象受影响", "需 2 人确认"] },
    en: { tab: "Delivery promise", change: "Critical-material window extended", title: "Supplier promise rule updated", summary: "The new promise window moves one previously normal order into the priority intervention queue.", deltas: [["Order SC-2188", "Not queued", "Priority queue"], ["Promise window", "7 days", "12 days"], ["Critical materials", "3", "5"]], evidence: ["32 / 32 checks pass", "5 objects affected", "Dual approval"] } },
  { id: "priority", changeId: "CR-SC-2026-0829-03", version: "v2.1.0 → v2.2.0",
    zh: { tab: "订单优先级", change: "战略客户延迟阈值下调", title: "订单优先干预规则发生变化", summary: "新阈值让战略客户订单更早进入干预范围，确认前不会进入执行流程。", deltas: [["订单 SC-3306", "不入队", "进入优先干预"], ["延迟阈值", "10 天", "7 天"], ["客户等级", "普通", "战略"]], evidence: ["31 / 32 项验证通过", "3 个对象受影响", "策略负责人待确认"] },
    en: { tab: "Priority policy", change: "Strategic delay threshold reduced", title: "Priority intervention policy updated", summary: "The new policy intervenes earlier on strategic accounts while keeping a human release gate.", deltas: [["Order SC-3306", "Not queued", "Priority queue"], ["Delay threshold", "10 days", "7 days"], ["Account tier", "Standard", "Strategic"]], evidence: ["31 / 32 checks pass", "3 objects affected", "Policy owner"] } },
];

const stateCopy = { zh: { needs_review: "等待业务确认", insufficient: "等待补充证据", held: "已暂缓", approved: "新结论已确认" }, en: { needs_review: "AWAITING BUSINESS CONFIRMATION", insufficient: "WAITING FOR EVIDENCE", held: "ON HOLD", approved: "NEW OUTCOME CONFIRMED" } };

const experienceCopy = {
  zh: {
    model: {
      eyebrow: "ONTOLOGY-AWARE WORKBENCH",
      title: "同一条业务判断，贯穿项目与持续运营。",
      caption: "以“供应商交付承诺”为例",
      owner: "业务负责人 / 供应链计划",
      stages: [
        { label: "START", status: "锁定业务判断", headline: "先说清一张订单该不该干预", body: "从订单 SC-2188 开始，确认它依赖哪些供应商、关键物料和交付规则。", metric: "1 个判断", receipt: "SC-2188 / SCOPE 01" },
        { label: "CAPTURE", status: "保留修正依据", headline: "把 7 天到 12 天的修正留下来", body: "合成场景预览把规则版本、业务证据、影响路径和确认人放在同一画面；当前 demo 不持久化该记录。", metric: "v0.9.1", receipt: "CORRECTION / RECEIPT 17" },
        { label: "REUSE", status: "再次发生变化", headline: "下次不用重新从头排查", body: "合成场景预览沿既有关系展示候选影响路径；不执行运行时重算或生成真实待办。", metric: "5 个对象", receipt: "REVIEW / QUEUE 03" },
      ],
      objectSet: "业务对象",
      relation: "对象关系",
      evidence: "证据与 Action",
      objects: ["Supplier / SUP-078", "Material / MAT-441", "Order / SC-2188"],
      chain: ["供应商 SUP-078", "供应 MAT-441", "用于订单 SC-2188"],
      evidenceRows: ["承诺规则 / v0.9.1", "供应商回执 / 2026-08-29", "负责人 / 王岚"],
      actionLabels: ["确认范围", "收录修正", "送交评审"],
      decisionLabel: "当前业务结论",
      stageDecisions: ["订单 SC-2188 是否进入优先干预队列？", "承诺窗口：7 天 → 12 天", "正常 → 进入优先干预队列"],
    },
    primitives: {
      eyebrow: "PRODUCT PRIMITIVES",
      title: "把现场工作，沉淀为可复用的决策组件。",
      hint: "选择一个组件查看其可追溯结构",
      items: [
        { label: "CHANGE EVENT", title: "变化事件", description: "把规则、数据或关系的变化，记录成一个有来源、有范围的事件。", meta: "CR-SC-2026-0829-02", state: "CAPTURED", rows: [["SOURCE", "ERP / PROMISE RULE"], ["SCOPE", "5 AFFECTED OBJECTS"], ["TIME", "2026-08-29 / 12:04"]] },
        { label: "IMPACT TRACE", title: "影响关系", description: "从变化沿本体关系找到受影响对象，并定位哪条业务判断需要重算。", meta: "TRACE / SC-2188", state: "VERIFIED", rows: [["OBJECT", "SUP-078 → MAT-441"], ["DECISION", "ORDER SC-2188"], ["OUTCOME", "NORMAL → PRIORITY"]] },
        { label: "APPROVAL RECEIPT", title: "审批回执", description: "把负责人、证据和发布结果保存在同一份可回溯记录中。", meta: "RECEIPT / v0.9.1", state: "HUMAN GATE", rows: [["OWNER", "WANG LAN / SUPPLY"], ["EVIDENCE", "32 / 32 CHECKS"], ["RELEASE", "2 OF 2 REQUIRED"]] },
      ],
      trace: {
        kicker: "SUPPLY CHAIN IMPACT / 场景演示", tracing: "正在沿对象关系追踪", awaiting: "等待业务确认", replay: "重新播放", replayLabel: "重新播放订单影响路径", ariaLabel: "供应商交付承诺变化沿物料关系传播到订单判断的关系图", currentState: "当前判断", stopNote: "系统给出影响范围、原因和候选结论；是否生效由业务负责人决定。",
        nodes: {
          change: { eyebrow: "规则变化", title: "交付承诺 v0.9.1", meta: "7 → 12 天", detail: "关键物料交付承诺期发生变化，开始检查相关供应商、物料与订单。", kind: "change" },
          supplier: { eyebrow: "SUPPLIER", title: "SUP-078", meta: "SOURCE OBJECT", detail: "该供应商提供受新承诺规则约束的关键物料。", kind: "object" },
          material: { eyebrow: "MATERIAL", title: "MAT-441", meta: "CRITICAL", detail: "关键物料 MAT-441 的预计到料窗口随规则改变。", kind: "object" },
          order: { eyebrow: "ORDER", title: "SC-2188", meta: "RECALCULATE", detail: "订单依赖该供应商与物料，因此原判断需要重新计算。", kind: "object" },
          "invalid-decision": { eyebrow: "原判断需复核", title: "正常 / 不入队", meta: "候选：进入优先干预", detail: "承诺期延长后，预计到料日越过战略订单的干预阈值。", kind: "decision" },
          "human-gate": { eyebrow: "业务确认", title: "等待供应链负责人确认", meta: "需 2 人确认", detail: "候选结论已经生成，确认前不会进入执行流程。", kind: "gate" },
        },
      },
    },
    replay: {
      kicker: "DECISION REPLAY / synthetic_demo",
      swipeHint: "点击 Gate 或横向滑动",
      status: ["CHANGE CAPTURED", "DECISIONPACK COMPILED", "IMPACT VERIFIED", "HUMAN GATE"],
      capture: { title: "供应商承诺规则发生变化", body: "关键物料交付承诺期限由 7 天延长至 12 天，并增加战略订单例外。", event: "CR-SC-2026-0829-02", affected: "已识别 5 个受影响对象", objects: ["Supplier SUP-078", "Material MAT-441", "Order SC-2188"] },
      compile: { title: "DecisionPack v0.9.1", body: "变化已被编译为可验证、可追溯的决策资产。", stats: [["03", "OBJECTS"], ["02", "LINKS"], ["04", "RULES"], ["01", "OWNER"]], receipt: "CHECKSUM 8F2A / DRAFT" },
      verify: { title: "订单 SC-2188 的原结论已不再成立", from: "正常 / 不入队", to: "进入优先干预队列", reason: "承诺窗口变化使预计到料日越过战略订单阈值。", checks: ["32 / 32 验证通过", "5 个对象受影响", "双人批准要求"] },
      approve: { title: "由业务负责人决定新逻辑是否生效", body: "批准后，新的判断与证据进入审计记录；原逻辑保留，可回溯。", gate: "需要业务负责人批准", receiptHint: "批准后生成审计回执", audit: "AUDIT RECEIPT / SC-2188 / v0.9.1", states: { needs_review: "等待业务批准", insufficient: "已要求补充证据", held: "发布已暂缓", approved: "新逻辑已批准" } },
    },
  },
  en: {
    model: {
      eyebrow: "ONTOLOGY-AWARE WORKBENCH",
      title: "ONE BUSINESS JUDGMENT, FROM ENGAGEMENT TO CONTINUOUS OPERATIONS.",
      caption: "Example: supplier delivery promise",
      owner: "Business owner / Supply planning",
      stages: [
        { label: "START", status: "Fix the business judgment", headline: "Begin with whether one order needs intervention", body: "Start with order SC-2188 and identify the supplier, critical material, and promise rule it depends on.", metric: "1 judgment", receipt: "SC-2188 / SCOPE 01" },
        { label: "CAPTURE", status: "Keep the correction evidence", headline: "Preserve the correction from 7 to 12 days", body: "The synthetic preview places the rule version, business evidence, impact path, and confirming owner in one view; the current demo does not persist that record.", metric: "v0.9.1", receipt: "CORRECTION / RECEIPT 17" },
        { label: "REUSE", status: "The next change arrives", headline: "Do not restart the investigation from scratch", body: "The synthetic preview shows a candidate impact path across existing relationships; it does not execute runtime recalculation or create a real work queue.", metric: "5 objects", receipt: "REVIEW / QUEUE 03" },
      ],
      objectSet: "BUSINESS OBJECTS",
      relation: "OBJECT RELATIONSHIP",
      evidence: "EVIDENCE & ACTION",
      objects: ["Supplier / SUP-078", "Material / MAT-441", "Order / SC-2188"],
      chain: ["Supplier SUP-078", "supplies MAT-441", "used in order SC-2188"],
      evidenceRows: ["Promise rule / v0.9.1", "Supplier receipt / 2026-08-29", "Owner / Wang Lan"],
      actionLabels: ["CONFIRM SCOPE", "CAPTURE CORRECTION", "ROUTE TO REVIEW"],
      decisionLabel: "CURRENT BUSINESS JUDGMENT",
      stageDecisions: ["Should order SC-2188 enter the priority intervention queue?", "Promise window: 7 days → 12 days", "Normal → Priority intervention queue"],
    },
    primitives: {
      eyebrow: "PRODUCT PRIMITIVES",
      title: "TURN FIELD WORK INTO REUSABLE DECISION COMPONENTS.",
      hint: "Select a component to inspect its traceable structure",
      items: [
        { label: "CHANGE EVENT", title: "Change event", description: "Record a rule, data, or relationship change as an event with a source and bounded scope.", meta: "CR-SC-2026-0829-02", state: "CAPTURED", rows: [["SOURCE", "ERP / PROMISE RULE"], ["SCOPE", "5 AFFECTED OBJECTS"], ["TIME", "2026-08-29 / 12:04"]] },
        { label: "IMPACT TRACE", title: "Impact trace", description: "Follow ontology relationships from the change to affected objects and the judgment that must be recalculated.", meta: "TRACE / SC-2188", state: "VERIFIED", rows: [["OBJECT", "SUP-078 → MAT-441"], ["DECISION", "ORDER SC-2188"], ["OUTCOME", "NORMAL → PRIORITY"]] },
        { label: "APPROVAL RECEIPT", title: "Approval receipt", description: "Keep the owner, evidence, and release result in one recoverable record.", meta: "RECEIPT / v0.9.1", state: "HUMAN GATE", rows: [["OWNER", "WANG LAN / SUPPLY"], ["EVIDENCE", "32 / 32 CHECKS"], ["RELEASE", "2 OF 2 REQUIRED"]] },
      ],
      trace: {
        kicker: "SUPPLY CHAIN IMPACT / SCENARIO DEMO", tracing: "TRACING OBJECT RELATIONSHIPS", awaiting: "AWAITING BUSINESS CONFIRMATION", replay: "REPLAY", replayLabel: "Replay the order impact path", ariaLabel: "Relationship graph showing a supplier promise change propagating through material to an order judgment", currentState: "CURRENT JUDGMENT", stopNote: "OntoPoc provides the impact scope, reason, and candidate outcome. The business owner decides whether it takes effect.",
        nodes: {
          change: { eyebrow: "CHANGE EVENT", title: "Promise rule v0.9.1", meta: "7 → 12 DAYS", detail: "The critical-material promise window changes and triggers an ontology relationship review.", kind: "change" },
          supplier: { eyebrow: "SUPPLIER", title: "SUP-078", meta: "SOURCE OBJECT", detail: "This supplier provides a critical material governed by the new promise rule.", kind: "object" },
          material: { eyebrow: "MATERIAL", title: "MAT-441", meta: "CRITICAL", detail: "The expected arrival window for material MAT-441 changes with the rule.", kind: "object" },
          order: { eyebrow: "ORDER", title: "SC-2188", meta: "RECALCULATE", detail: "The order depends on this supplier and material, so its prior outcome must be recalculated.", kind: "object" },
          "invalid-decision": { eyebrow: "PRIOR JUDGMENT TO REVIEW", title: "NORMAL / NOT QUEUED", meta: "CANDIDATE: PRIORITY INTERVENTION", detail: "The longer promise window pushes expected arrival beyond the strategic-order intervention threshold.", kind: "decision" },
          "human-gate": { eyebrow: "BUSINESS CONFIRMATION", title: "AWAITING SUPPLY-CHAIN OWNER", meta: "2 CONFIRMATIONS REQUIRED", detail: "The candidate outcome exists, but it will not enter execution before confirmation.", kind: "gate" },
        },
      },
    },
    replay: {
      kicker: "DECISION REPLAY / synthetic_demo",
      swipeHint: "Click a gate or swipe horizontally",
      status: ["CHANGE CAPTURED", "DECISIONPACK COMPILED", "IMPACT VERIFIED", "HUMAN GATE"],
      capture: { title: "Supplier promise logic changed", body: "The critical-material promise window moved from 7 to 12 days, with a new strategic-order exception.", event: "CR-SC-2026-0829-02", affected: "5 affected objects identified", objects: ["Supplier SUP-078", "Material MAT-441", "Order SC-2188"] },
      compile: { title: "DecisionPack v0.9.1", body: "The change is compiled into a traceable, testable decision asset.", stats: [["03", "OBJECTS"], ["02", "LINKS"], ["04", "RULES"], ["01", "OWNER"]], receipt: "CHECKSUM 8F2A / DRAFT" },
      verify: { title: "The prior outcome for order SC-2188 no longer holds", from: "NORMAL / NOT QUEUED", to: "PRIORITY INTERVENTION", reason: "The promise-window change pushes expected arrival beyond the strategic-order threshold.", checks: ["32 / 32 checks pass", "5 objects affected", "Dual approval required"] },
      approve: { title: "The business owner decides whether the new logic takes effect", body: "On approval, the new judgment and evidence enter the audit record. Prior logic remains recoverable.", gate: "BUSINESS OWNER APPROVAL REQUIRED", receiptHint: "AUDIT RECEIPT CREATED ON RELEASE", audit: "AUDIT RECEIPT / SC-2188 / v0.9.1", states: { needs_review: "AWAITING BUSINESS APPROVAL", insufficient: "EVIDENCE REQUESTED", held: "RELEASE ON HOLD", approved: "NEW LOGIC APPROVED" } },
    },
  },
};

export function App() {
  const [language, setLanguage] = useState("zh");
  const [trialOpen, setTrialOpen] = useState(false);
  const [activeGate, setActiveGate] = useState(0);
  const [activeModelStage, setActiveModelStage] = useState(0);
  const t = content[language];
  const experience = experienceCopy[language];

  useEffect(() => { document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; }, [language]);
  useEffect(() => {
    if (!trialOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event) => event.key === "Escape" && setTrialOpen(false);
    document.body.style.overflow = "hidden"; window.addEventListener("keydown", onKeyDown);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", onKeyDown); };
  }, [trialOpen]);

  const setLang = (next) => setLanguage(next);

  return <main>
    <header className="site-header" aria-label={t.ariaNav}>
      <a className="brand" href="#top" aria-label={t.home}><img src="/assets/ontopoc-logo.png" alt="OntoPoc" /></a>
      <nav>{primaryNavTargets.map((target) => <a href={`#${target}`} key={target}>{t.nav[target]}</a>)}</nav>
      <div className="header-actions"><div className="language-switch" aria-label="Language"><button className={language === "zh" ? "is-active" : ""} type="button" onClick={() => setLang("zh")} aria-pressed={language === "zh"}>中</button><button className={language === "en" ? "is-active" : ""} type="button" onClick={() => setLang("en")} aria-pressed={language === "en"}>EN</button></div><button className="header-cta" type="button" onClick={() => setTrialOpen(true)}>{t.trial} <ArrowDownRight size={17} strokeWidth={2.4} /></button></div>
    </header>

    <section className="hero" id="top"><img className="hero-field" src="/assets/decision-field.png" alt={t.heroAlt} /><div className="hero-kicker"><span className="live-dot" />{t.heroKicker}</div><h1><span>KEEP</span><span>DECISIONS</span><span>VALID.</span></h1><p className="hero-vision">{t.heroVision}</p><div className="hero-bottom"><button type="button" onClick={() => document.querySelector("#proof")?.scrollIntoView({ behavior: "smooth" })}>{t.seeDelta} <ArrowRight size={20} /></button></div></section>

    <section className="statement" id="why"><div className="section-index">01 / WHY</div><div className="statement-copy"><p className="eyebrow">{t.whyEyebrow}</p><h2>{t.whyTitle[0]}<br />{t.whyTitle[1]}</h2><p className="lead">{t.whyLead}</p></div></section>

    <PrimaryProof t={t} copy={experience.primitives.trace} />

    <section className="flow-section" id="how"><div className="section-heading"><div className="section-index">03 / HOW</div><p className="eyebrow">{t.howEyebrow}</p><h2>{t.howTitle[0]}<br />{t.howTitle[1]}</h2><p>{t.howLead}</p></div><div className="flow-progress" aria-hidden="true"><span style={{ transform: `scaleX(${(activeGate + 1) / t.flow.length})` }} /></div><div className="replay-layout"><div className="replay-gates" role="tablist" aria-label={t.howEyebrow}>{t.flow.map(([id, label, title], index) => { const gateState = index === activeGate ? "is-active" : index < activeGate ? "is-complete" : ""; return <button id={`gate-tab-${index}`} type="button" role="tab" aria-selected={index === activeGate} aria-controls={`gate-panel-${index}`} tabIndex={activeGate === index ? 0 : -1} className={`replay-gate ${gateState}`} onClick={() => setActiveGate(index)} onKeyDown={(event) => { if (!["ArrowRight", "ArrowLeft"].includes(event.key)) return; event.preventDefault(); const next = moveStage(index, event.key === "ArrowRight" ? 1 : -1, t.flow.length); setActiveGate(next); event.currentTarget.parentElement?.querySelector(`#gate-tab-${next}`)?.focus(); }} key={id}><span>{id} / {label}</span><strong>{title}</strong></button>; })}</div><GateSummary flow={t.flow} activeGate={activeGate} setActiveGate={setActiveGate} /></div></section>

    <section className="model-section" id="model"><div className="model-frame"><div className="section-index">04 / MODEL</div><div className="model-copy"><p className="eyebrow">{t.modelEyebrow}</p><h2>{t.modelTitle[0]}<br />{t.modelTitle[1]}</h2><p>{t.modelLead}</p></div><BusinessModelLoop t={t} copy={experience.model} activeStage={activeModelStage} setActiveStage={setActiveModelStage} /></div></section>

    <section className="build-section" id="build"><img className="build-field" src="/assets/decision-field.png" alt="" aria-hidden="true" /><div className="vertical-label">START WITH ONE DECISION</div><div className="build-content"><p className="eyebrow">{t.buildEyebrow}</p><h2>{t.buildTitle[0]}<br />{t.buildTitle[1]}</h2><p className="build-lead">{t.buildLead}</p><div className="build-actions"><button className="build-primary" type="button" onClick={() => setTrialOpen(true)}>{t.buildPrimary} <ArrowRight size={20} /></button><button className="build-secondary" type="button" onClick={() => document.querySelector("#proof")?.scrollIntoView({ behavior: "smooth" })}>{t.buildSecondary}</button></div></div></section>

    <footer><img src="/assets/ontopoc-logo.png" alt="OntoPoc" /><p>AI FDE DECISION COMPILER</p><p>© 2026 OntoPoc</p></footer>
    {trialOpen && <TrialModal t={t} language={language} onClose={() => setTrialOpen(false)} />}
  </main>;
}

const modelIcons = [PackageCheck, ClipboardCheck, GitCompareArrows];

function PrimaryProof({ t, copy }) {
  const proofRef = useRef(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    const element = proofRef.current;
    if (!element || !window.IntersectionObserver) { setActive(true); return undefined; }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setActive(true);
      observer.disconnect();
    }, { threshold: 0.28 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return <section className="proof-section" id="proof" ref={proofRef}>
    <div className="proof-heading"><div className="section-index">02 / PRODUCT MOMENT</div><p className="eyebrow">{t.proofEyebrow}</p><h2>{t.proofTitle[0]}<br />{t.proofTitle[1]}</h2><p>{t.proofLead}</p></div>
    <div className="proof-stage"><ImpactTrace active={active} copy={copy} /></div>
    <div className="proof-tech" aria-label="OntoPoc technical differentiators">{t.techPillars.map(([label, title, body]) => <div key={label}><span>{label}</span><strong>{title}</strong><p>{body}</p></div>)}</div>
  </section>;
}

function GateSummary({ flow, activeGate, setActiveGate }) {
  const swipeStart = useRef(null);
  const gate = flow[activeGate];
  const moveGate = (direction) => setActiveGate((current) => moveStage(current, direction, flow.length));
  return <div
    className="gate-summary"
    id={`gate-panel-${activeGate}`}
    role="tabpanel"
    aria-labelledby={`gate-tab-${activeGate}`}
    tabIndex={0}
    onPointerDown={(event) => { swipeStart.current = { x: event.clientX, y: event.clientY, id: event.pointerId }; event.currentTarget.setPointerCapture?.(event.pointerId); }}
    onPointerUp={(event) => { const start = swipeStart.current; swipeStart.current = null; if (!start || start.id !== event.pointerId) return; const deltaX = event.clientX - start.x; const deltaY = event.clientY - start.y; if (Math.abs(deltaX) >= 56 && Math.abs(deltaX) > Math.abs(deltaY) * 1.2) moveGate(deltaX < 0 ? 1 : -1); }}
    onKeyDown={(event) => { if (!["ArrowRight", "ArrowLeft"].includes(event.key)) return; event.preventDefault(); moveGate(event.key === "ArrowRight" ? 1 : -1); }}
  >
    <span className="gate-summary-count">0{activeGate + 1}</span>
    <div><span>{gate[1]}</span><h3>{gate[2]}</h3><p>{gate[3]}</p></div>
    <div className="gate-summary-path" aria-hidden="true">{flow.map((item, index) => <i className={index <= activeGate ? "is-active" : ""} key={item[0]} />)}</div>
  </div>;
}

function BusinessModelLoop({ t, copy, activeStage, setActiveStage }) {
  const stage = copy.stages[activeStage];
  return <div className="business-loop">
    <div className="business-loop-tabs" role="tablist" aria-label={t.modelEyebrow}>
      {t.modelSteps.map(([label, title], index) => <button id={`business-tab-${index}`} type="button" role="tab" aria-selected={activeStage === index} aria-controls={`business-panel-${index}`} tabIndex={activeStage === index ? 0 : -1} className={activeStage === index ? "is-active" : ""} onClick={() => setActiveStage(index)} onKeyDown={(event) => { if (!["ArrowRight", "ArrowLeft"].includes(event.key)) return; event.preventDefault(); const next = moveStage(index, event.key === "ArrowRight" ? 1 : -1, copy.stages.length); setActiveStage(next); event.currentTarget.parentElement?.querySelector(`#business-tab-${next}`)?.focus(); }} key={label}><span>{label}</span><strong>{title}</strong></button>)}
    </div>
    <div className="business-loop-panel" id={`business-panel-${activeStage}`} role="tabpanel" aria-labelledby={`business-tab-${activeStage}`} key={activeStage}>
      <div><span>{stage.status}</span><h3>{stage.headline}</h3></div>
      <p>{stage.body}</p>
      <div className="business-loop-receipt"><strong>{stage.metric}</strong><span>{stage.receipt}</span></div>
    </div>
  </div>;
}

function ModelWorkbench({ t, copy, activeStage, setActiveStage }) {
  const stage = copy.stages[activeStage];
  const StageIcon = modelIcons[activeStage];
  return <div className="model-workbench">
    <div className="model-stage-tabs" role="tablist" aria-label={copy.eyebrow}>
      {t.modelSteps.map(([label, title], index) => <button id={`model-tab-${index}`} type="button" role="tab" aria-selected={activeStage === index} aria-controls={`model-panel-${index}`} tabIndex={activeStage === index ? 0 : -1} className={activeStage === index ? "is-active" : ""} onClick={() => setActiveStage(index)} onKeyDown={(event) => { if (!['ArrowRight', 'ArrowLeft'].includes(event.key)) return; event.preventDefault(); const next = event.key === "ArrowRight" ? Math.min(copy.stages.length - 1, index + 1) : Math.max(0, index - 1); setActiveStage(next); event.currentTarget.parentElement?.querySelector(`#model-tab-${next}`)?.focus(); }} key={label}><span>{label}</span><strong>{title}</strong></button>)}
    </div>
    <div className="workbench-window" id={`model-panel-${activeStage}`} role="tabpanel" aria-labelledby={`model-tab-${activeStage}`} key={activeStage}>
      <header className="workbench-header"><div><Workflow size={17} /> ONTOPOC / DECISION OPERATIONS</div><span>synthetic_demo</span></header>
      <div className="workbench-context">
        <div><span>{copy.caption}</span><strong>{stage.status}</strong></div>
        <div><span>{copy.owner}</span><strong>{stage.receipt}</strong></div>
      </div>
      <div className="workbench-grid">
        <aside className="object-panel">
          <div className="panel-label"><Database size={15} /> {copy.objectSet}</div>
          {copy.objects.map((object, index) => <button type="button" aria-pressed={index === activeStage} className={index === activeStage ? "is-selected" : ""} onClick={() => setActiveStage(index)} key={object}><span>0{index + 1}</span><strong>{object}</strong></button>)}
        </aside>
        <div className="relationship-panel">
          <div className="panel-label"><Link2 size={15} /> {copy.relation}</div>
          <div className="decision-focus">
            <div className="focus-icon"><StageIcon size={24} /></div>
            <span>{copy.decisionLabel}</span>
            <h3>{copy.stageDecisions[activeStage]}</h3>
            <p>{stage.body}</p>
          </div>
          <div className="object-chain">
            {copy.chain.map((node, index) => <div className="chain-item" key={node}><span>{index === 0 ? <Factory size={16} /> : index === 1 ? <Boxes size={16} /> : <Truck size={16} />}</span><strong>{node}</strong>{index < copy.chain.length - 1 && <ArrowRight size={17} />}</div>)}
          </div>
        </div>
        <aside className="evidence-panel">
          <div className="panel-label"><FileCheck2 size={15} /> {copy.evidence}</div>
          <div className="stage-result"><span>{stage.metric}</span><h3>{stage.headline}</h3></div>
          <div className="evidence-list">{copy.evidenceRows.map((row) => <div key={row}><Check size={14} /><span>{row}</span></div>)}</div>
          <button type="button" onClick={() => setActiveStage((activeStage + 1) % copy.stages.length)}>{copy.actionLabels[activeStage]} <ArrowRight size={16} /></button>
        </aside>
      </div>
    </div>
  </div>;
}

const primitiveIcons = [AlertTriangle, GitCompareArrows, BadgeCheck];

function ProductPrimitives({ copy }) {
  const [activePrimitive, setActivePrimitive] = useState(0);
  return <div className="product-primitives">
    <div className="primitive-heading"><div><span>{copy.eyebrow}</span><h3>{copy.title}</h3></div><p>{copy.hint}</p></div>
    <div className="primitive-shell">
      <div className="primitive-tabs" role="tablist" aria-label={copy.eyebrow}>
        {copy.items.map((item, index) => {
          const Icon = primitiveIcons[index];
          return <button id={`primitive-tab-${index}`} type="button" role="tab" aria-selected={activePrimitive === index} aria-controls={`primitive-panel-${index}`} tabIndex={activePrimitive === index ? 0 : -1} className={activePrimitive === index ? "is-active" : ""} onClick={() => setActivePrimitive(index)} onKeyDown={(event) => { if (!['ArrowRight', 'ArrowLeft'].includes(event.key)) return; event.preventDefault(); const next = event.key === "ArrowRight" ? (index + 1) % copy.items.length : (index - 1 + copy.items.length) % copy.items.length; setActivePrimitive(next); event.currentTarget.parentElement?.querySelector(`#primitive-tab-${next}`)?.focus(); }} key={item.label}><Icon size={18} /><span>0{index + 1}</span><strong>{item.label}</strong></button>;
        })}
      </div>
      {copy.items.map((item, index) => {
        const Icon = primitiveIcons[index];
        return <div id={`primitive-panel-${index}`} className={`primitive-panel ${index === 1 ? "is-impact-trace" : ""}`} role="tabpanel" aria-labelledby={`primitive-tab-${index}`} hidden={activePrimitive !== index} key={item.label}>
          {index === 1 ? (activePrimitive === index ? <ImpactTrace active copy={copy.trace} /> : null) : <>
            <div className="primitive-summary"><div className="primitive-icon"><Icon size={25} /></div><span>{item.label}</span><h3>{item.title}</h3><p>{item.description}</p></div>
            <div className="primitive-ledger"><header><span>{item.meta}</span><strong>{item.state}</strong></header>{item.rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
          </>}
        </div>;
      })}
    </div>
  </div>;
}

function DecisionReplay({ copy, activeGate, setActiveGate }) {
  const swipeStart = useRef(null);
  const wheelLocked = useRef(false);
  const moveGate = (direction) => setActiveGate((current) => Math.max(0, Math.min(copy.status.length - 1, current + direction)));
  const startSwipe = (event) => {
    if (event.target.closest?.("button")) return;
    swipeStart.current = { x: event.clientX, y: event.clientY, pointerId: event.pointerId };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const finishSwipe = (event) => {
    const start = swipeStart.current;
    swipeStart.current = null;
    if (!start || start.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.abs(deltaX) >= 56 && Math.abs(deltaX) > Math.abs(deltaY) * 1.2) moveGate(deltaX < 0 ? 1 : -1);
  };
  const handleWheel = (event) => {
    if (Math.abs(event.deltaX) < 24 || Math.abs(event.deltaX) <= Math.abs(event.deltaY) || wheelLocked.current) return;
    event.preventDefault();
    wheelLocked.current = true;
    moveGate(event.deltaX > 0 ? 1 : -1);
    window.setTimeout(() => { wheelLocked.current = false; }, 360);
  };
  const scenes = [
    <CaptureScene copy={copy.capture} />,
    <CompileScene copy={copy.compile} />,
    <VerifyScene copy={copy.verify} />,
    <ApproveScene copy={copy.approve} />,
  ];
  return <div className={`replay-stage replay-stage-${activeGate}`} id={`gate-panel-${activeGate}`} role="tabpanel" tabIndex="0" aria-labelledby={`gate-tab-${activeGate}`} aria-label={`${copy.status[activeGate]}. ${copy.swipeHint}`} onPointerDown={startSwipe} onPointerUp={finishSwipe} onPointerCancel={() => { swipeStart.current = null; }} onWheel={handleWheel} onKeyDown={(event) => { if (event.key === "ArrowRight") moveGate(1); if (event.key === "ArrowLeft") moveGate(-1); }}>
    <header><div><span className="status-dot" />{copy.status[activeGate]}</div><span className="replay-gesture"><MoveHorizontal size={14} />{copy.swipeHint}<b>{copy.kicker}</b></span></header>
    <div className="replay-scene" key={activeGate}>{scenes[activeGate]}</div>
  </div>;
}

function CaptureScene({ copy }) {
  return <div className="capture-scene">
    <div className="scene-primary"><div className="scene-icon"><AlertTriangle size={24} /></div><span>CHANGE EVENT / {copy.event}</span><h3>{copy.title}</h3><p>{copy.body}</p><strong>{copy.affected}</strong></div>
    <div className="impact-objects"><span>AFFECTED OBJECTS</span>{copy.objects.map((object, index) => <div key={object}><b>0{index + 1}</b><strong>{object}</strong><ArrowRight size={16} /></div>)}</div>
  </div>;
}

function CompileScene({ copy }) {
  return <div className="compile-scene"><div className="pack-title"><div className="scene-icon"><Workflow size={24} /></div><span>COMPILE RECEIPT</span><h3>{copy.title}</h3><p>{copy.body}</p></div><div className="pack-stats">{copy.stats.map(([number, label]) => <div key={label}><strong>{number}</strong><span>{label}</span></div>)}</div><div className="pack-footer"><span>{copy.receipt}</span><div><i /><i /><i /><i /></div></div></div>;
}

function VerifyScene({ copy }) {
  return <div className="verify-scene"><div className="verify-title"><div className="scene-icon"><GitCompareArrows size={24} /></div><span>DECISION VALIDITY CHECK</span><h3>{copy.title}</h3></div><div className="outcome-shift"><div><span>CURRENT</span><strong>{copy.from}</strong></div><ArrowRight size={28} /><div><span>CANDIDATE</span><strong>{copy.to}</strong></div></div><p>{copy.reason}</p><div className="verify-checks">{copy.checks.map((check, index) => <div key={check}>{index === 2 ? <UserCheck size={16} /> : <Check size={16} />}<span>{check}</span></div>)}</div></div>;
}

function ApproveScene({ copy }) {
  return <div className="approve-scene"><div className="approve-summary"><div className="scene-icon"><UserCheck size={24} /></div><span>RELEASE AUTHORITY / SUPPLY PLANNING</span><h3>{copy.title}</h3><p>{copy.body}</p></div><div className="approval-receipt needs-review"><div><BadgeCheck size={22} /><span>{copy.states.needs_review}</span></div><strong>{copy.audit}</strong></div><div className="approval-mechanism"><strong>{copy.gate}</strong><span>{copy.receiptHint}</span></div></div>;
}

function DecisionMoment({ t, language, scenario, localized, onOpenTrial }) {
  const [decision, current, candidate] = localized.deltas[0];
  return <div className="review-console decision-moment" aria-label={t.deltaAria}>
    <div className="console-header"><div><span className="orange-dot" /> {stateCopy[language].needs_review}<span className="demo-badge">{t.demoLabel}</span></div><span>{scenario.changeId}</span></div>
    <div className="moment-title" key={`${scenario.id}-moment`}><div><span>{t.domain}</span><h3>{localized.title}</h3><p>{localized.summary}</p></div><span className="version">{scenario.version}</span></div>
    <div className="moment-shift" key={`${scenario.id}-shift`}><div><span>{t.decision}</span><strong>{decision}</strong></div><div><span>{t.current}</span><strong>{current}</strong></div><ArrowRight size={22} /><div className="candidate"><span>{t.candidate}</span><strong>{candidate}</strong></div></div>
    <div className="evidence-row">{localized.evidence.map((evidence, index) => <div key={evidence}>{index === 0 ? <FileCheck2 size={18} /> : index === 1 ? <ScanSearch size={18} /> : <ShieldCheck size={18} />} {evidence}</div>)}</div>
    <button className="moment-cta" type="button" onClick={onOpenTrial}>{t.reviewCta}<ArrowRight size={18} /></button>
  </div>;
}

function DecisionConsole({ t, language, scenario, localized, reviewState, setReviewState }) {
  return <div className={`review-console ${reviewState}`} aria-label={t.deltaAria}><div className="console-header"><div><span className="orange-dot" /> {stateCopy[language][reviewState]}<span className="demo-badge">{t.demoLabel}</span></div><span>{scenario.changeId}</span></div><div className="console-title" key={`${scenario.id}-title`}><div><span>{t.domain}</span><h3>{localized.title}</h3><p>{localized.summary}</p></div><span className="version">{scenario.version}</span></div><div className="delta-head"><span>{t.decision}</span><span>{t.current}</span><span>{t.candidate}</span></div><div className="delta-body" key={scenario.id}>{localized.deltas.map(([name, current, candidate], index) => <div className="delta-row" style={{ "--row-index": index }} key={name}><strong>{name}</strong><span>{current}</span><span className="candidate">{candidate}</span></div>)}</div><div className="evidence-row" key={`${scenario.id}-evidence`}><div><FileCheck2 size={18} /> {localized.evidence[0]}</div><div><ScanSearch size={18} /> {localized.evidence[1]}</div><div><ShieldCheck size={18} /> {localized.evidence[2]}</div></div><div className="console-actions"><button type="button" aria-pressed={reviewState === "insufficient"} onClick={() => setReviewState("insufficient")}>{t.actions.request}</button><button type="button" aria-pressed={reviewState === "held"} onClick={() => setReviewState("held")}>{t.actions.hold}</button><button type="button" aria-pressed={reviewState === "approved"} className="approve" onClick={() => setReviewState("approved")}><Check size={18} /> {t.actions.approve}</button></div></div>;
}

function TrialModal({ t, language, onClose }) {
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    previousFocusRef.current = document.activeElement;
    const focusFrame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(focusFrame);
      previousFocusRef.current?.focus();
    };
  }, []);

  const trapFocus = (event) => {
    if (event.key !== "Tab") return;
    const focusableElements = [...dialogRef.current.querySelectorAll('button, [href], textarea, input, select, [tabindex]:not([tabindex="-1"])')].filter((element) => !element.disabled);
    if (!focusableElements.length) return;
    const first = focusableElements[0];
    const last = focusableElements[focusableElements.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };

  return <div className="trial-overlay" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section ref={dialogRef} className="trial-window" role="dialog" aria-modal="true" aria-label={t.preview} onKeyDown={trapFocus}><aside className="trial-rail"><img src="/assets/ontopoc-logo.png" alt="OntoPoc" /><div><Layers3 size={18} /><ScanSearch size={18} /><ShieldCheck size={18} /></div><span>OP</span></aside><div className="trial-workspace"><div className="trial-topbar"><div><span>{t.preview}</span><small>synthetic_demo · READ ONLY</small></div><button ref={closeButtonRef} type="button" onClick={onClose} aria-label={t.close}><X size={20} /></button></div><TrialWorkspace language={language} /></div></section></div>;
}
