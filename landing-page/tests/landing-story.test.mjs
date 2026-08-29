import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const workspace = await readFile(new URL("../src/TrialWorkspace.jsx", import.meta.url), "utf8").catch(() => "");
const ontologyWorkspace = await readFile(new URL("../src/OntologyWorkspace.jsx", import.meta.url), "utf8").catch(() => "");
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
