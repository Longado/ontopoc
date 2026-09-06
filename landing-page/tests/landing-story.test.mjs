import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const workspace = await readFile(new URL("../src/TrialWorkspace.jsx", import.meta.url), "utf8").catch(() => "");
const ontologyWorkspace = await readFile(new URL("../src/OntologyWorkspace.jsx", import.meta.url), "utf8").catch(() => "");
const documentModeler = await readFile(new URL("../src/DocumentModeler.jsx", import.meta.url), "utf8").catch(() => "");
const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

test("landing story has one full operational surface and the accepted section order", () => {
  assert.equal(app.includes('className="trial-section"'), false);
  assert.match(app, /<PrimaryProof t=\{t\} copy=\{experience\.primitives\.trace\} \/>/);

  const review = app.indexOf('id="review"');
  const how = app.indexOf('id="how"');
  const model = app.indexOf('id="model"');
  const build = app.indexOf('id="build"');
  assert.ok(review < how && how < model && model < build);
});

test("landing copy labels runtime and persistence behavior as synthetic or proposed", () => {
  assert.match(app, /合成场景预览/);
  assert.match(app, /当前已验证能力仅生成并检查 synthetic_demo/);
  assert.match(app, /Synthetic scenario preview/);
  assert.match(app, /The verified capability is limited to generating and inspecting synthetic_demo/);
  assert.match(app, /不执行运行时重算或生成真实待办/);
  assert.match(app, /does not execute runtime recalculation or create a real work queue/);

  assert.doesNotMatch(app, /规则一变，立即找出受影响订单；业务确认后生效。/);
  assert.doesNotMatch(app, /OntoPoc propagates the change through supplier–material–order relationships, recalculates the judgment/);
  assert.doesNotMatch(app, /规则版本、业务证据、影响路径和确认人进入同一份可回溯记录。/);
  assert.doesNotMatch(app, /The rule version, business evidence, impact path, and confirming owner stay in one recoverable record/);
});

test("mounted Trial path uses the artifact workspace without approval controls", () => {
  assert.equal(app.includes("replayState"), false);
  assert.match(app, /function ApproveScene\(\{ copy \}\)/);
  assert.match(app, /className="approval-mechanism"/);
  assert.match(app, /import \{ TrialWorkspace \} from "\.\/TrialWorkspace\.jsx"/);
  const mountedTrial = app.slice(app.indexOf("function TrialModal"));
  assert.match(mountedTrial, /<TrialWorkspace language=\{language\} \/>/);
  assert.doesNotMatch(mountedTrial, /<DecisionConsole/);
  assert.doesNotMatch(workspace, /className="console-actions"|t\.actions\.approve|setReviewState/);
});

