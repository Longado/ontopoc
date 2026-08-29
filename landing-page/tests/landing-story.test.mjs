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

test("idle Trial mounts the document modeler and only its compiled action runs the artifact callback", () => {
  assert.match(workspace, /import \{ DocumentModeler \} from "\.\/DocumentModeler\.jsx"/);
  assert.match(workspace, /<DocumentModeler language=\{language\} runAgentDemo=\{runAgentDemo\} \/>/);
  assert.match(documentModeler, /resolveDocumentModelingRequest/);
  assert.match(documentModeler, /runAgentDemo/);
  assert.match(documentModeler, /BUSINESS MODELING AGENT \/ RECORDED DEMO/);
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
  assert.match(documentModeler, /BUSINESS MODELING AGENT \/ RECORDED DEMO/);
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

test("document modeling stays frontend-only and exposes no API POST or credential surface", () => {
  assert.doesNotMatch(documentModeler, /fetch\(|axios|\.post\(|method:\s*["']POST|\/api\/|token|credential/i);
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