test("Trial workspace runs one synchronous artifact load and exposes four read-only stages", () => {
  assert.match(workspace, /status, setStatus.*"idle"/);
  assert.match(workspace, /setStatus\("loading"\)/);
  assert.match(workspace, /setStatus\("succeeded"\)/);
  assert.match(workspace, /setStatus\("error"\)/);
  assert.match(workspace, /fetch\("\/artifacts\/supply-chain-recognition\.json"/);
  assert.doesNotMatch(workspace, /setTimeout|setInterval/);
  assert.match(workspace, /RecognitionPanel/);
  assert.match(workspace, /DecisionPackPanel/);
  assert.match(workspace, /OntologySpecPanel/);
  assert.match(workspace, /ValidationPanel/);
});

test("Validation projects recorded receipts, evidence hashes, and delivery boundaries", () => {
  assert.match(workspace, /后端已记录的回执 · 无实时执行 · 无外部写入/);
  assert.match(workspace, /BACKEND-RECORDED RECEIPTS · NO LIVE EXECUTION · NO EXTERNAL WRITE/);
  assert.match(workspace, /data\.cases\.map/);
  assert.match(workspace, /className={`validation-case-row/);
  assert.match(workspace, /atRiskChange/);
  assert.match(workspace, /唯一变化 · at_risk/);
  assert.match(workspace, /<details/);
  assert.match(workspace, /decisionPackContentHash/);
  assert.match(workspace, /ontologySpecContentHash/);
  assert.match(workspace, /factsContentHash/);
  assert.match(workspace, /receipt\.contentHash/);
  assert.match(workspace, /receipt\.factRefs/);
  assert.match(workspace, /receipt\.evidenceRefs/);
  assert.match(workspace, /className="validation-boundaries"/);
  assert.doesNotMatch(workspace, /receipt = null|CONTRACT ONLY \/ NOT IMPLEMENTED/);
});

test("idle Trial mounts the document modeler and only its compiled action runs the artifact callback", () => {
  assert.match(workspace, /import \{ DocumentModeler \} from "\.\/DocumentModeler\.jsx"/);
  assert.match(workspace, /<DocumentModeler language=\{language\} runAgentDemo=\{runAgentDemo\} \/>/);
  assert.match(documentModeler, /resolveDocumentModelingRequest/);
  assert.match(documentModeler, /runAgentDemo/);
  assert.match(documentModeler, /QUALITY EVENT TRACE \/ PHASE 1/);
});

test("recorded Agent review binds the compiled candidate set before entering the workspace", () => {
  assert.match(workspace, /createRecordedAgentModelingSession/);
  assert.match(workspace, /confirmAgentModelingSession/);
  assert.match(workspace, /setStatus\("agent_review"\)/);
  assert.match(workspace, /function AgentReviewPanel/);
  assert.match(workspace, /session\.candidates\.counts/);
  assert.match(workspace, /confirmationReceipt/);
  assert.match(workspace, /session\.boundaries/);
  assert.match(workspace, /SESSION ONLY \/ NOT SAVED/);
  assert.doesNotMatch(workspace, /method:\s*["']POST|localStorage|sessionStorage/);
});

test("document modeler exposes deterministic presets and a read-only candidate graph", () => {
  assert.match(documentModeler, /QUALITY EVENT TRACE \/ PHASE 1/);
  assert.match(documentModeler, /SCENARIO PREVIEW \/ NOT COMPILED/);
  assert.match(documentModeler, /synthetic_demo/);
  assert.match(documentModeler, /<textarea/);
  assert.match(documentModeler, /type="button"/);
  assert.match(documentModeler, /from "@xyflow\/react"/);
  assert.match(documentModeler, /nodesDraggable=\{false\}/);
  assert.match(documentModeler, /nodesConnectable=\{false\}/);
  assert.match(documentModeler, /edgesReconnectable=\{false\}/);
  assert.match(documentModeler, /onNodeClick=/);
  assert.match(documentModeler, /className=\{`document-evidence-item/);
});

test("Phase 1 leads with the quality event, cross-source records, and an explicit data gap", () => {
  assert.match(documentModeler, /className="quality-event-summary"/);
  assert.match(documentModeler, /preset\.event\.id/);
  assert.match(documentModeler, /preset\.investigationQuestion/);
  assert.match(documentModeler, /className="source-record-list"/);
  assert.match(documentModeler, /preset\.sourceRecords\.map/);
  assert.match(documentModeler, /record\.status === "missing"/);
  assert.match(documentModeler, /evidence\?\.evidenceRef/);
  assert.match(documentModeler, /查看追溯证据链/);
});

test("Phase 1 reads one fixed investigation artifact and shows factors, counterevidence, and gaps", () => {
  assert.match(documentModeler, /fetch\("\/artifacts\/quality-investigation\.json"/);
  assert.match(documentModeler, /className="investigation-scope-summary"/);
  assert.match(documentModeler, /className="investigation-factor-list"/);
  assert.match(documentModeler, /investigation\.factors\.map/);
  assert.match(documentModeler, /factor\.counterevidence_refs/);
  assert.match(documentModeler, /investigation\.gaps\.map/);
  assert.match(documentModeler, /优先调查/);
  assert.match(documentModeler, /正常对照削弱/);
  assert.doesNotMatch(documentModeler, /evaluate_investigation_scope|EXECUTED_ON.*USES_BATCH/s);
});

test("Phase 1 leads with four-state control scope objects before investigation factors", () => {
  assert.match(documentModeler, /className="control-scope-summary"/);
  assert.match(documentModeler, /className="control-scope-groups"/);
  assert.match(documentModeler, /investigation\.control_scope_objects\.filter/);
  assert.match(documentModeler, /确定影响/);
  assert.match(documentModeler, /可能影响/);
  assert.match(documentModeler, /已排除/);
  assert.match(documentModeler, /无法评估/);
  assert.match(documentModeler, /object\.reason/);
  assert.ok(
    documentModeler.indexOf('className="control-scope-summary"')
      < documentModeler.indexOf('className="investigation-factor-list"'),
  );
});

test("Phase 1 lets the quality owner finish a session-only control scope decision", () => {
  assert.match(documentModeler, /controlDecisions, setControlDecisions/);
  assert.match(documentModeler, /className="control-scope-actions"/);
  assert.match(documentModeler, /纳入临时控制/);
  assert.match(documentModeler, /待补证/);
  assert.match(documentModeler, /aria-pressed=\{controlDecisions\[object\.object_id\] === action\.id\}/);
  assert.match(documentModeler, /className="control-decision-summary"/);
  assert.match(documentModeler, /本次范围已完成/);
  assert.match(documentModeler, /会话内选择 · 未执行业务控制/);
  assert.doesNotMatch(documentModeler, /localStorage|sessionStorage|method:\s*["']POST/);
});

test("Phase 1 lets the FDE adjust evidence-bound candidates and confirm a session-only pack", () => {
  assert.match(documentModeler, /buildPhase1DecisionPack/);
  assert.match(documentModeler, /preset\.decisionOwner/);
  assert.match(documentModeler, /preset\.trigger/);
  assert.match(documentModeler, /toggleCandidate/);
  assert.match(documentModeler, /projectCandidateGraph\(result\.preset, includedCandidates\)/);
  assert.match(documentModeler, /includedEntityIds\.has\(source\)/);
  assert.match(documentModeler, /reviewNote/);
  assert.match(documentModeler, /confirmDecisionPack/);
  assert.doesNotMatch(documentModeler, /downloadDecisionPack|createObjectURL|Download/);
  assert.match(documentModeler, /decision_pack\.phase1_candidate\.v1/);
  assert.match(documentModeler, /SESSION ONLY/);
  assert.match(documentModeler, /对象候选/);
});

test("document modeling only reads the fixed synthetic artifact and exposes no API POST or credential surface", () => {
  assert.equal((documentModeler.match(/fetch\(/g) ?? []).length, 1);
  assert.match(documentModeler, /fetch\("\/artifacts\/quality-investigation\.json"/);
  assert.doesNotMatch(documentModeler, /axios|\.post\(|method:\s*["']POST|\/api\/|token|credential/i);
  assert.doesNotMatch(documentModeler, /file|upload|persist|publish|writeback|approval/i);
  assert.doesNotMatch(documentModeler, /ValidationReceipt|Action/);
});

test("idle document modeler is PC-first and collapses without horizontal overflow", () => {
  assert.match(styles, /\.standalone-demo\s*\{[^}]*min-width:\s*0/s);
  assert.doesNotMatch(styles, /\.standalone-demo\s*\{[^}]*min-width:\s*1024px/s);
  assert.match(styles, /\.document-modeler\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1\.1fr\)/s);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*\.document-modeler\s*\{[^}]*grid-template-columns:\s*1fr/s);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*\.standalone-demo-workspace\s*\{[^}]*overflow:\s*visible/s);
  assert.match(styles, /\.document-modeler\s*\{[^}]*min-width:\s*0/s);
});

test("desktop Trial keeps artifact content and evidence in a PC-first split layout", () => {
  assert.match(workspace, /className="workspace-detail-layout"/);
  assert.match(workspace, /className="workspace-detail-main"/);
  assert.match(workspace, /className="workspace-detail-aside"/);
  assert.match(styles, /\.workspace-detail-layout\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) 300px/s);
  assert.match(styles, /\.workspace-detail-aside\s*\{[^}]*position:\s*sticky/s);
});

test("OntologySpec owns a read-only Graph and Details view without creating a fifth stage", () => {
  assert.match(workspace, /import \{ OntologyWorkspace \} from "\.\/OntologyWorkspace\.jsx"/);
  assert.match(workspace, /<OntologyWorkspace data=\{data\} t=\{t\} language=\{language\} \/>/);
  assert.match(ontologyWorkspace, /from "@xyflow\/react"/);
  assert.match(ontologyWorkspace, /nodesDraggable=\{false\}/);
  assert.match(ontologyWorkspace, /nodesConnectable=\{false\}/);
  assert.match(ontologyWorkspace, /edgesReconnectable=\{false\}/);
  assert.match(ontologyWorkspace, /className="ontology-node-copy"/);
  assert.match(ontologyWorkspace, /role="tablist" aria-label=\{copy\.viewLabel\}/);
  assert.match(ontologyWorkspace, /Graph/);
  assert.match(ontologyWorkspace, /Details/);
  assert.match(ontologyWorkspace, /ArrowLeft/);
  assert.match(ontologyWorkspace, /ArrowRight/);
  assert.match(ontologyWorkspace, /onSelectionChange=/);
  assert.match(ontologyWorkspace, /selection\.nodes/);
  assert.match(ontologyWorkspace, /selection\.edges/);
});

test("ontology graph keeps a 300px inspector and exposes deterministic fit and reset controls", () => {
  assert.match(ontologyWorkspace, /className="ontology-graph-layout"/);
  assert.match(ontologyWorkspace, /className="ontology-inspector-shell"/);
  assert.match(ontologyWorkspace, /fitView/);
  assert.match(ontologyWorkspace, /setViewport/);
  assert.match(styles, /\.ontology-graph-layout\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) 300px/s);
  assert.match(styles, /\.ontology-graph-canvas\s*\{[^}]*background-color:\s*#f8f7f1/s);
});

test("artifact chat is a same-width deterministic drawer with refusal boundaries and no API write", () => {
  assert.match(ontologyWorkspace, /answerArtifactQuestion/);
  assert.match(ontologyWorkspace, /className="ontology-chat-drawer"/);
  assert.match(ontologyWorkspace, /确定性 artifact 查询/);
  assert.match(ontologyWorkspace, /非实时模型调用/);
  assert.match(ontologyWorkspace, /missing_runtime_facts/);
  assert.match(ontologyWorkspace, /event\.key === "Enter"/);
  assert.match(ontologyWorkspace, /event\.key === "Escape"/);
  assert.match(ontologyWorkspace, /chatWasOpenRef\.current/);
  assert.match(ontologyWorkspace, /chatTriggerRef\.current\?\.focus/);
  assert.doesNotMatch(ontologyWorkspace, /fetch\(|axios|\.post\(|\/api\/|token/i);
  assert.match(styles, /\.ontology-chat-drawer\s*\{[^}]*position:\s*absolute/s);
  assert.match(styles, /\.ontology-chat-drawer\s*\{[^}]*inset:\s*0/s);
});

test("workbench and gate tabs expose controlled panels and roving focus", () => {
  assert.match(app, /id={`model-tab-\$\{index\}`}/);
  assert.match(app, /aria-controls={`model-panel-\$\{index\}`}/);
  assert.match(app, /id={`gate-tab-\$\{index\}`}/);
  assert.match(app, /aria-controls={`gate-panel-\$\{index\}`}/);
  assert.match(app, /tabIndex={activeStage === index \? 0 : -1}/);
  assert.match(app, /tabIndex={activeGate === index \? 0 : -1}/);
});

test("modal traps focus and restores it to the opener", () => {
  assert.match(app, /previousFocusRef/);
  assert.match(app, /closeButtonRef/);
  assert.match(app, /focusableElements/);
  assert.match(app, /previousFocusRef\.current\?\.focus/);
});

test("primary proof mounts the accepted Impact Trace surface", () => {
  assert.match(app, /function PrimaryProof\(\{ t, copy \}\)/);
  assert.match(app, /<ImpactTrace active=\{active\} copy=\{copy\} \/>/);
});
